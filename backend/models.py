# backend/models/models.py
"""
SQLAlchemy ORM models corresponding to the PostgreSQL schema.
These define the Python representation of our database tables.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey,
    Integer, SmallInteger, String, Text, Float, func
)
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import relationship, mapped_column, Mapped

from database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    country_code: Mapped[str] = mapped_column(String(5), default="+1")
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    email: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    failed_otp_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notification_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    # Relationships
    devices = relationship("Device", back_populates="owner", cascade="all, delete-orphan")
    otp_sessions = relationship("OtpSession", back_populates="user")
    refresh_tokens = relationship("RefreshToken", back_populates="user")
    notifications = relationship("Notification", back_populates="user")


class OtpSession(Base):
    __tablename__ = "otp_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False)
    otp_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False)  # login, device_register
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    user_agent: Mapped[Optional[str]] = mapped_column(Text)

    user = relationship("User", back_populates="otp_sessions")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_name: Mapped[str] = mapped_column(String(100), nullable=False)
    device_model: Mapped[Optional[str]] = mapped_column(String(100))
    device_brand: Mapped[Optional[str]] = mapped_column(String(100))
    android_version: Mapped[Optional[str]] = mapped_column(String(20))
    sdk_version: Mapped[Optional[int]] = mapped_column(Integer)
    device_fingerprint: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    registration_token: Mapped[Optional[str]] = mapped_column(String(512))
    api_token_hash: Mapped[Optional[str]] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_lost_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    lost_mode_message: Mapped[Optional[str]] = mapped_column(Text)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_location_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    online_status: Mapped[str] = mapped_column(String(20), default="offline")
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    consent_given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(10), default="1.0")
    tracking_enabled: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    owner = relationship("User", back_populates="devices")
    locations = relationship("DeviceLocation", back_populates="device", cascade="all, delete-orphan")
    status_logs = relationship("DeviceStatusLog", back_populates="device", cascade="all, delete-orphan")
    commands = relationship("RemoteCommand", back_populates="device", cascade="all, delete-orphan")
    installed_apps = relationship("DeviceInstalledApp", back_populates="device", cascade="all, delete-orphan")


class DeviceLocation(Base):
    __tablename__ = "device_locations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    altitude: Mapped[Optional[float]] = mapped_column(Float)
    accuracy: Mapped[Optional[float]] = mapped_column(Float)
    speed: Mapped[Optional[float]] = mapped_column(Float)
    bearing: Mapped[Optional[float]] = mapped_column(Float)
    provider: Mapped[Optional[str]] = mapped_column(String(30))
    is_mock: Mapped[bool] = mapped_column(Boolean, default=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    device = relationship("Device", back_populates="locations")


class DeviceStatusLog(Base):
    __tablename__ = "device_status_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    battery_level: Mapped[Optional[int]] = mapped_column(SmallInteger)
    battery_charging: Mapped[Optional[bool]] = mapped_column(Boolean)
    battery_temp: Mapped[Optional[float]] = mapped_column(Float)
    ram_total_mb: Mapped[Optional[int]] = mapped_column(Integer)
    ram_available_mb: Mapped[Optional[int]] = mapped_column(Integer)
    storage_total_gb: Mapped[Optional[float]] = mapped_column(Float)
    storage_available_gb: Mapped[Optional[float]] = mapped_column(Float)
    network_type: Mapped[Optional[str]] = mapped_column(String(20))
    wifi_ssid: Mapped[Optional[str]] = mapped_column(String(100))
    signal_strength: Mapped[Optional[int]] = mapped_column(SmallInteger)
    is_roaming: Mapped[Optional[bool]] = mapped_column(Boolean)
    cpu_usage: Mapped[Optional[float]] = mapped_column(Float)
    screen_on: Mapped[Optional[bool]] = mapped_column(Boolean)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    device = relationship("Device", back_populates="status_logs")


class RemoteCommand(Base):
    __tablename__ = "remote_commands"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    issued_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    command_type: Mapped[str] = mapped_column(String(50), nullable=False)
    payload: Mapped[Optional[dict]] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    result: Mapped[Optional[dict]] = mapped_column(JSONB)

    device = relationship("Device", back_populates="commands")


class DeviceInstalledApp(Base):
    __tablename__ = "device_installed_apps"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    package_name: Mapped[str] = mapped_column(String(255), nullable=False)
    app_name: Mapped[Optional[str]] = mapped_column(String(255))
    version_name: Mapped[Optional[str]] = mapped_column(String(50))
    version_code: Mapped[Optional[int]] = mapped_column(Integer)
    install_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_system_app: Mapped[bool] = mapped_column(Boolean, default=False)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    device = relationship("Device", back_populates="installed_apps")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    device_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL"))
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="notifications")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    device_info: Mapped[Optional[str]] = mapped_column(Text)
    ip_address: Mapped[Optional[str]] = mapped_column(INET)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user = relationship("User", back_populates="refresh_tokens")