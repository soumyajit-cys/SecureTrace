# backend/services/websocket_manager.py
"""
WebSocket connection manager for real-time communication.

Handles:
- Dashboard clients (browser connections) - owners monitoring devices
- Device clients (Android app connections) - devices reporting data
- Broadcasting updates from devices to dashboard
- Delivering remote commands to devices
"""
import json
import asyncio
from datetime import datetime, timezone
from typing import Dict, Set, Optional
from uuid import UUID

import structlog
from fastapi import WebSocket, WebSocketDisconnect

logger = structlog.get_logger(__name__)


class ConnectionManager:
    """
    Manages all WebSocket connections.

    Architecture:
    - dashboard_connections: { user_id -> set of WebSocket connections }
    - device_connections: { device_id -> WebSocket connection }
    """

    def __init__(self):
        # Dashboard clients: user_id -> {websocket, ...}
        self.dashboard_connections: Dict[str, Set[WebSocket]] = {}
        # Device clients: device_id -> websocket
        self.device_connections: Dict[str, WebSocket] = {}

    # ============================================================
    # DASHBOARD CLIENT MANAGEMENT
    # ============================================================

    async def connect_dashboard(self, websocket: WebSocket, user_id: str):
        """Register a new dashboard WebSocket connection."""
        await websocket.accept()
        if user_id not in self.dashboard_connections:
            self.dashboard_connections[user_id] = set()
        self.dashboard_connections[user_id].add(websocket)
        logger.info("Dashboard client connected", user_id=user_id[:8])

    def disconnect_dashboard(self, websocket: WebSocket, user_id: str):
        """Remove a dashboard connection."""
        if user_id in self.dashboard_connections:
            self.dashboard_connections[user_id].discard(websocket)
            if not self.dashboard_connections[user_id]:
                del self.dashboard_connections[user_id]
        logger.info("Dashboard client disconnected", user_id=user_id[:8])

    async def send_to_dashboard(self, user_id: str, message: dict):
        """Send a message to all dashboard sessions for a user."""
        if user_id not in self.dashboard_connections:
            return

        dead_connections = set()
        for ws in self.dashboard_connections[user_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead_connections.add(ws)

        # Clean up dead connections
        for ws in dead_connections:
            self.dashboard_connections[user_id].discard(ws)

    # ============================================================
    # DEVICE CLIENT MANAGEMENT
    # ============================================================

    async def connect_device(self, websocket: WebSocket, device_id: str):
        """Register a device WebSocket connection."""
        await websocket.accept()
        # Disconnect existing connection for this device if any
        if device_id in self.device_connections:
            try:
                await self.device_connections[device_id].close()
            except Exception:
                pass
        self.device_connections[device_id] = websocket
        logger.info("Device connected via WebSocket", device_id=device_id[:8])

    def disconnect_device(self, device_id: str):
        """Remove a device connection."""
        if device_id in self.device_connections:
            del self.device_connections[device_id]
        logger.info("Device disconnected", device_id=device_id[:8])

    async def send_to_device(self, device_id: str, message: dict) -> bool:
        """
        Send a command/message to a specific device.
        Returns True if delivered, False if device offline.
        """
        if device_id not in self.device_connections:
            return False

        try:
            ws = self.device_connections[device_id]
            await ws.send_json(message)
            return True
        except Exception as e:
            logger.warning("Failed to send to device", device_id=device_id[:8], error=str(e))
            self.disconnect_device(device_id)
            return False

    def is_device_online(self, device_id: str) -> bool:
        """Check if a device is currently connected."""
        return device_id in self.device_connections

    # ============================================================
    # BROADCAST HELPERS
    # ============================================================

    async def broadcast_location_update(
        self,
        user_id: str,
        device_id: str,
        location_data: dict,
    ):
        """Push a location update from device to all owner dashboard sessions."""
        message = {
            "type": "location_update",
            "device_id": device_id,
            "data": location_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.send_to_dashboard(user_id, message)

    async def broadcast_status_update(
        self,
        user_id: str,
        device_id: str,
        status_data: dict,
    ):
        """Push device status (battery, network, etc.) to dashboard."""
        message = {
            "type": "status_update",
            "device_id": device_id,
            "data": status_data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self.send_to_dashboard(user_id, message)

    async def broadcast_device_online(self, user_id: str, device_id: str):
        """Notify dashboard that a device just came online."""
        await self.send_to_dashboard(user_id, {
            "type": "device_online",
            "device_id": device_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def broadcast_device_offline(self, user_id: str, device_id: str):
        """Notify dashboard that a device went offline."""
        await self.send_to_dashboard(user_id, {
            "type": "device_offline",
            "device_id": device_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    async def deliver_command(self, device_id: str, command: dict) -> bool:
        """
        Deliver a remote command to a device.
        Command format: { "command": "ring", "payload": {...}, "command_id": "..." }
        """
        message = {
            "type": "command",
            **command,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        return await self.send_to_device(device_id, message)

    # ============================================================
    # HEARTBEAT
    # ============================================================

    async def send_heartbeat(self):
        """
        Periodically ping all device connections to detect stale connections.
        Called by a background task.
        """
        dead_devices = []
        for device_id, ws in self.device_connections.items():
            try:
                await ws.send_json({"type": "ping"})
            except Exception:
                dead_devices.append(device_id)

        for device_id in dead_devices:
            self.disconnect_device(device_id)

        if dead_devices:
            logger.info("Cleaned up stale device connections", count=len(dead_devices))


# Global singleton
manager = ConnectionManager()