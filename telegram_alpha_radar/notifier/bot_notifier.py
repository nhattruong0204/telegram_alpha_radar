"""Send trending-token alerts via Telegram Bot API with cooldown."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import aiohttp

from telegram_alpha_radar.config import BotNotifierConfig, TrendingConfig
from telegram_alpha_radar.core.models import TrendingToken
from telegram_alpha_radar.core.utils import utcnow

logger = logging.getLogger(__name__)

_BOT_API = "https://api.telegram.org/bot{token}/sendMessage"


class BotNotifier:
    """Sends formatted alerts via Telegram Bot API to a specific chat."""

    def __init__(
        self,
        bot_config: BotNotifierConfig,
        trending_config: TrendingConfig,
        dry_run: bool = False,
    ) -> None:
        self._token = bot_config.token
        self._chat_id = bot_config.chat_id
        self._cooldown_minutes = trending_config.cooldown_minutes
        self._dry_run = dry_run
        self._session: aiohttp.ClientSession | None = None
        # contract -> last alert time
        self._cooldowns: dict[str, datetime] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def is_on_cooldown(self, contract: str) -> bool:
        last = self._cooldowns.get(contract)
        if last is None:
            return False
        elapsed = utcnow() - last
        return elapsed < timedelta(minutes=self._cooldown_minutes)

    async def _fetch_token_name(self, contract: str, chain: str) -> str:
        """Look up token name/symbol from Dexscreener. Returns '' on failure."""
        dex_chain = "solana" if chain == "solana" else "ethereum"
        url = f"https://api.dexscreener.com/latest/dex/tokens/{contract}"
        try:
            session = await self._get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return ""
                data = await resp.json()
                pairs = data.get("pairs") or []
                if pairs:
                    base = pairs[0].get("baseToken", {})
                    name = base.get("name", "")
                    symbol = base.get("symbol", "")
                    if symbol and name:
                        return f"{name} ({symbol})"
                    return symbol or name or ""
        except Exception:
            logger.debug("Failed to fetch token name for %s", contract[:12])
        return ""

    async def notify(self, tokens: list[TrendingToken]) -> int:
        """Send alerts for tokens not on cooldown. Returns count sent."""
        sent = 0

        for token in tokens:
            if self.is_on_cooldown(token.contract):
                logger.debug("Skipping %s — on cooldown", token.contract[:12])
                continue

            token_name = await self._fetch_token_name(token.contract, token.chain)
            msg = self._format_alert(token, token_name)

            if self._dry_run:
                logger.info("[DRY-RUN] Would send bot alert:\n%s", msg)
            else:
                try:
                    await self._send_message(msg)
                    logger.info(
                        "Bot alert sent for %s (%s, score=%.1f)",
                        token.contract[:12],
                        token.chain,
                        token.score,
                    )
                except Exception:
                    logger.exception(
                        "Failed to send bot alert for %s",
                        token.contract[:12],
                    )
                    continue

            self._cooldowns[token.contract] = utcnow()
            sent += 1

        return sent

    async def _send_message(self, text: str) -> None:
        session = await self._get_session()
        url = _BOT_API.format(token=self._token)
        payload = {
            "chat_id": self._chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        async with session.post(url, json=payload) as resp:
            if resp.status != 200:
                body = await resp.text()
                logger.error(
                    "Bot API error %d: %s", resp.status, body
                )
                raise RuntimeError(f"Bot API {resp.status}: {body}")

    def cleanup_expired_cooldowns(self) -> int:
        now = utcnow()
        limit = timedelta(minutes=self._cooldown_minutes)
        expired = [
            k for k, v in self._cooldowns.items() if (now - v) >= limit
        ]
        for k in expired:
            del self._cooldowns[k]
        return len(expired)

    @staticmethod
    def _format_alert(token: TrendingToken, token_name: str = "") -> str:
        chain_display = token.chain.upper()
        velocity_pct = (
            f"{token.velocity * 100:+.0f}%" if token.velocity else "NEW"
        )
        ca = token.contract
        links = BotNotifier._build_links(token.chain, ca)
        name_line = f"🪙 *Token:* {token_name}\n" if token_name else ""

        return (
            f"🚨 *TRENDING TOKEN DETECTED*\n"
            f"\n"
            f"🔗 *Chain:* {chain_display}\n"
            f"{name_line}"
            f"📋 *Contract:* `{ca}`\n"
            f"💬 *Mentions (5m):* {token.mention_count}\n"
            f"👥 *Unique Groups:* {token.unique_chats}\n"
            f"📈 *Velocity:* {velocity_pct}\n"
            f"⭐ *Score:* {token.score:.1f}\n"
            f"\n"
            f"🔗 {links}\n"
        )

    @staticmethod
    def _build_links(chain: str, contract: str) -> str:
        """Build chain-appropriate explorer/tool links."""
        if chain == "solana":
            return (
                f"[DS](https://dexscreener.com/solana/{contract})"
                f" | [GMGN](https://gmgn.ai/sol/token/{contract})"
                f" | [PH](https://photon-sol.tinyastro.io/en/lp/{contract})"
                f" | [AXI](https://axiom.trade/t/{contract})"
                f" | [BullX](https://bullx.io/terminal?chainId=1399811149&address={contract})"
            )
        elif chain == "evm":
            # Default to Ethereum; works for most EVM chains
            return (
                f"[DS](https://dexscreener.com/ethereum/{contract})"
                f" | [GMGN](https://gmgn.ai/eth/token/{contract})"
                f" | [DT](https://www.dextools.io/app/en/ether/pair-explorer/{contract})"
                f" | [Etherscan](https://etherscan.io/token/{contract})"
            )
        else:
            return (
                f"[DS](https://dexscreener.com/{chain}/{contract})"
                f" | [GMGN](https://gmgn.ai/{chain}/token/{contract})"
            )
