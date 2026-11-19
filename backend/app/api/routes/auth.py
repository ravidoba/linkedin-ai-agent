from app.core.dependencies import get_current_user
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
)
from app.db.database import get_db
from app.models.user import User
from app.schemas.auth import (
    UserRegister,
    UserResponse,
    UserLogin,
    TokenResponse,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=201,
)
async def register(
    data: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    email = str(data.email).lower()

    existing = await db.scalar(
        select(User).where(User.email == email)
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Email already registered",
        )

    user = User(
        full_name=data.full_name,
        email=email,
        password_hash=hash_password(data.password),
    )

    db.add(user)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        from sqlalchemy.exc import IntegrityError
        if isinstance(exc, IntegrityError):
            raise HTTPException(
                status_code=409,
                detail="Email already registered",
            ) from exc
        raise

    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    data: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    email = str(data.email).lower()

    user = await db.scalar(
        select(User).where(User.email == email)
    )

    if not user or not verify_password(
        data.password, user.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password",
        )

    settings = get_settings()

    token = create_access_token(
        user_id=user.id,
        secret_key=settings.JWT_SECRET_KEY,
    )

    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    return current_user
