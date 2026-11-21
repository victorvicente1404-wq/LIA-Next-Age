from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

PAIRING_REQUEST_TTL_SECONDS = 300
DEFAULT_DEVICE_TOKEN_TTL_SECONDS = 30 * 24 * 60 * 60
MAX_PAIRING_ATTEMPTS = 5
ALLOWED_DEVICE_SCOPES = frozenset({"chat", "voice"})


class PairingError(Exception):
    pass


class PairingStore:
    """Local-approval device pairing; only token hashes are persisted."""

    def __init__(
        self,
        database_path: Path,
        token_ttl_seconds: int = DEFAULT_DEVICE_TOKEN_TTL_SECONDS,
    ) -> None:
        self._path = database_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._token_ttl = token_ttl_seconds
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS pairing_requests (
                    id TEXT PRIMARY KEY,
                    device_name TEXT NOT NULL,
                    code_hash TEXT NOT NULL,
                    scopes TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending'
                );
                CREATE TABLE IF NOT EXISTS paired_devices (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    token_hash TEXT NOT NULL UNIQUE,
                    scopes TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    revoked_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_pairing_requests_status
                    ON pairing_requests(status, expires_at);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_name(value: str) -> str:
        name = " ".join(value.split())
        if not name or len(name) > 64:
            raise PairingError("O nome do dispositivo deve ter entre 1 e 64 caracteres.")
        if any(ord(char) < 32 for char in name):
            raise PairingError("Nome de dispositivo inválido.")
        return name

    @staticmethod
    def _normalize_scopes(scopes: list[str]) -> tuple[str, ...]:
        normalized = tuple(sorted(set(scopes)))
        if not normalized or not set(normalized).issubset(ALLOWED_DEVICE_SCOPES):
            raise PairingError("Dispositivos só podem solicitar os escopos chat e voice.")
        return normalized

    def create_request(
        self, device_name: str, scopes: list[str]
    ) -> dict[str, Any]:
        name = self._normalize_name(device_name)
        allowed = self._normalize_scopes(scopes)
        now = int(time.time())
        request_id = uuid.uuid4().hex
        code = secrets.token_urlsafe(9)
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM pairing_requests WHERE expires_at < ? OR status != 'pending'",
                (now - 3600,),
            )
            pending = connection.execute(
                "SELECT COUNT(*) FROM pairing_requests WHERE status = 'pending' AND expires_at >= ?",
                (now,),
            ).fetchone()[0]
            if pending >= 10:
                raise PairingError("Há solicitações de pareamento demais aguardando aprovação.")
            connection.execute(
                """
                INSERT INTO pairing_requests
                (id, device_name, code_hash, scopes, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (request_id, name, self._hash(code), " ".join(allowed), now,
                 now + PAIRING_REQUEST_TTL_SECONDS),
            )
        return {
            "request_id": request_id,
            "pairing_code": code,
            "expires_in_seconds": PAIRING_REQUEST_TTL_SECONDS,
            "requested_scopes": list(allowed),
            "instructions": "Confirme o código no dispositivo principal antes de aprovar.",
        }

    def list_pending(self) -> list[dict[str, Any]]:
        now = int(time.time())
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, device_name, scopes, created_at, expires_at, attempts
                FROM pairing_requests
                WHERE status = 'pending' AND expires_at >= ?
                ORDER BY created_at
                """,
                (now,),
            ).fetchall()
        return [
            {
                "request_id": row["id"],
                "device_name": row["device_name"],
                "requested_scopes": row["scopes"].split(),
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
                "attempts": row["attempts"],
            }
            for row in rows
        ]

    def approve(self, request_id: str, pairing_code: str) -> dict[str, Any]:
        now = int(time.time())
        token = secrets.token_urlsafe(32)
        device_id = uuid.uuid4().hex
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM pairing_requests WHERE id = ?",
                (request_id,),
            ).fetchone()
            if (
                row is None
                or row["status"] != "pending"
                or row["expires_at"] < now
                or row["attempts"] >= MAX_PAIRING_ATTEMPTS
            ):
                connection.rollback()
                raise PairingError("Solicitação inválida, expirada ou já utilizada.")
            supplied_hash = self._hash(pairing_code)
            if not hmac.compare_digest(row["code_hash"], supplied_hash):
                attempts = row["attempts"] + 1
                new_status = "locked" if attempts >= MAX_PAIRING_ATTEMPTS else "pending"
                connection.execute(
                    "UPDATE pairing_requests SET attempts = ?, status = ? WHERE id = ?",
                    (attempts, new_status, request_id),
                )
                connection.commit()
                raise PairingError("Código de pareamento incorreto.")
            scopes = row["scopes"]
            connection.execute(
                """
                INSERT INTO paired_devices
                (id, name, token_hash, scopes, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (device_id, row["device_name"], self._hash(token), scopes, now,
                 now + self._token_ttl),
            )
            connection.execute(
                "UPDATE pairing_requests SET status = 'approved' WHERE id = ?",
                (request_id,),
            )
            connection.commit()
        return {
            "device_id": device_id,
            "device_name": row["device_name"],
            "access_token": token,
            "token_type": "Bearer",
            "expires_at": now + self._token_ttl,
            "scopes": scopes.split(),
            "warning": "Copie o token agora. Ele não será exibido novamente.",
        }

    def authenticate(self, token: str) -> dict[str, Any] | None:
        if not token or len(token) > 256:
            return None
        now = int(time.time())
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, name, scopes, expires_at
                FROM paired_devices
                WHERE token_hash = ? AND revoked_at IS NULL AND expires_at >= ?
                """,
                (self._hash(token), now),
            ).fetchone()
        if row is None:
            return None
        return {
            "device_id": row["id"],
            "device_name": row["name"],
            "scopes": frozenset(row["scopes"].split()),
            "expires_at": row["expires_at"],
        }

    def revoke(self, device_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE paired_devices SET revoked_at = ?
                WHERE id = ? AND revoked_at IS NULL
                """,
                (int(time.time()), device_id),
            )
        return cursor.rowcount == 1

    def list_devices(self) -> list[dict[str, Any]]:
        now = int(time.time())
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, name, scopes, created_at, expires_at, revoked_at
                FROM paired_devices ORDER BY created_at DESC
                """
            ).fetchall()
        return [
            {
                "device_id": row["id"],
                "device_name": row["name"],
                "scopes": row["scopes"].split(),
                "created_at": row["created_at"],
                "expires_at": row["expires_at"],
                "revoked": row["revoked_at"] is not None or row["expires_at"] < now,
            }
            for row in rows
        ]
