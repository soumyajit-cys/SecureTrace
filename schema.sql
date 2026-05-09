-- ============================================================
-- OTP Authorized Device Management System - Database Schema
-- ============================================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- USERS TABLE
-- ============================================================
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    phone_number    VARCHAR(20) UNIQUE NOT NULL,
    country_code    VARCHAR(5) NOT NULL DEFAULT '+1',
    display_name    VARCHAR(100),
    email           VARCHAR(255) UNIQUE,
    is_active       BOOLEAN DEFAULT TRUE,
    is_verified     BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ,
    -- Security fields
    failed_otp_attempts     INTEGER DEFAULT 0,
    locked_until            TIMESTAMPTZ,
    -- Preferences
    notification_enabled    BOOLEAN DEFAULT TRUE,
    timezone                VARCHAR(50) DEFAULT 'UTC'
);

CREATE INDEX idx_users_phone ON users(phone_number);

-- ============================================================
-- OTP SESSIONS TABLE
-- ============================================================
CREATE TABLE otp_sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id) ON DELETE CASCADE,
    phone_number    VARCHAR(20) NOT NULL,
    otp_hash        VARCHAR(255) NOT NULL,   -- bcrypt hashed OTP
    purpose         VARCHAR(50) NOT NULL,    -- 'login', 'device_register', 'revoke'
    is_used         BOOLEAN DEFAULT FALSE,
    attempts        INTEGER DEFAULT 0,
    max_attempts    INTEGER DEFAULT 3,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    used_at         TIMESTAMPTZ,
    ip_address      INET,
    user_agent      TEXT
);

CREATE INDEX idx_otp_phone ON otp_sessions(phone_number);
CREATE INDEX idx_otp_expires ON otp_sessions(expires_at);

-- Auto-cleanup expired OTPs
CREATE OR REPLACE FUNCTION cleanup_expired_otps() RETURNS void AS $$
BEGIN
    DELETE FROM otp_sessions WHERE expires_at < NOW() - INTERVAL '1 hour';
END;
$$ LANGUAGE plpgsql;

-- ============================================================
-- DEVICES TABLE
-- ============================================================
CREATE TABLE devices (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    owner_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_name         VARCHAR(100) NOT NULL,
    device_model        VARCHAR(100),
    device_brand        VARCHAR(100),
    android_version     VARCHAR(20),
    sdk_version         INTEGER,
    device_fingerprint  VARCHAR(255) UNIQUE NOT NULL,  -- Unique hardware identifier
    registration_token  VARCHAR(512),                   -- FCM push token
    api_token_hash      VARCHAR(255),                   -- Hashed API token for device auth
    is_active           BOOLEAN DEFAULT TRUE,
    is_lost_mode        BOOLEAN DEFAULT FALSE,
    lost_mode_message   TEXT,
    -- Status
    last_seen_at        TIMESTAMPTZ,
    last_location_at    TIMESTAMPTZ,
    online_status       VARCHAR(20) DEFAULT 'offline',  -- 'online', 'offline', 'idle'
    -- Timestamps
    registered_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    -- Security
    consent_given_at    TIMESTAMPTZ NOT NULL,           -- MUST have consent timestamp
    consent_version     VARCHAR(10) DEFAULT '1.0',
    tracking_enabled    BOOLEAN DEFAULT TRUE
);

CREATE INDEX idx_devices_owner ON devices(owner_id);
CREATE INDEX idx_devices_fingerprint ON devices(device_fingerprint);

-- ============================================================
-- DEVICE LOCATIONS TABLE
-- ============================================================
CREATE TABLE device_locations (
    id              BIGSERIAL PRIMARY KEY,
    device_id       UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    latitude        DECIMAL(10, 8) NOT NULL,
    longitude       DECIMAL(11, 8) NOT NULL,
    altitude        DECIMAL(10, 2),
    accuracy        DECIMAL(10, 2),          -- meters
    speed           DECIMAL(8, 2),           -- m/s
    bearing         DECIMAL(6, 2),           -- degrees
    provider        VARCHAR(30),             -- 'gps', 'network', 'fused'
    is_mock         BOOLEAN DEFAULT FALSE,   -- Detect mock locations
    recorded_at     TIMESTAMPTZ NOT NULL,    -- When device recorded it
    received_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_locations_device ON device_locations(device_id);
CREATE INDEX idx_locations_recorded ON device_locations(recorded_at DESC);
-- Partial index for recent data
CREATE INDEX idx_locations_recent ON device_locations(device_id, recorded_at DESC)
    WHERE recorded_at > NOW() - INTERVAL '7 days';

-- ============================================================
-- DEVICE STATUS LOGS TABLE
-- ============================================================
CREATE TABLE device_status_logs (
    id                  BIGSERIAL PRIMARY KEY,
    device_id           UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    -- Battery
    battery_level       SMALLINT,           -- 0-100
    battery_charging    BOOLEAN,
    battery_temp        DECIMAL(5, 2),      -- Celsius
    -- Memory
    ram_total_mb        INTEGER,
    ram_available_mb    INTEGER,
    -- Storage
    storage_total_gb    DECIMAL(10, 2),
    storage_available_gb DECIMAL(10, 2),
    -- Network
    network_type        VARCHAR(20),        -- 'wifi', '4g', '5g', 'none'
    wifi_ssid           VARCHAR(100),
    signal_strength     SMALLINT,           -- dBm
    is_roaming          BOOLEAN,
    -- System
    cpu_usage           DECIMAL(5, 2),
    screen_on           BOOLEAN,
    -- Timestamps
    recorded_at         TIMESTAMPTZ NOT NULL,
    received_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_status_device ON device_status_logs(device_id);
CREATE INDEX idx_status_recorded ON device_status_logs(recorded_at DESC);

-- ============================================================
-- REMOTE COMMANDS TABLE
-- ============================================================
CREATE TABLE remote_commands (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    device_id       UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    issued_by       UUID NOT NULL REFERENCES users(id),
    command_type    VARCHAR(50) NOT NULL,   -- 'ring', 'message', 'lock', 'lost_mode', 'locate'
    payload         JSONB,                  -- Command-specific data
    status          VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'delivered', 'executed', 'failed'
    issued_at       TIMESTAMPTZ DEFAULT NOW(),
    delivered_at    TIMESTAMPTZ,
    executed_at     TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ DEFAULT NOW() + INTERVAL '24 hours',
    result          JSONB                   -- Execution result from device
);

CREATE INDEX idx_commands_device ON remote_commands(device_id);
CREATE INDEX idx_commands_status ON remote_commands(status) WHERE status = 'pending';

-- ============================================================
-- INSTALLED APPS TABLE (Optional - user permission required)
-- ============================================================
CREATE TABLE device_installed_apps (
    id              BIGSERIAL PRIMARY KEY,
    device_id       UUID NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
    package_name    VARCHAR(255) NOT NULL,
    app_name        VARCHAR(255),
    version_name    VARCHAR(50),
    version_code    INTEGER,
    install_date    TIMESTAMPTZ,
    is_system_app   BOOLEAN DEFAULT FALSE,
    last_synced_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_apps_device ON device_installed_apps(device_id);

-- ============================================================
-- NOTIFICATIONS TABLE
-- ============================================================
CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_id       UUID REFERENCES devices(id) ON DELETE SET NULL,
    type            VARCHAR(50) NOT NULL,   -- 'alert', 'info', 'command', 'geofence'
    title           VARCHAR(200) NOT NULL,
    message         TEXT NOT NULL,
    is_read         BOOLEAN DEFAULT FALSE,
    data            JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_notifications_user ON notifications(user_id, is_read);

-- ============================================================
-- REFRESH TOKENS TABLE
-- ============================================================
CREATE TABLE refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      VARCHAR(255) NOT NULL UNIQUE,
    device_info     TEXT,
    ip_address      INET,
    expires_at      TIMESTAMPTZ NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    revoked_at      TIMESTAMPTZ
);

CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id);

-- ============================================================
-- AUDIT LOG TABLE
-- ============================================================
CREATE TABLE audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID REFERENCES users(id),
    device_id   UUID REFERENCES devices(id),
    action      VARCHAR(100) NOT NULL,
    details     JSONB,
    ip_address  INET,
    user_agent  TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_user ON audit_logs(user_id, created_at DESC);

-- ============================================================
-- UPDATED_AT TRIGGER
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_devices_updated_at
    BEFORE UPDATE ON devices
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();