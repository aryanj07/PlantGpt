"""Tests for the local object store (Phase 3 plan, sub-task 2)."""

from app.modules.rag.object_store import LocalObjectStore


def test_save_and_read_round_trip(tmp_path) -> None:
    store = LocalObjectStore(root=tmp_path)

    uri = store.save(tenant_id="tenant-1", filename="sop.pdf", content=b"fake pdf bytes")

    assert store.read(uri) == b"fake pdf bytes"


def test_save_scopes_files_under_the_tenant_directory(tmp_path) -> None:
    store = LocalObjectStore(root=tmp_path)

    uri = store.save(tenant_id="tenant-1", filename="sop.pdf", content=b"data")

    assert str(tmp_path / "tenant-1") in uri


def test_two_uploads_with_the_same_filename_do_not_collide(tmp_path) -> None:
    store = LocalObjectStore(root=tmp_path)

    uri_a = store.save(tenant_id="tenant-1", filename="sop.pdf", content=b"version a")
    uri_b = store.save(tenant_id="tenant-1", filename="sop.pdf", content=b"version b")

    assert uri_a != uri_b
    assert store.read(uri_a) == b"version a"
    assert store.read(uri_b) == b"version b"
