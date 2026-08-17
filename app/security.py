# app/security.py
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AdminUser

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# auto_error=False：缺少/错误凭据时由我们自己抛 401，且不返回
# WWW-Authenticate 头，避免浏览器劫持弹出原生登录框（页面用 fetch 自行处理）。
basic = HTTPBasic(auto_error=False)


def hash_password(raw: str) -> str:
    return pwd_context.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    return pwd_context.verify(raw, hashed)


def ensure_seed_admin(db: Session, username: str, password: str) -> None:
    existing = db.query(AdminUser).filter_by(username=username).first()
    if existing is None:
        db.add(AdminUser(username=username, password_hash=hash_password(password), role="ops"))
        db.commit()


def require_admin(
    credentials: Optional[HTTPBasicCredentials] = Depends(basic),
    db: Session = Depends(get_db),
) -> AdminUser:
    user = (
        db.query(AdminUser).filter_by(username=credentials.username).first()
        if credentials is not None
        else None
    )
    if user is None or not verify_password(credentials.password, user.password_hash):
        # 不返回 WWW-Authenticate，避免浏览器弹出原生 Basic 登录框。
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )
    return user


def require_csr(user: AdminUser = Depends(require_admin)) -> AdminUser:
    # ops 也可执行核销；如需收紧改为 role == "csr"
    if user.role not in ("ops", "csr"):
        raise HTTPException(status_code=403, detail="forbidden")
    return user
