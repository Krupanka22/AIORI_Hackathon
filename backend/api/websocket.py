"""
AIORI - WebSocket API
Real-time communication channel for live monitoring updates.
"""

import asyncio
import json
from typing import Set
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from loguru import logger

router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts."""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Send a message to all connected clients."""
        if not self.active_connections:
            return

        payload = json.dumps(message, default=str)
        disconnected = set()

        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                disconnected.add(connection)

        for conn in disconnected:
            self.active_connections.discard(conn)

    async def send_to(self, websocket: WebSocket, message: dict):
        """Send a message to a specific client."""
        try:
            await websocket.send_text(json.dumps(message, default=str))
        except Exception:
            self.active_connections.discard(websocket)

    @property
    def client_count(self) -> int:
        return len(self.active_connections)


# Singleton connection manager
ws_manager = ConnectionManager()


@router.websocket("/live")
async def websocket_endpoint(websocket: WebSocket):
    """
    Main WebSocket endpoint for real-time monitoring.

    Message types sent to clients:
    - device_update: Device status changes
    - connection_log: New network connection observed
    - ipv6_rotation: IPv6 address rotation event
    - alert: New security alert
    - traffic_stats: Updated traffic statistics
    - identity_resolution: Identity resolution result
    - experiment_update: Experiment status change
    - blockchain_record: New blockchain audit record
    """
    await ws_manager.connect(websocket)

    try:
        # Send initial status
        await ws_manager.send_to(websocket, {
            "type": "system",
            "event": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": "Connected to AIORI monitoring stream.",
        })

        while True:
            # Listen for client messages (heartbeat, subscriptions, etc.)
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                msg_type = message.get("type", "")

                if msg_type == "ping":
                    await ws_manager.send_to(websocket, {
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    })
                elif msg_type == "subscribe":
                    # Client can subscribe to specific event types
                    await ws_manager.send_to(websocket, {
                        "type": "subscribed",
                        "channels": message.get("channels", []),
                    })
            except json.JSONDecodeError:
                pass

    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        ws_manager.disconnect(websocket)


# Helper functions for broadcasting events from services

async def broadcast_device_update(device_id: str, status: str, data: dict = None):
    await ws_manager.broadcast({
        "type": "device_update",
        "device_id": device_id,
        "status": status,
        "data": data or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def broadcast_connection_log(log_data: dict):
    await ws_manager.broadcast({
        "type": "connection_log",
        "data": log_data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def broadcast_ipv6_rotation(device_id: str, old_addr: str, new_addr: str):
    await ws_manager.broadcast({
        "type": "ipv6_rotation",
        "device_id": device_id,
        "old_address": old_addr,
        "new_address": new_addr,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def broadcast_alert(alert_data: dict):
    await ws_manager.broadcast({
        "type": "alert",
        "data": alert_data,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def broadcast_identity_resolution(result: dict):
    await ws_manager.broadcast({
        "type": "identity_resolution",
        "data": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
