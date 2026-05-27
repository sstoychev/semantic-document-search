from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.user import LoginRequest, TokenResponse
from app.services.user_service import authenticate_user, create_token

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """Authenticate and return a signed JWT access token."""
    result = authenticate_user(db, payload.username, payload.password)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    username, permissions, jwt_secret = result
    token = create_token(username, permissions, jwt_secret)
    return TokenResponse(access_token=token)
