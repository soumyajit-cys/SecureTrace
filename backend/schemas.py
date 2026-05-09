# backend/models/schemas.py
"""
Pydantic v2 schemas for request validation and response serialization.
These define the API contract — what clients send and receive.
"""
import uuid
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, Field, field_validator


# ============================================================
# AUTH SCHEMAS
# ============================================================

class SendOTPRequest(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=15, pattern=r"^\+?[1-9]\d{9,14}$")
    purpose: str = Field(default="login", pattern="^(login|device_register)$")

    @field_validator("phone_number")
    @classmethod
    def normalize_phone(cls, v: str) -> str:
        # Remove spaces and dashes
        return v.replace(" ", "").replace("-", "")


class VerifyOTPRequest(BaseModel):
    phone_number: str
    otp: str = Field(..., min_length=4, max_length=8, pattern=r"^\d+$")
    purpose: str = Field(default="login")


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int  # seconds
    user: "UserResponse"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


# ============================================================
# USER SCHEMAS
# ============================================================

class UserResponse(BaseModel):
    id: uuid.UUID
    phone_number: str
    display_name: Optional[str]
    email: Optional[str]
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UpdateUserRequest(BaseModel):
    display_name: Optional[str] = Field(None, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    timezone: Optional[str] = Field(None, max_length=50)
    notification_enabled: Optional[bool] = None


# ============================================================
# DEVICE SCHEMAS
# ============================================================

class DeviceRegistrationRequest(BaseModel):
    """Sent by Android app during first-time registration."""
    device_name: str = Field(..., min_length=1, max_length=100)
    device_model: Optional[str] = Field(None, max_length=100)
    device_brand: Optional[str] = Field(None, max_length=100)
    android_version: Optional[str] = Field(None, max_length=20)
    sdk_version: Optional[int] = None
    device_fingerprint: str = Field(..., min_length=16, max_length=255)
    registration_token: Optional[str] = Field(None, max_length=512)  # FCM token
    # REQUIRED: Owner must explicitly consent to tracking
    owner_consent: bool = Field(..., description="Owner must explicitly consent to tracking")
    otp_session_id: str = Field(..., description="OTP session ID proving owner identity")


class DeviceRegistrationResponse(BaseModel):
    device_id: uuid.UUID
    api_token: str  # Returned ONCE — device must store securely
    message: str


class DeviceResponse(BaseModel):
    id: uuid.UUID
    device_name: str
    device_model: Optional[str]
    device_brand: Optional[str]
    android_version: Optional[str]
    is_active: bool
    is_lost_mode: bool
    lost_mode_message: Optional[str]
    last_seen_at: Optional[datetime]
    last_location_at: Optional[datetime]
    online_status: str
    registered_at: datetime
    tracking_enabled: bool
    # Latest location (if available)
    latest_location: Optional["LocationResponse"] = None
    latest_status: Optional["DeviceStatusResponse"] = None

    model_config = {"from_attributes": True}


# ============================================================
# LOCATION SCHEMAS
# ============================================================

class LocationUpdateRequest(BaseModel):
    """Sent by Android app to report GPS location."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    altitude: Optional[float] = None
    accuracy: Optional[float] = Field(None, ge=0, description="Accuracy in meters")
    speed: Optional[float] = Field(None, ge=0, description="Speed in m/s")
    bearing: Optional[float] = Field(None, ge=0, le=360)
    provider: Optional[str] = Field(None, max_length=30)
    is_mock: bool = Field(default=False)
    recorded_at: datetime


class LocationResponse(BaseModel):
    id: int
    latitude: float
    longitude: float
    altitude: Optional[float]
    accuracy: Optional[float]
    speed: Optional[float]
    provider: Optional[str]
    is_mock: bool
    recorded_at: datetime
    received_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# DEVICE STATUS SCHEMAS
# ============================================================

class DeviceStatusRequest(BaseModel):
    """Sent by Android app to report device telemetry."""
    battery_level: Optional[int] = Field(None, ge=0, le=100)
    battery_charging: Optional[bool] = None
    battery_temp: Optional[float] = None
    ram_total_mb: Optional[int] = Field(None, ge=0)
    ram_available_mb: Optional[int] = Field(None, ge=0)
    storage_total_gb: Optional[float] = Field(None, ge=0)
    storage_available_gb: Optional[float] = Field(None, ge=0)
    network_type: Optional[str] = Field(None, max_length=20)
    wifi_ssid: Optional[str] = Field(None, max_length=100)
    signal_strength: Optional[int] = None
    is_roaming: Optional[bool] = None
    cpu_usage: Optional[float] = Field(None, ge=0, le=100)
    screen_on: Optional[bool] = None
    recorded_at: datetime


class DeviceStatusResponse(BaseModel):
    battery_level: Optional[int]
    battery_charging: Optional[bool]
    ram_total_mb: Optional[int]
    ram_available_mb: Optional[int]
    storage_total_gb: Optional[float]
    storage_available_gb: Optional[float]
    network_type: Optional[str]
    wifi_ssid: Optional[str]
    signal_strength: Optional[int]
    cpu_usage: Optional[float]
    screen_on: Optional[bool]
    recorded_at: datetime

    model_config = {"from_attributes": True}


# ============================================================
# COMMAND SCHEMAS
# ============================================================

VALID_COMMANDS = {
    "ring": "Play a loud ringtone on the device",
    "show_message": "Display a custom message on screen",
    "lost_mode": "Activate lost mode with optional message",
    "locate": "Request immediate GPS location update",
    "high_accuracy": "Enable high-accuracy GPS mode",
    "lock_app": "Lock the device management app",
    "cancel_lost_mode": "Deactivate lost mode",
}


class RemoteCommandRequest(BaseModel):
    command_type: str = Field(..., description="Command to execute on device")
    payload: Optional[dict] = Field(None, description="Command-specific parameters")

    @field_validator("command_type")
    @classmethod
    def validate_command(cls, v: str) -> str:
        if v not in VALID_COMMANDS:
            raise ValueError(f"Invalid command. Valid commands: {list(VALID_COMMANDS.keys())}")
        return v


class RemoteCommandResponse(BaseModel):
    id: uuid.UUID
    command_type: str
    status: str
    issued_at: datetime
    delivered: bool  # Whether device received it via WebSocket

    model_config = {"from_attributes": True}


# ============================================================
# INSTALLED APPS SCHEMAS
# ============================================================

class InstalledAppItem(BaseModel):
    package_name: str
    app_name: Optional[str]
    version_name: Optional[str]
    is_system_app: bool


class InstalledAppsUpdateRequest(BaseModel):
    apps: List[InstalledAppItem]


# ============================================================
# NOTIFICATION SCHEMAS
# ============================================================

class NotificationResponse(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    message: str
    is_read: bool
    created_at: datetime
    device_id: Optional[uuid.UUID]

    model_config = {"from_attributes": True}


# ============================================================
# GENERIC RESPONSES
# ============================================================

class SuccessResponse(BaseModel):
    success: bool = True
    message: str


class ErrorResponse(BaseModel):
    success: bool = False
    error: str
    details: Optional[Any] = None


class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    per_page: int
    has_next: bool