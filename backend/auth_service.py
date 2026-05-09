# backend/services/auth_service.py
"""
Authentication service handling:
- OTP generation, hashing, verification
- JWT token creation and validation
- Password/token hashing utilities
- Session management
"""
import hashlib
import hmac
import random
import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from models.models import OtpSession, RefreshToken, User

settings = get_settings()

# bcrypt context for hashing OTPs and tokens
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ============================================================
# OTP UTILITIES
# ============================================================

def generate_otp(length: int = 6) -> str:
    """
    Generate a cryptographically secure numeric OTP.
    Uses secrets module for true randomness.
    """
    return "".join(secrets.choice(string.digits) for _ in range(length))


def hash_otp(otp: str) -> str:
    """Hash OTP using bcrypt before storing in database."""
    return pwd_context.hash(otp)


def verify_otp_hash(plain_otp: str, hashed_otp: str) -> bool:
    """Verify a plain OTP against its bcrypt hash."""
    return pwd_context.verify(plain_otp, hashed_otp)


async def create_otp_session(
    db: AsyncSession,
    phone_number: str,
    purpose: str,
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> tuple[str, OtpSession]:
    """
    Create a new OTP session:
    1. Generate OTP
    2. Hash it for secure storage
    3. Store session in database
    4. Return plain OTP (to be sent via SMS) and session
    """
    # Invalidate any existing unused OTPs for this phone/purpose
    await db.execute(
        update(OtpSession)
        .where(
            and_(
                OtpSession.phone_number == phone_number,
                OtpSession.purpose == purpose,
                OtpSession.is_used == False,
            )
        )
        .values(is_used=True)
    )

    # Generate fresh OTP
    plain_otp = generate_otp(settings.otp_length)
    otp_hash = hash_otp(plain_otp)

    # Calculate expiry
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=settings.otp_expiry_minutes)

    # Create session record
    session = OtpSession(
        user_id=user_id,
        phone_number=phone_number,
        otp_hash=otp_hash,
        purpose=purpose,
        expires_at=expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(session)
    await db.flush()  # Get the ID without committing

    return plain_otp, session


async def verify_otp_session(
    db: AsyncSession,
    phone_number: str,
    plain_otp: str,
    purpose: str,
) -> tuple[bool, str, Optional[OtpSession]]:
    """
    Verify an OTP:
    Returns: (success, message, session)
    """
    now = datetime.now(timezone.utc)

    # Find the most recent valid session
    result = await db.execute(
        select(OtpSession)
        .where(
            and_(
                OtpSession.phone_number == phone_number,
                OtpSession.purpose == purpose,
                OtpSession.is_used == False,
                OtpSession.expires_at > now,
            )
        )
        .order_by(OtpSession.created_at.desc())
        .limit(1)
    )
    session = result.scalar_one_or_none()

    if not session:
        return False, "OTP not found or expired. Please request a new one.", None

    # Check attempt limit
    if session.attempts >= session.max_attempts:
        session.is_used = True
        return False, "Too many failed attempts. Please request a new OTP.", None

    # Increment attempt counter
    session.attempts += 1

    # Verify the OTP
    if not verify_otp_hash(plain_otp, session.otp_hash):
        remaining = session.max_attempts - session.attempts
        return False, f"Invalid OTP. {remaining} attempts remaining.", None

    # Mark as used
    session.is_used = True
    session.used_at = now

    return True, "OTP verified successfully.", session


# ============================================================
# JWT TOKEN UTILITIES
# ============================================================

def create_access_token(
    user_id: str,
    phone_number: str,
    additional_claims: dict = None,
) -> str:
    """
    Create a short-lived JWT access token.
    Contains: user_id, phone, expiry, token type.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)

    payload = {
        "sub": str(user_id),          # Subject (user ID)
        "phone": phone_number,
        "type": "access",
        "iat": now,                    # Issued at
        "exp": expire,                 # Expiry
        "jti": secrets.token_hex(16), # JWT ID (unique per token)
    }

    if additional_claims:
        payload.update(additional_claims)

    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token() -> str:
    """
    Generate a secure opaque refresh token.
    NOT a JWT — stored hashed in database.
    """
    return secrets.token_urlsafe(64)


def hash_token(token: str) -> str:
    """Hash a token using SHA-256 for database storage."""
    return hashlib.sha256(token.encode()).hexdigest()


async def create_refresh_token_session(
    db: AsyncSession,
    user_id: str,
    device_info: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> str:
    """Create and store a refresh token session."""
    plain_token = create_refresh_token()
    token_hash = hash_token(plain_token)

    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)

    refresh_session = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        device_info=device_info,
        ip_address=ip_address,
        expires_at=expires_at,
    )
    db.add(refresh_session)
    await db.flush()

    return plain_token


def decode_access_token(token: str) -> Optional[dict]:
    """
    Decode and validate a JWT access token.
    Returns payload dict on success, None on failure.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        # Verify token type
        if payload.get("type") != "access":
            return None
        return payload
    except JWTError:
        return None


async def revoke_refresh_token(db: AsyncSession, plain_token: str) -> bool:
    """Revoke a refresh token (logout)."""
    token_hash = hash_token(plain_token)
    now = datetime.now(timezone.utc)

    result = await db.execute(
        update(RefreshToken)
        .where(
            and_(
                RefreshToken.token_hash == token_hash,
                RefreshToken.revoked_at.is_(None),
            )
        )
        .values(revoked_at=now)
    )
    return result.rowcount > 0


# ============================================================
# DEVICE API TOKEN
# ============================================================

def generate_device_api_token() -> str:
    """Generate a secure API token for device authentication."""
    return f"dm_{secrets.token_urlsafe(48)}"


def hash_api_token(token: str) -> str:
    """Hash device API token for storage."""
    return hashlib.sha256(token.encode()).hexdigest()


def verify_api_token(plain_token: str, hashed_token: str) -> bool:
    """Verify device API token using constant-time comparison."""
    expected_hash = hash_api_token(plain_token)
    return hmac.compare_digest(expected_hash, hashed_token)