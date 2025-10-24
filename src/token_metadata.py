"""
Token metadata fetching (decimals, symbol) via eth_call
"""
from cachetools import TTLCache


# Function selectors
FN_SELECTOR_DECIMALS = "0x313ce567"  # decimals()
FN_SELECTOR_SYMBOL = "0x95d89b41"    # symbol()


class TokenMeta:
    """Fetch and cache token metadata"""
    
    def __init__(self, rpc):
        self.rpc = rpc
        self.decimals_cache = TTLCache(maxsize=50_000, ttl=24*3600)
        self.symbol_cache = TTLCache(maxsize=50_000, ttl=24*3600)

    async def decimals(self, token: str) -> int:
        """Get token decimals"""
        token = token.lower()
        if token in self.decimals_cache:
            return self.decimals_cache[token]
        
        try:
            raw = await self.rpc.request("eth_call", [{"to": token, "data": FN_SELECTOR_DECIMALS}, "latest"])
            d = 18
            if isinstance(raw, str) and raw.startswith("0x") and len(raw) >= 2 + 64:
                val = int(raw[-64:], 16)
                d = val if 0 <= val <= 36 else 18
        except Exception:
            d = 18
        
        self.decimals_cache[token] = d
        return d

    async def symbol(self, token: str) -> str:
        """Get token symbol"""
        token = token.lower()
        if token in self.symbol_cache:
            return self.symbol_cache[token]
        
        sym = "UNKNOWN"
        try:
            raw = await self.rpc.request("eth_call", [{"to": token, "data": FN_SELECTOR_SYMBOL}, "latest"])
            if isinstance(raw, str) and raw.startswith("0x"):
                data = bytes.fromhex(raw[2:])
                if len(data) >= 64:
                    offset = int.from_bytes(data[:32], "big")
                    if 0 < offset < len(data):
                        strlen = int.from_bytes(data[offset:offset+32], "big")
                        sbytes = data[offset+32:offset+32+strlen]
                        sym = sbytes.decode(errors="ignore").strip("\x00") or "UNKNOWN"
                    else:
                        sym = data[:32].rstrip(b"\x00").decode(errors="ignore") or "UNKNOWN"
        except Exception:
            sym = "UNKNOWN"
        
        self.symbol_cache[token] = sym
        return sym
