"""Exercises the Phase 0 in-memory chat flow end to end: create a
conversation, post a message, get back a (stub) assistant reply, and confirm
tenant isolation on access. This is the Phase 0 smoke test - it proves the
module wiring (Auth dev-mode -> Chat -> LLM Gateway stub) actually runs, not
just imports.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
HEADERS = {"X-Dev-Tenant-Id": "tenant-1", "X-Dev-User-Id": "user-1"}


def test_requires_dev_identity_headers() -> None:
    response = client.post("/v1/conversations")
    assert response.status_code == 401


def test_full_chat_flow() -> None:
    create_resp = client.post("/v1/conversations", headers=HEADERS)
    assert create_resp.status_code == 200
    conversation_id = create_resp.json()["id"]

    message_resp = client.post(
        f"/v1/conversations/{conversation_id}/messages",
        headers=HEADERS,
        json={"content": "What's the ideal kiln temperature for clinker production?"},
    )
    assert message_resp.status_code == 200
    messages = message_resp.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert "kiln temperature" in messages[1]["content"]

    list_resp = client.get(f"/v1/conversations/{conversation_id}/messages", headers=HEADERS)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 2


def test_tenant_isolation_on_conversation_access() -> None:
    create_resp = client.post("/v1/conversations", headers=HEADERS)
    conversation_id = create_resp.json()["id"]

    other_tenant_headers = {"X-Dev-Tenant-Id": "tenant-2", "X-Dev-User-Id": "user-2"}
    resp = client.get(f"/v1/conversations/{conversation_id}/messages", headers=other_tenant_headers)
    assert resp.status_code == 404
