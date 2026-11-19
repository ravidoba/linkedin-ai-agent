
from datetime import datetime, timedelta, timezone

import jwt
from pwdlib import PasswordHash

password_hasher = PasswordHash.recommended()

ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return password_hasher.verify(password, hashed)


def create_access_token(
    user_id: int,
    secret_key: str,
    expires_minutes: int = 60,
) -> str:
    expires = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes
    )

    return jwt.encode(
        {"sub": str(user_id), "exp": expires},
        secret_key,
        algorithm=ALGORITHM,
    )
