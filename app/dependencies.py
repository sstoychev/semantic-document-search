"""FastAPI dependency factories for authentication and permission enforcement."""
from fastapi import Depends, Header, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.permissions import check_permission
from app.services.user_service import get_user_jwt_secret

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)

_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


def _decode_token(token: str, db: Session) -> dict:
    """Decode and fully verify *token*. Raises HTTP 401 on any failure."""
    try:
        # Read subject without verification so we can look up the per-user secret.
        unverified = jwt.get_unverified_claims(token)
        username: str = unverified.get("sub", "")
        if not username:
            raise _credentials_exception
    except JWTError:
        raise _credentials_exception

    jwt_secret = get_user_jwt_secret(db, username)
    if jwt_secret is None:
        raise _credentials_exception

    try:
        payload = jwt.decode(token, jwt_secret, algorithms=[settings.algorithm])
        if payload.get("sub") != username:
            raise _credentials_exception
        permissions: int = int(payload.get("permissions", 0))
    except JWTError:
        raise _credentials_exception

    return {"username": username, "permissions": permissions}


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> dict:
    """Dependency: extract and verify Bearer token from Authorization header."""
    if not token:
        raise _credentials_exception
    return _decode_token(token, db)


def get_current_user_from_header_or_query(
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """Dependency for browser-navigated endpoints (e.g. /view).

    Accepts the JWT either as a standard ``Authorization: Bearer <token>``
    header *or* as a ``?token=<jwt>`` query parameter so that links opened
    in a new browser tab can include authentication.

    Note: passing tokens in query strings leaks them into server logs and
    browser history; only use this for low-sensitivity read-only pages.
    """
    raw = token
    if not raw and authorization:
        raw = authorization.removeprefix("Bearer ").strip() or None
    if not raw:
        raise _credentials_exception
    return _decode_token(raw, db)


def require_permission(perm: int):
    """Return a FastAPI dependency that enforces *perm* bitmask."""
    def dependency(user: dict = Depends(get_current_user)) -> dict:
        if not check_permission(user["permissions"], perm):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user
    return dependency


def require_permission_view(perm: int):
    """Same as require_permission but uses header-or-query auth (for /view pages)."""
    def dependency(
        user: dict = Depends(get_current_user_from_header_or_query),
    ) -> dict:
        if not check_permission(user["permissions"], perm):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user
    return dependency
