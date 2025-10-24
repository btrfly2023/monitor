"""
WebSocket JSON-RPC client for blockchain monitoring
"""
import json
import ssl
from typing import Any, List, Optional

import certifi
import websockets


class RawWSRPC:
    """Raw WebSocket JSON-RPC client"""
    
    def __init__(self, url: str, ping_interval: int = 20, ping_timeout: int = 20):
        self.url = url
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self._id = 0
        self.ssl_context = ssl.create_default_context(cafile=certifi.where())

    async def connect(self):
        """Establish WebSocket connection"""
        if self.ws and not self.ws.closed:
            return
        self.ws = await websockets.connect(
            self.url,
            ssl=self.ssl_context,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout
        )

    async def close(self):
        """Close WebSocket connection"""
        if self.ws and not self.ws.closed:
            await self.ws.close()

    async def request(self, method: str, params: List[Any]) -> Any:
        """Send JSON-RPC request and wait for response"""
        await self.connect()
        self._id += 1
        req_id = self._id
        payload = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        await self.ws.send(json.dumps(payload))
        
        while True:
            msg = await self.ws.recv()
            data = json.loads(msg)
            if "id" in data and data["id"] == req_id:
                if "error" in data:
                    raise RuntimeError(f"RPC error {method}: {data['error']}")
                return data.get("result")

    async def subscribe_new_heads(self) -> str:
        """Subscribe to new block headers"""
        await self.connect()
        self._id += 1
        payload = {"jsonrpc": "2.0", "id": self._id, "method": "eth_subscribe", "params": ["newHeads"]}
        await self.ws.send(json.dumps(payload))
        
        while True:
            msg = await self.ws.recv()
            data = json.loads(msg)
            if data.get("id") == self._id:
                if "error" in data:
                    raise RuntimeError(f"Subscription error: {data['error']}")
                return data.get("result")

    async def recv(self) -> Optional[dict]:
        """Receive next WebSocket message"""
        try:
            msg = await self.ws.recv()
            return json.loads(msg)
        except Exception:
            return None
