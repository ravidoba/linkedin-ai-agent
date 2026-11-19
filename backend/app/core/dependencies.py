
import jwt

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.database import get_db
from app.models.user import User

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            credentials.credentials,
            get_settings().JWT_SECRET_KEY,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )

        user_id = int(payload["sub"])

    except (jwt.InvalidTokenError, ValueError, TypeError, KeyError):
        raise error

    user = await db.get(User, user_id)

    if user is None:
        raise error

    return user
