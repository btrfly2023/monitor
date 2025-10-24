"""
WebSocket RPC client for Ethereum
"""
import json
import ssl
from typing import Any, List, Optional

import certifi
import websockets
from websockets.client import WebSocketClientProtocol


class RawWSRPC:
    """Raw JSON-RPC client over WebSockets"""
    
    def __init__(self, url: str, ping_interval: int = 20, ping_timeout: int = 20):
        self.url = url
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.ws: Optional[WebSocketClientProtocol] = None
        self._id = 0
        self.ssl_context = ssl.create_default_context(cafile=certifi.where())

    async def connect(self):
        """Connect to WebSocket endpoint"""
        # Check if already connected
        if self.ws is not None:
            try:
                # Try to check if connection is still open
                if not self.ws.closed:
                    return
            except AttributeError:
                # Fallback for older websockets versions without 'closed' attribute
                try:
                    # Try a ping to check if connection is alive
                    await self.ws.ping()
                    return
                except Exception:
                    # Connection is dead, reconnect
                    pass
        
        # Connect
        self.ws = await websockets.connect(
            self.url,
            ssl=self.ssl_context,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout
        )

    async def close(self):
        """Close WebSocket connection"""
        if self.ws is not None:
            try:
                if not self.ws.closed:
                    await self.ws.close()
            except AttributeError:
                # Fallback for older versions
                try:
                    await self.ws.close()
                except Exception:
                    pass
            finally:
                self.ws = None

    async def request(self, method: str, params: List[Any]) -> Any:
        """Send JSON-RPC request and wait for response"""
        await self.connect()
        self._id += 1
        req_id = self._id
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params
        }
        
        await self.ws.send(json.dumps(payload))
        
        while True:
            msg = await self.ws.recv()
            data = json.loads(msg)
            
            if "id" in data and data["id"] == req_id:
                if "error" in data:
                    raise RuntimeError(f"RPC error {method}: {data['error']}")
                return data.get("result")

    async def subscribe_new_heads(self) -> str:
        """Subscribe to newHeads events"""
        await self.connect()
        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._id,
            "method": "eth_subscribe",
            "params": ["newHeads"]
        }
        
        await self.ws.send(json.dumps(payload))
        
        while True:
            msg = await self.ws.recv()
            data = json.loads(msg)
            
            if data.get("id") == self._id:
                if "error" in data:
                    raise RuntimeError(f"Subscription error: {data['error']}")
                return data.get("result")

    async def recv(self) -> Optional[dict]:
        """Receive message from WebSocket"""
        try:
            msg = await self.ws.recv()
            return json.loads(msg)
        except Exception:
            return None
