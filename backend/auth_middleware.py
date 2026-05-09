# backend/middleware/auth_middleware.py
"""
FastAPI dependency injection for authentication.
Provides get_current_user and get_current_device for route protection.
"""
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.models import Device, User
from services.auth_service import decode_access_token, verify_api_token

logger = structlog.get_logger(__name__)
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency: validates JWT and returns the current user.
    Use this for all dashboard/web API endpoints.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token = credentials.credentials
    payload = decode_access_token(token)

    if not payload:
        raise credentials_exception

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception

    # Fetch user from database
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated",
        )

    # Check if account is locked
    if user.locked_until and user.locked_until > datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is temporarily locked",
        )

    return user


async def get_current_device(
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: AsyncSession = Depends(get_db),
) -> Device:
    """
    FastAPI dependency: validates device API token.
    Use this for Android app endpoints (location updates, status, etc.)
    """
    token = credentials.credentials

    # Device tokens start with "dm_"
    if not token.startswith("dm_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid device token format",
        )

    # Find all active devices and check token
    # (In production, use a hash index for performance)
    result = await db.execute(
        select(Device).where(
            Device.is_active == True,
            Device.api_token_hash.isnot(None),
        )
    )
    devices = result.scalars().all()

    authenticated_device = None
    for device in devices:
        if device.api_token_hash and verify_api_token(token, device.api_token_hash):
            authenticated_device = device
            break

    if not authenticated_device:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired device token",
        )

    # Update last seen
    authenticated_device.last_seen_at = datetime.now(timezone.utc)

    return authenticated_device