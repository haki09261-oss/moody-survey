# tests/test_security.py
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.database import get_db
from app.security import hash_password, require_admin, ensure_seed_admin
from app.models import AdminUser


def _app_with_protected(db_session):
    app = FastAPI()

    @app.get("/secret")
    def secret(user: AdminUser = Depends(require_admin)):
        return {"user": user.username, "role": user.role}

    app.dependency_overrides[get_db] = lambda: db_session
    return app


def test_hash_password_roundtrip():
    h = hash_password("abc123")
    from app.security import verify_password
    assert verify_password("abc123", h)
    assert not verify_password("wrong", h)


def test_require_admin_rejects_no_auth(db_session):
    app = _app_with_protected(db_session)
    client = TestClient(app)
    assert client.get("/secret").status_code == 401


def test_require_admin_accepts_valid(db_session):
    user = AdminUser(username="ops1", password_hash=hash_password("pw"), role="ops")
    db_session.add(user)
    db_session.commit()
    app = _app_with_protected(db_session)
    client = TestClient(app)
    resp = client.get("/secret", auth=("ops1", "pw"))
    assert resp.status_code == 200
    assert resp.json()["role"] == "ops"


def test_ensure_seed_admin_creates_once(db_session):
    ensure_seed_admin(db_session, "admin", "pw")
    ensure_seed_admin(db_session, "admin", "pw")
    count = db_session.query(AdminUser).filter_by(username="admin").count()
    assert count == 1
