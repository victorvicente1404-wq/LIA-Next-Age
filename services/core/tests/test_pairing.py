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

    def __init__(self):
        self.last_messages = []

    async def complete(self, messages, temperature, max_tokens):
        self.last_messages = messages
        return "Resposta local."


def test_pairing_store_approves_once_persists_hash_and_revokes(tmp_path: Path):
    store = PairingStore(tmp_path / "pairing.sqlite3")
    request = store.create_request("Celular", ["chat", "voice"])
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0]["device_name"] == "Celular"

    approved = store.approve(request["request_id"], request["pairing_code"])
    assert request["pairing_code"]
    assert set(approved["scopes"]) == {"chat", "voice"}
    assert store.authenticate(approved["device_id"])["device_id"] == approved["device_id"]
    assert request["pairing_code"].encode() not in (tmp_path / "pairing.sqlite3").read_bytes()

    with pytest.raises(PairingError):
        store.approve(request["request_id"], request["pairing_code"])

    reopened = PairingStore(tmp_path / "pairing.sqlite3")
    assert reopened.authenticate(approved["device_id"])["device_id"] == approved["device_id"]
    assert reopened.revoke(approved["device_id"]) is True
    assert reopened.authenticate(approved["device_id"]) is None
    assert reopened.revoke(approved["device_id"]) is False


def test_pairing_request_status_tracks_approval_and_revocation(tmp_path: Path):
    store = PairingStore(tmp_path / "pairing.sqlite3")
    request = store.create_request("Celular", ["chat"])
    request_id = request["request_id"]
    assert store.request_status(request_id) == "pending"

    approved = store.approve(request_id, request["pairing_code"])
    assert store.request_status(request_id) == "approved"

    assert store.revoke(approved["device_id"]) is True
    assert store.request_status(request_id) == "expired"
    assert store.request_status("0" * 32) == "expired"


def test_pairing_code_attempt_limit_locks_request(tmp_path: Path):
    store = PairingStore(tmp_path / "pairing.sqlite3")
    request = store.create_request("Tablet", ["chat"])
    for _ in range(5):
        with pytest.raises(PairingError):
            store.approve(request["request_id"], "wrong-code")
    assert store.list_pending() == []
    with pytest.raises(PairingError):
        store.approve(request["request_id"], request["pairing_code"])


def signed_headers(
    device_id: str, pairing_code: str, method: str, path: str, nonce: str
) -> dict[str, str]:
    timestamp = str(int(time.time()))
    message = f"{method.upper()}\n{path}\n{timestamp}\n{nonce}".encode()
    signing_key = hashlib.sha256(pairing_code.encode()).digest()
    signature = hmac.new(signing_key, message, hashlib.sha256).hexdigest()
    return {
        "X-Lia-Device-ID": device_id,
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
        allowed_origins=("https://lia.test", "http://localhost:5173"),
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
    assert request.headers["cache-control"] == "no-store"
    assert request.json()["expires_in_seconds"] == 300


def test_remote_device_can_check_only_its_pairing_request_status(tmp_path: Path):
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
        json={"device_name": "Celular", "scopes": ["chat", "voice"]},
    )
    request_id = created.json()["request_id"]

    pending = remote.get(
        f"/api/v1/pairing/requests/{request_id}/status",
        headers={"Origin": "https://lia.test"},
    )
    assert pending.status_code == 200
    assert pending.json() == {"status": "pending"}
    assert pending.headers["cache-control"] == "no-store"
    untrusted = remote.get(
        f"/api/v1/pairing/requests/{request_id}/status",
        headers={"Origin": "https://evil.test"},
    )
    assert untrusted.status_code == 403

    approved = local.post(
        f"/api/v1/pairing/requests/{request_id}/approve",
        json={"pairing_code": created.json()["pairing_code"]},
    )
    assert approved.status_code == 200
    status_response = remote.get(
        f"/api/v1/pairing/requests/{request_id}/status",
        headers={"Origin": "https://lia.test"},
    )
    assert status_response.json() == {"status": "approved"}

    assert local.delete(
        f"/api/v1/pairing/devices/{request_id}"
    ).status_code == 204
    revoked_status = remote.get(
        f"/api/v1/pairing/requests/{request_id}/status",
        headers={"Origin": "https://lia.test"},
    )
    assert revoked_status.json() == {"status": "expired"}

    wrong_scheme = TestClient(
        app, base_url="http://lia.test", client=("192.168.1.20", 45000)
    )
    blocked = wrong_scheme.get(
        f"/api/v1/pairing/requests/{request_id}/status",
        headers={"Origin": "https://lia.test"},
    )
    assert blocked.status_code == 403


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

    pending = local.get(
        "/api/v1/pairing/requests",
        headers={"Origin": "http://localhost:5173"},
    )
    assert pending.status_code == 200
    local.post(
        "/api/v1/memories",
        json={"kind": "note", "content": "private note only for the owner"},
    )
    approved = local.post(
        f"/api/v1/pairing/requests/{created['request_id']}/approve",
        json={"pairing_code": created["pairing_code"]},
    )
    assert approved.status_code == 200
    assert approved.headers["cache-control"] == "no-store"
    assert "access_token" not in approved.json()
    token = created["pairing_code"]
    device_id = approved.json()["device_id"]

    path = "/api/v1/chat"
    headers = signed_headers(device_id, token, "POST", path, "nonce-123456789012")
    payload = {"messages": [{"role": "user", "content": "Oi"}]}
    first = remote.post(path, headers=headers, json=payload)
    assert first.status_code == 200
    assert all(
        "private note only for the owner" not in item["content"]
        for item in app.state.inference.last_messages
    )
    replay = remote.post(path, headers=headers, json=payload)
    assert replay.status_code == 401

    conversation = remote.post(
        "/api/v1/conversations",
        headers=signed_headers(
            device_id, token, "POST", "/api/v1/conversations", "nonce-123456789017"
        ),
        json={"title": "Conversa do celular"},
    )
    assert conversation.status_code == 201
    conversation_path = f"/api/v1/conversations/{conversation.json()['id']}"
    delete_conversation = remote.delete(
        conversation_path,
        headers=signed_headers(
            device_id, token, "DELETE", conversation_path, "nonce-123456789018"
        ),
    )
    assert delete_conversation.status_code == 403
    no_memory_scope = remote.get(
        "/api/v1/memories",
        headers=signed_headers(device_id, token, "GET", "/api/v1/memories", "nonce-123456789013"),
    )
    assert no_memory_scope.status_code == 403

    dev_access = remote.get(
        "/api/v1/dev/workspaces",
        headers=signed_headers(device_id, token, "GET", "/api/v1/dev/workspaces", "nonce-123456789014"),
    )
    assert dev_access.status_code == 403

    device_id = approved.json()["device_id"]
    assert local.delete(f"/api/v1/pairing/devices/{device_id}").status_code == 204
    revoked = remote.post(
        path,
        headers=signed_headers(device_id, token, "POST", path, "nonce-123456789015"),
        json=payload,
    )
    assert revoked.status_code == 401

    memory_request = remote.post(
        "/api/v1/pairing/requests",
        headers={"Origin": "https://lia.test"},
        json={"device_name": "Tablet com memória", "scopes": ["chat", "memory:read"]},
    ).json()
    memory_approval = local.post(
        f"/api/v1/pairing/requests/{memory_request['request_id']}/approve",
        json={"pairing_code": memory_request["pairing_code"]},
    )
    assert memory_approval.status_code == 200
    assert "access_token" not in memory_approval.json()
    memory_response = remote.get(
        "/api/v1/memories",
        headers=signed_headers(
            memory_approval.json()["device_id"],
            memory_request["pairing_code"],
            "GET",
            "/api/v1/memories",
            "nonce-123456789016",
        ),
    )
    assert memory_response.status_code == 200


def test_pairing_admin_endpoints_are_loopback_only(tmp_path: Path):
    app = build_pairing_app(tmp_path)
    remote = TestClient(
        app, base_url="https://lia.test", client=("192.168.1.20", 45000)
    )
    assert remote.get(
        "/api/v1/pairing/requests", headers={"Origin": "https://lia.test"}
    ).status_code == 403


def test_remote_api_stays_closed_when_pairing_is_disabled(tmp_path: Path):
    settings = Settings(
        llm_base_url="http://127.0.0.1:8080/v1",
        llm_model="test-model",
        data_dir=tmp_path,
        runtime_backend="llama.cpp",
        pairing_enabled=False,
    )
    app = create_app(settings=settings, inference=FakeModel())
    remote = TestClient(
        app, base_url="http://lia.test", client=("192.168.1.20", 45000)
    )
    local = TestClient(
        app, base_url="http://127.0.0.1", client=("127.0.0.1", 45001)
    )

    blocked = remote.get("/api/v1/conversations")
    disabled_pairing = remote.post(
        "/api/v1/pairing/requests",
        json={"device_name": "Celular", "scopes": ["chat"]},
    )
    assert blocked.status_code == 403
    assert disabled_pairing.status_code == 403
    assert local.get("/health").status_code == 200
    assert local.get("/api/v1/conversations").status_code == 200
    local_origin = local.get(
        "/api/v1/conversations",
        headers={"Origin": "http://localhost:5173"},
    )
    hostile_origin = local.get(
        "/api/v1/conversations",
        headers={"Origin": "https://evil.test"},
    )
    assert local_origin.status_code == 200
    assert hostile_origin.status_code == 403
    local_pairing = local.get(
        "/api/v1/pairing/requests",
        headers={"Origin": "http://localhost:5173"},
    )
    assert local_pairing.status_code == 200
    assert local_pairing.json() == []


def test_untrusted_browser_origin_cannot_use_local_admin_routes(tmp_path: Path):
    app = build_pairing_app(tmp_path)
    local = TestClient(
        app, base_url="http://127.0.0.1", client=("127.0.0.1", 45001)
    )
    response = local.get(
        "/api/v1/pairing/requests",
        headers={"Origin": "https://evil.test"},
    )
    assert response.status_code == 403
