"""User authentication and management helpers."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import cast

from jose import jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User
from app.permissions import PERM_ALL

ADMIN_USERNAME = "document-admin"


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------

def hash_password(password: str, salt: str) -> str:
    """Return SHA-256 hex digest of (password + salt)."""
    return hashlib.sha256((password + salt).encode()).hexdigest()


def _admin_password_hash() -> str:
    """Return configured admin password hash."""
    return settings.admin_password_hash


def _admin_jwt_secret() -> str:
    return _admin_password_hash() + settings.admin_jwt_salt


def _user_jwt_secret(user: User) -> str:
    password_hash = cast(str, user.password_hash)
    jwt_salt = cast(str, user.jwt_salt)
    return password_hash + jwt_salt


# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

def create_token(username: str, permissions: int, jwt_secret: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": username, "permissions": permissions, "exp": expire}
    return jwt.encode(payload, jwt_secret, algorithm=settings.algorithm)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def authenticate_user(
    db: Session, username: str, password: str
) -> tuple[str, int, str] | None:
    """Verify credentials.

    Returns ``(username, permissions, jwt_secret)`` on success, else ``None``.
    """
    if username == ADMIN_USERNAME:
        if hashlib.sha256(password.encode()).hexdigest() == _admin_password_hash():
            return (username, PERM_ALL, _admin_jwt_secret())
        return None

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        return None
    salt = cast(str, user.salt)
    password_hash = cast(str, user.password_hash)
    permissions = cast(int, user.permissions)
    if hash_password(password, salt) != password_hash:
        return None
    return (username, permissions, _user_jwt_secret(user))


def get_user_jwt_secret(db: Session, username: str) -> str | None:
    """Return the JWT signing/verifying secret for *username*, or ``None``."""
    if username == ADMIN_USERNAME:
        return _admin_jwt_secret()
    user = db.query(User).filter(User.username == username).first()
    if user is None:
        return None
    return _user_jwt_secret(user)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def create_user(
    db: Session, username: str, password: str, permissions: int = 1
) -> User:
    """Create a new user with a securely salted password."""
    salt = secrets.token_hex(16)
    jwt_salt = secrets.token_hex(16)
    user = User(
        username=username,
        password_hash=hash_password(password, salt),
        salt=salt,
        permissions=permissions,
        jwt_salt=jwt_salt,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


user_service = type("_UserService", (), {
    "create": staticmethod(create_user),
    "get_by_username": staticmethod(
        lambda db, username: db.query(User).filter(User.username == username).first()
    ),
    "authenticate": staticmethod(authenticate_user),
})()
