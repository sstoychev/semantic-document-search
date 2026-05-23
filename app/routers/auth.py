from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.user import LoginRequest, TokenResponse
from app.services.user_service import user_service

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticate a user and return an access token.
    TODO: generate a real JWT with python-jose.
    """
    user = user_service.authenticate(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # TODO: replace with a real JWT
    dummy_token = f"dummy-token-for-user-{user.id}"
    return TokenResponse(access_token=dummy_token)


@router.post("/logout")
def logout():
    """
    Invalidate the current session token.
    TODO: implement token blocklist or revocation.
    """
    return {"message": "Logged out successfully"}
