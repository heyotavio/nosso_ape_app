from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import User
from .db import get_db
from .config import settings

password_hasher = PasswordHasher()
bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def make_token(user_id: int) -> str:
    exp = datetime.now(timezone.utc) + timedelta(minutes=settings().token_expiration_minutes)
    return jwt.encode({'sub': str(user_id), 'exp': exp, 'iss': 'nosso-ape'}, settings().validated_secret(), algorithm='HS256')


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(status.HTTP_401_UNAUTHORIZED, detail='Autenticacao necessaria',
                                 headers={'WWW-Authenticate': 'Bearer'})
    if not credentials or credentials.scheme.lower() != 'bearer':
        raise unauthorized
    try:
        payload = jwt.decode(credentials.credentials, settings().validated_secret(),
                             algorithms=['HS256'], issuer='nosso-ape')
        user_id = int(payload['sub'])
    except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
        raise unauthorized
    user = db.get(User, user_id)
    if not user or not user.active:
        raise unauthorized
    return user
