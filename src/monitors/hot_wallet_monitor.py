"""
Hot Wallet Monitor - Tracks accumulated token transfers by sender/receiver
"""
import asyncio
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Dict, Tuple, Deque, Optional, List

from cachetools import TTLCache
from loguru import logger

from ..websocket_rpc import RawWSRPC
from ..token_metadata import TokenMeta


# Constants
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
WINDOWS = [60, 300]  # 1m, 5m
PRINT_EVERY_N_BLOCKS = 10
ALERT_COOLDOWN_SECONDS = 3600  # 60 minutes cooldown


# Utilities
def safe_checksum(addr: Optional[str]) -> Optional[str]:
    """Validate and return address"""
    if not addr or addr in ("0x", "0x0", "0x0000"):
        return None
    if isinstance(addr, str) and addr.startswith("0x") and len(addr) == 42:
        return addr
    return None


def short(addr: Optional[str]) -> str:
    """Shorten address for display"""
    if not addr:
        return "None"
    return f"{addr[:6]}...{addr[-4:]}"


def hex_to_int(x: str) -> int:
    """Convert hex string to int"""
    return int(x, 16)


def topic_to_address(topic_hex: str) -> Optional[str]:
    """Extract address from topic"""
    if not isinstance(topic_hex, str) or not topic_hex.startswith("0x") or len(topic_hex) != 66:
        return None
    return "0x" + topic_hex[-40:]


# Data structures
@dataclass
class TxRecord:
    ts: int
    tx_hash: str
    frm: str
    to: Optional[str]
    token_amounts: Dict[str, float]


@dataclass
class TransferEvent:
    ts: int
    sender: str
    receiver: str
    token: str
    amount: float


@dataclass
class ContractWindowState:
    records_by_window: Dict[int, Deque[TxRecord]]
    transfer_events_by_window: Dict[int, Deque[TransferEvent]]

    def __init__(self):
        self.records_by_window = {w: deque() for w in WINDOWS}
        self.transfer_events_by_window = {w: deque() for w in WINDOWS}


class AccumulatedSenderReceiverDetector:
    """Detects whale activity by tracking accumulated transfers"""
    
    def __init__(self, rpc: RawWSRPC, token_thresholds: Dict[str, float], notification_callback=None, alert_cooldown_seconds: int = ALERT_COOLDOWN_SECONDS):
        self.rpc = rpc
        self.meta = TokenMeta(rpc)
        self.token_thresholds = {k.lower(): v for k, v in token_thresholds.items()}
        self.notification_callback = notification_callback
        self.alert_cooldown_seconds = alert_cooldown_seconds
        self.contract_state: Dict[str, ContractWindowState] = defaultdict(ContractWindowState)
        self.code_cache = TTLCache(maxsize=100_000, ttl=6*3600)
        
        # Alert cooldown tracking: contract_address -> last_alert_timestamp
        self.alert_cooldowns: Dict[str, float] = {}

    def is_token_monitored(self, token: str) -> bool:
        """Check if token is being monitored"""
        return token.lower() in self.token_thresholds

    def whale_threshold_for(self, token: str) -> Optional[float]:
        """Get whale threshold for token"""
        return self.token_thresholds.get(token.lower())

    async def is_contract(self, addr: str) -> bool:
        """Check if address is a contract"""
        key = addr.lower()
        if key in self.code_cache:
            return self.code_cache[key]
        
        try:
            code_hex = await self.rpc.request("eth_getCode", [addr, "latest"])
            is_c = isinstance(code_hex, str) and code_hex not in ("0x", "0x0")
        except Exception:
            is_c = False
        
        self.code_cache[key] = is_c
        return is_c

    def is_in_cooldown(self, contract: str, current_ts: float) -> bool:
        """Check if contract is in alert cooldown period"""
        contract_key = contract.lower()
        if contract_key not in self.alert_cooldowns:
            return False
        
        last_alert_time = self.alert_cooldowns[contract_key]
        time_since_alert = current_ts - last_alert_time
        
        if time_since_alert < self.alert_cooldown_seconds:
            remaining = self.alert_cooldown_seconds - time_since_alert
            logger.debug(f"Contract {short(contract)} in cooldown, {remaining:.0f}s remaining")
            return True
        
        return False

    def set_alert_cooldown(self, contract: str, current_ts: float):
        """Set alert cooldown for a contract"""
        contract_key = contract.lower()
        self.alert_cooldowns[contract_key] = current_ts
        logger.info(f"Alert cooldown set for {short(contract)} until {current_ts + self.alert_cooldown_seconds}")

    def prune_old(self, state: ContractWindowState, current_ts: int):
        """Remove old records outside time windows"""
        for w in WINDOWS:
            dq = state.records_by_window[w]
            while dq and dq[0].ts <= current_ts - w:
                dq.popleft()
            edq = state.transfer_events_by_window[w]
            while edq and edq[0].ts <= current_ts - w:
                edq.popleft()

    def add_tx_and_events(self, contract: str, rec: TxRecord, transfer_events: List[TransferEvent]):
        """Add transaction and transfer events to tracking"""
        state = self.contract_state[contract]
        for w in WINDOWS:
            state.records_by_window[w].append(rec)
        for ev in transfer_events:
            for w in WINDOWS:
                state.transfer_events_by_window[w].append(ev)

    def compute_sender_receiver_accumulated(self, contract: str, current_ts: int):
        """Compute accumulated amounts by sender/receiver"""
        state = self.contract_state[contract]
        self.prune_old(state, current_ts)

        out = {}
        for w in WINDOWS:
            sender_sums: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
            receiver_sums: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

            for ev in state.transfer_events_by_window[w]:
                if not self.is_token_monitored(ev.token):
                    continue
                sender_sums[ev.sender][ev.token] += ev.amount
                receiver_sums[ev.receiver][ev.token] += ev.amount

            exceeds: List[Tuple[str, str, str, float, float]] = []
            for sender, tok_map in sender_sums.items():
                for tok, total_amt in tok_map.items():
                    thr = self.whale_threshold_for(tok)
                    if thr is not None and total_amt >= thr:
                        exceeds.append(("sender", sender, tok, total_amt, thr))
            
            for receiver, tok_map in receiver_sums.items():
                for tok, total_amt in tok_map.items():
                    thr = self.whale_threshold_for(tok)
                    if thr is not None and total_amt >= thr:
                        exceeds.append(("receiver", receiver, tok, total_amt, thr))

            out[w] = {
                "sender_sums": {s: dict(tmap) for s, tmap in sender_sums.items()},
                "receiver_sums": {r: dict(tmap) for r, tmap in receiver_sums.items()},
                "exceeds": exceeds,
            }
        return out

    async def maybe_alert(self, contract: str, winstats: Dict[int, Dict], current_ts: float):
        """Send alert if thresholds exceeded and not in cooldown"""
        hits = []
        for w in WINDOWS:
            for (role, addr, tok, total_amt, thr) in winstats.get(w, {}).get("exceeds", []):
                hits.append((w, role, addr, tok, total_amt, thr))
        
        if not hits:
            return

        # Check cooldown
        if self.is_in_cooldown(contract, current_ts):
            logger.debug(f"Skipping alert for {short(contract)} - in cooldown period")
            return

        # Compose alert message with full contract address
        lines = []
        for w, role, addr, tok, total_amt, thr in sorted(hits, key=lambda x: (x[0], x[1]))[:12]:
            sym = await self.meta.symbol(tok)
            lines.append(f"- {w}s: {role}={short(addr)} token={sym}({short(tok)}) window_sum={total_amt:,.4f} thr={thr:,.4f}")

        alert_msg = f"🐋 Hot Wallet Alert - Contract {contract}\n" + "\n".join(lines)
        logger.warning(f"[HOT WALLET ALERT] {alert_msg}")
        
        # Send notification via callback
        if self.notification_callback:
            try:
                await self.notification_callback(alert_msg)
                # Set cooldown after successful notification
                self.set_alert_cooldown(contract, current_ts)
            except Exception as e:
                logger.error(f"Failed to send notification: {e}")

    async def parse_transfer_events(self, receipt: dict) -> List[TransferEvent]:
        """Parse ERC-20 Transfer events from receipt"""
        events: List[TransferEvent] = []
        for log in receipt.get("logs", []):
            try:
                topics = log.get("topics", [])
                if not topics or topics[0] != TRANSFER_TOPIC:
                    continue
                
                token = safe_checksum(log.get("address"))
                if not token or not self.is_token_monitored(token):
                    continue

                sender = topic_to_address(topics[1]) if len(topics) > 1 else None
                receiver = topic_to_address(topics[2]) if len(topics) > 2 else None
                sender = safe_checksum(sender)
                receiver = safe_checksum(receiver)
                if not sender or not receiver:
                    continue

                data_field = log.get("data", "0x")
                amount_raw = int(data_field, 16) if isinstance(data_field, str) else 0
                d = await self.meta.decimals(token)
                amount = amount_raw / (10 ** d)

                events.append(TransferEvent(ts=0, sender=sender, receiver=receiver, token=token, amount=amount))
            except Exception as e:
                logger.debug(f"Error parsing transfer event: {e}")
                continue
        return events


class HotWalletMonitor:
    """Main hot wallet monitoring class"""
    
    def __init__(self, ws_url: str, token_thresholds: Dict[str, float], notification_callback=None, alert_cooldown_minutes: int = 60):
        self.ws_url = ws_url
        self.token_thresholds = token_thresholds
        self.notification_callback = notification_callback
        self.alert_cooldown_seconds = alert_cooldown_minutes * 60
        self.rpc = RawWSRPC(ws_url)
        self.detector = None
        self.running = False

    async def start(self):
        """Start monitoring"""
        logger.info(f"[HOT WALLET] Starting monitor on {self.ws_url}")
        logger.info(f"[HOT WALLET] Monitoring {len(self.token_thresholds)} tokens")
        logger.info(f"[HOT WALLET] Alert cooldown: {self.alert_cooldown_seconds / 60:.0f} minutes")

        if not self.token_thresholds:
            logger.warning("[HOT WALLET] No tokens configured for monitoring")
            return

        # Connectivity check
        try:
            netver = await self.rpc.request("net_version", [])
            chain_id_hex = await self.rpc.request("eth_chainId", [])
            latest_hex = await self.rpc.request("eth_blockNumber", [])
            chain_id = hex_to_int(chain_id_hex)
            latest = hex_to_int(latest_hex)
            logger.info(f"[HOT WALLET] Connected. net_version={netver}, chain_id={chain_id}, latest_block={latest}")
        except Exception as e:
            logger.error(f"[HOT WALLET] Connection failed: {e}")
            return

        # Subscribe to new blocks
        try:
            sub_id = await self.rpc.subscribe_new_heads()
            logger.info(f"[HOT WALLET] Subscribed to newHeads: {sub_id}")
        except Exception as e:
            logger.error(f"[HOT WALLET] Failed to subscribe: {e}")
            return

        self.detector = AccumulatedSenderReceiverDetector(
            self.rpc, 
            self.token_thresholds, 
            self.notification_callback,
            self.alert_cooldown_seconds
        )
        self.running = True
        blocks_seen = 0

        while self.running:
            data = await self.rpc.recv()
            if not data:
                logger.warning("[HOT WALLET] Empty message, reconnecting...")
                await asyncio.sleep(2)
                try:
                    await self.rpc.close()
                    await self.rpc.connect()
                    sub_id = await self.rpc.subscribe_new_heads()
                    logger.info(f"[HOT WALLET] Re-subscribed: {sub_id}")
                except Exception as e:
                    logger.error(f"[HOT WALLET] Re-subscribe failed: {e}")
                continue

            if data.get("method") != "eth_subscription":
                continue
            
            params = data.get("params", {})
            if params.get("subscription") != sub_id:
                continue
            
            header = params.get("result", {})
            blk_hash = header.get("hash")
            if not blk_hash:
                continue

            await self._process_block(blk_hash, blocks_seen)
            blocks_seen += 1

    async def _process_block(self, blk_hash: str, blocks_seen: int):
        """Process a single block"""
        t0 = time.time()
        
        try:
            block = await self.rpc.request("eth_getBlockByHash", [blk_hash, True])
        except Exception as e:
            logger.error(f"[HOT WALLET] Error fetching block: {e}")
            return

        block_num = hex_to_int(block["number"]) if isinstance(block["number"], str) else block["number"]
        block_ts = hex_to_int(block["timestamp"]) if isinstance(block["timestamp"], str) else block["timestamp"]
        txs = block.get("transactions", [])
        
        logger.debug(f"[HOT WALLET] Block #{block_num} txs={len(txs)}")

        txs_processed = 0
        for tx in txs:
            to_addr = safe_checksum(tx.get("to"))
            frm_addr = safe_checksum(tx.get("from"))
            if to_addr is None or frm_addr is None:
                continue

            # Only process contract calls
            try:
                is_contract = await self.detector.is_contract(to_addr)
            except Exception:
                is_contract = False
            if not is_contract:
                continue

            # Fetch receipt
            try:
                rcp = await self.rpc.request("eth_getTransactionReceipt", [tx["hash"]])
            except Exception:
                continue

            events = await self.detector.parse_transfer_events(rcp)
            if not events:
                continue

            # Aggregate token amounts
            token_amounts: Dict[str, float] = defaultdict(float)
            for ev in events:
                token_amounts[ev.token] += ev.amount

            tx_hash_hex = tx["hash"] if isinstance(tx["hash"], str) else tx["hash"]["hash"]
            rec = TxRecord(
                ts=block_ts,
                tx_hash=tx_hash_hex,
                frm=frm_addr,
                to=to_addr,
                token_amounts=dict(token_amounts)
            )

            # Add timestamp to events
            evs_with_ts = [
                TransferEvent(ts=block_ts, sender=e.sender, receiver=e.receiver, token=e.token, amount=e.amount)
                for e in events
            ]

            self.detector.add_tx_and_events(to_addr, rec, evs_with_ts)
            acc = self.detector.compute_sender_receiver_accumulated(to_addr, block_ts)
            # Pass current timestamp for cooldown check
            await self.detector.maybe_alert(to_addr, acc, time.time())
            txs_processed += 1

        dt_ms = (time.time() - t0) * 1000
        logger.debug(f"[HOT WALLET] Block #{block_num} processed {txs_processed}/{len(txs)} txs in {dt_ms:.1f}ms")

        if blocks_seen % PRINT_EVERY_N_BLOCKS == 0:
            logger.info(f"[HOT WALLET] Heartbeat: blocks_seen={blocks_seen}, latest=#{block_num}")

    async def stop(self):
        """Stop monitoring"""
        logger.info("[HOT WALLET] Stopping monitor")
        self.running = False
        await self.rpc.close()
