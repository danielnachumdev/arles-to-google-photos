"""TDD: oauth identity upsert + per-owner job isolation (no cross-user leak)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.jobs.persistence.auth import (
    LOCAL_DEV_EMAIL,
    IdentityError,
    resolve_request_email,
)
from src.jobs.persistence.models import METADATA
from src.jobs.persistence.sqlalchemy_state import SqliteStateStore
from src.jobs.persistence.users import UserRecord, UserStore
from tests.support.album import AlbumTree
from tests.support.builders import JobRecordBuilder
from tests.support.waits import JobWaiter


class TestResolveRequestEmail:
    def test_prefers_x_auth_request_email(self) -> None:
        email = resolve_request_email(
            {
                "x-auth-request-email": "Alice@Example.com",
                "x-forwarded-email": "other@example.com",
            },
            app_env="cloud",
        )
        assert email == "alice@example.com"

    def test_falls_back_to_x_forwarded_email(self) -> None:
        assert (
            resolve_request_email(
                {"x-forwarded-email": "Bob@Example.com"},
                app_env="cloud",
            )
            == "bob@example.com"
        )

    def test_cloud_without_identity_raises(self) -> None:
        with pytest.raises(IdentityError):
            resolve_request_email({}, app_env="cloud")

    def test_local_without_headers_uses_dev_email(self) -> None:
        assert resolve_request_email({}, app_env="local") == LOCAL_DEV_EMAIL

    def test_local_headers_still_win(self) -> None:
        assert (
            resolve_request_email(
                {"x-auth-request-email": "dev@example.com"},
                app_env="local",
            )
            == "dev@example.com"
        )


class TestUsersTableAndUpsert:
    def test_migration_creates_users_and_owner_columns(self, tmp_path: Path) -> None:
        store = SqliteStateStore(tmp_path)
        try:
            from sqlalchemy import inspect

            inspector = inspect(store._engine)
            tables = set(inspector.get_table_names())
            assert "users" in tables
            job_cols = {c["name"] for c in inspector.get_columns("jobs")}
            event_cols = {c["name"] for c in inspector.get_columns("events")}
            assert "owner_id" in job_cols
            assert "owner_id" in event_cols
            # Hard reset: migration must not seed a fake owner row.
            assert "users" in METADATA.tables
            with store._engine.connect() as conn:
                count = conn.exec_driver_sql("SELECT COUNT(*) FROM users").scalar()
            assert count == 0
        finally:
            store.close()

    def test_migration_file_has_no_legacy_seed(self) -> None:
        path = (
            Path(__file__).resolve().parents[3]
            / "alembic"
            / "versions"
            / "002_users_owner.py"
        )
        text = path.read_text(encoding="utf-8").lower()
        assert "legacy@" not in text
        assert "00000000-0000-0000-0000-000000000000" not in text
        assert "insert into users" not in text
        assert "op.bulk_insert" not in text

    def test_user_store_upserts_by_email(self, tmp_path: Path) -> None:
        state = SqliteStateStore(tmp_path)
        try:
            users = UserStore(state)
            first = users.upsert_email("alice@example.com")
            second = users.upsert_email("Alice@Example.com")
            assert isinstance(first, UserRecord)
            assert first.id == second.id
            assert first.email == "alice@example.com"
            assert users.get(first.id).email == "alice@example.com"
        finally:
            state.close()


class TestOwnerIsolationStateStore:
    def test_list_and_get_are_scoped_to_owner(self, tmp_path: Path) -> None:
        state = SqliteStateStore(tmp_path)
        try:
            users = UserStore(state)
            alice = users.upsert_email("alice@example.com")
            bob = users.upsert_email("bob@example.com")
            state.create(
                JobRecordBuilder()
                .with_id("a1")
                .with_owner_id(alice.id)
                .with_status("done")
                .build()
            )
            state.create(
                JobRecordBuilder()
                .with_id("b1")
                .with_owner_id(bob.id)
                .with_status("done")
                .build()
            )
            assert [r.id for r in state.list_all(owner_id=alice.id)] == ["a1"]
            assert [r.id for r in state.list_all(owner_id=bob.id)] == ["b1"]
            assert state.get("a1", owner_id=alice.id).id == "a1"
            with pytest.raises(Exception):
                state.get("a1", owner_id=bob.id)
        finally:
            state.close()


class TestApiCrossUserIsolation:
    def _clients(self, tmp_path: Path) -> tuple[TestClient, TestClient]:
        # One app so both clients share JobStore memory + sqlite (true isolation).
        app = create_app(jobs_root=tmp_path / "jobs")
        alice = TestClient(app, headers={"X-Auth-Request-Email": "alice@example.com"})
        bob = TestClient(app, headers={"X-Auth-Request-Email": "bob@example.com"})
        return alice, bob

    def test_user_cannot_list_or_fetch_another_users_job(self, tmp_path: Path) -> None:
        alice, bob = self._clients(tmp_path)

        created = alice.post("/api/jobs", files=AlbumTree.mini_multipart())
        assert created.status_code == 201, created.text
        job_id = created.json()["id"]

        alice_list = alice.get("/api/jobs")
        assert alice_list.status_code == 200
        alice_ids = {j["id"] for j in alice_list.json()["jobs"]}
        assert job_id in alice_ids

        bob_list = bob.get("/api/jobs")
        assert bob_list.status_code == 200
        bob_ids = {j["id"] for j in bob_list.json()["jobs"]}
        assert job_id not in bob_ids

        bob_get = bob.get(f"/api/jobs/{job_id}")
        assert bob_get.status_code == 404
        assert bob_get.json()["detail"] == "job not found"

        alice_get = alice.get(f"/api/jobs/{job_id}")
        assert alice_get.status_code == 200
        assert alice_get.json()["id"] == job_id

    def test_user_cannot_fetch_another_users_history_or_media(self, tmp_path: Path) -> None:
        alice, bob = self._clients(tmp_path)

        created = alice.post("/api/jobs", files=AlbumTree.mini_multipart())
        assert created.status_code == 201, created.text
        job_id = created.json()["id"]
        # POST returns before parse finishes; wait for preview like other ingest tests.
        job = JobWaiter().http_status(
            alice,
            job_id,
            status="done",
            last_stages=("preview_ready", "done"),
        )
        item_id = job["preview"]["items"][0]["id"]

        bob_history = bob.get(f"/api/jobs/{job_id}/history")
        assert bob_history.status_code == 404
        assert bob_history.json()["detail"] == "job not found"

        bob_media = bob.get(f"/api/jobs/{job_id}/media/{item_id}")
        assert bob_media.status_code == 404
        assert bob_media.json()["detail"] == "job not found"

        alice_history = alice.get(f"/api/jobs/{job_id}/history")
        assert alice_history.status_code == 200

        alice_media = alice.get(f"/api/jobs/{job_id}/media/{item_id}")
        assert alice_media.status_code == 200

    def test_local_without_headers_still_works(self, tmp_path: Path) -> None:
        app = create_app(jobs_root=tmp_path / "jobs")
        client = TestClient(app)
        response = client.get("/api/jobs")
        assert response.status_code == 200
        assert "jobs" in response.json()
