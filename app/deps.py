"""Shared dependencies: current authenticated user."""
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import decode_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if creds is None:
        raise unauthorized
    try:
        user_id = decode_token(creds.credentials, "access")
    except jwt.ExpiredSignatureError:
        unauthorized.detail = "Token expired"
        raise unauthorized
    except (jwt.PyJWTError, ValueError):
        unauthorized.detail = "Invalid token"
        raise unauthorized
    user = db.get(User, user_id)
    if user is None:
        raise unauthorized
    return user
