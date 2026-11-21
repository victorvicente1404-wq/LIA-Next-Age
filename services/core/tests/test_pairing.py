from __future__ import annotations

import hashlib
import hmac
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lia_core.config import Settings
from lia_core.main import create_app
from lia_core.pairing import PairingError, PairingStore


class FakeModel:
    engine_name = "llama.cpp"

    async def complete(self, messages, temperature, max_tokens):
        return "Resposta local."


def test_pairing_store_approves_once_persists_hash_and_revokes(tmp_path: Path):
    store = PairingStore(tmp_path / "pairing.sqlite3")
    request = store.create_request("Celular", ["chat", "voice"])
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0]["device_name"] == "Celular"

    approved = store.approve(request["request_id"], request["pairing_code"])
    assert approved["access_token"]
    assert set(approved["scopes"]) == {"chat", "voice"}
    assert store.authenticate(approved["access_token"])["device_id"] == approved["device_id"]

    with pytest.raises(PairingError):
        store.approve(request["request_id"], request["pairing_code"])

    reopened = PairingStore(tmp_path / "pairing.sqlite3")
    assert reopened.authenticate(approved["access_token"])["device_id"] == approved["device_id"]
    assert reopened.revoke(approved["device_id"]) is True
    assert reopened.authenticate(approved["access_token"]) is None
    assert reopened.revoke(approved["device_id"]) is False


def test_pairing_code_attempt_limit_locks_request(tmp_path: Path):
    store = PairingStore(tmp_path / "pairing.sqlite3")
    request = store.create_request("Tablet", ["chat"])
    for _ in range(5):
        with pytest.raises(PairingError):
            store.approve(request["request_id"], "wrong-code")
    assert store.list_pending() == []
    with pytest.raises(PairingError):
        store.approve(request["request_id"], request["pairing_code"])


def signed_headers(token: str, method: str, path: str, nonce: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    message = "\n".join([method.upper(), path, timestamp, nonce]).encode("utf-8")
    signature = hmac.new(token.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return {
        "Authorization": f"Bearer {token}",
        "X-Lia-Timestamp": timestamp,
        "X-Lia-Nonce": nonce,
        "X-Lia-Signature": signature,
        "Origin": "https://lia.test",
    }


def build_pairing_app(tmp_path: Path):
    settings = Settings(
        llm_base_url="http://127.0.0.1:8080/v1",
        llm_model="test-model",
        data_dir=tmp_path,
        runtime_backend="llama.cpp",
        pairing_enabled=True,
        allowed_origins=("https://lia.test",),
    )
    return create_app(settings=settings, inference=FakeModel())


def test_remote_pairing_requires_https_and_trusted_origin(tmp_path: Path):
    app = build_pairing_app(tmp_path)
    http_remote = TestClient(
        app, base_url="http://lia.test", client=("192.168.1.20", 45000)
    )
    response = http_remote.post(
        "/api/v1/pairing/requests",
        json={"device_name": "Celular", "scopes": ["chat"]},
    )
    assert response.status_code == 403
    assert "HTTPS" in response.json()["detail"]

    remote = TestClient(
        app, base_url="https://lia.test", client=("192.168.1.20", 45000)
    )
    untrusted = remote.post(
        "/api/v1/pairing/requests",
        headers={"Origin": "https://evil.test"},
        json={"device_name": "Celular", "scopes": ["chat"]},
    )
    assert untrusted.status_code == 403

    request = remote.post(
        "/api/v1/pairing/requests",
        headers={"Origin": "https://lia.test"},
        json={"device_name": "Celular", "scopes": ["chat"]},
    )
    assert request.status_code == 201
    assert request.json()["expires_in_seconds"] == 300


def test_remote_api_requires_scoped_signed_token_and_nonce(tmp_path: Path):
    app = build_pairing_app(tmp_path)
    remote = TestClient(
        app, base_url="https://lia.test", client=("192.168.1.20", 45000)
    )
    local = TestClient(
        app, base_url="http://127.0.0.1", client=("127.0.0.1", 45001)
    )

    created = remote.post(
        "/api/v1/pairing/requests",
        headers={"Origin": "https://lia.test"},
        json={"device_name": "Celular", "scopes": ["chat"]},
    ).json()
    assert remote.post(
        "/api/v1/chat",
        json={"messages": [{"role": "user", "content": "Oi"}]},
    ).status_code == 401

    pending = local.get("/api/v1/pairing/requests")
    assert pending.status_code == 200
    approved = local.post(
        f"/api/v1/pairing/requests/{created['request_id']}/approve",
        json={"pairing_code": created["pairing_code"]},
    )
    assert approved.status_code == 200
    token = approved.json()["access_token"]

    path = "/api/v1/chat"
    headers = signed_headers(token, "POST", path, "nonce-123456789012")
    payload = {"messages": [{"role": "user", "content": "Oi"}]}
    first = remote.post(path, headers=headers, json=payload)
    assert first.status_code == 200
    replay = remote.post(path, headers=headers, json=payload)
    assert replay.status_code == 401

    no_memory_scope = remote.get(
        "/api/v1/memories",
        headers=signed_headers(token, "GET", "/api/v1/memories", "nonce-123456789013"),
    )
    assert no_memory_scope.status_code == 403

    dev_access = remote.get(
        "/api/v1/dev/workspaces",
        headers=signed_headers(token, "GET", "/api/v1/dev/workspaces", "nonce-123456789014"),
    )
    assert dev_access.status_code == 403

    device_id = approved.json()["device_id"]
    assert local.delete(f"/api/v1/pairing/devices/{device_id}").status_code == 204
    revoked = remote.post(
        path,
        headers=signed_headers(token, "POST", path, "nonce-123456789015"),
        json=payload,
    )
    assert revoked.status_code == 401


def test_pairing_admin_endpoints_are_loopback_only(tmp_path: Path):
    app = build_pairing_app(tmp_path)
    remote = TestClient(
        app, base_url="https://lia.test", client=("192.168.1.20", 45000)
    )
    assert remote.get(
        "/api/v1/pairing/requests", headers={"Origin": "https://lia.test"}
    ).status_code == 403
