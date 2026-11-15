import logging
from typing import Optional, Dict, Any, List
import httpx

from config import settings

logger = logging.getLogger(__name__)


class CryptoBotError(Exception):
    """Base exception for Crypto Pay API (@CryptoBot) errors."""
    pass


class CryptoBotClient:
    """
    Async client for Crypto Pay API (@CryptoBot).
    Official documentation: https://help.cryptopay.me/crypto-pay-api
    """

    def __init__(self):
        self.timeout = 10.0

    @property
    def is_configured(self) -> bool:
        token = settings.cryptobot_api_token.strip()
        return bool(token and token != "YOUR_CRYPTOBOT_API_TOKEN")

    @property
    def base_url(self) -> str:
        if settings.cryptobot_testnet:
            return "https://testnet-pay.crypt.bot/api"
        return "https://pay.crypt.bot/api"

    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Crypto-Pay-API-Token": settings.cryptobot_api_token.strip(),
            "User-Agent": "TrivelaMusicBot/2.0",
        }

    async def get_me(self) -> Optional[Dict[str, Any]]:
        """Tests the token and returns basic information about the bot app."""
        if not self.is_configured:
            return None

        url = f"{self.base_url}/getMe"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, headers=self.headers)
                data = resp.json()
                if not data.get("ok"):
                    logger.warning("CryptoBot getMe error: %s", data.get("error"))
                    return None
                return data.get("result")
        except Exception as exc:
            logger.error("Failed to connect to CryptoBot API: %s", exc)
            return None

    async def create_invoice(
        self,
        amount: float,
        asset: str = "USDT",
        description: str = "",
        payload: str = "",
        expires_in: int = 3600,
    ) -> Dict[str, Any]:
        """
        Creates a new payment invoice in CryptoBot.
        :param amount: Amount in cryptocurrency (e.g. 5.76)
        :param asset: Cryptocurrency code: USDT, TON, BTC, ETH, LTC, BNB, TRX, USDC
        :param description: Description shown to user
        :param payload: Internal identifier (payment_id)
        :param expires_in: Time in seconds before expiration (default 1 hour)
        :return: Dict containing invoice_id, pay_url, bot_invoice_url, etc.
        """
        if not self.is_configured:
            raise CryptoBotError("CryptoBot API token is not configured in .env (CRYPTOBOT_API_TOKEN)")

        url = f"{self.base_url}/createInvoice"
        # Format amount to max 6 decimals without trailing zeroes for crypto, or 2 for USDT
        if asset in ("USDT", "USDC"):
            amount_str = f"{amount:.2f}"
        else:
            amount_str = f"{amount:.6f}".rstrip("0").rstrip(".")

        payload_data = {
            "amount": amount_str,
            "asset": asset,
            "description": description[:1024] if description else "",
            "payload": payload[:1024] if payload else "",
            "expires_in": expires_in,
            "allow_comments": False,
            "allow_anonymous": True,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, headers=self.headers, json=payload_data)
                data = resp.json()

                if not data.get("ok"):
                    err = data.get("error", {})
                    err_msg = f"CryptoBot error {err.get('code')}: {err.get('name')}"
                    logger.error("Failed to create CryptoBot invoice: %s", err_msg)
                    raise CryptoBotError(err_msg)

                res = data.get("result", {})
                logger.info(
                    "Created CryptoBot invoice #%s for %s %s (payload=%s)",
                    res.get("invoice_id"),
                    amount_str,
                    asset,
                    payload,
                )
                return res
        except httpx.RequestError as exc:
            logger.error("HTTP network error connecting to CryptoBot: %s", exc)
            raise CryptoBotError(f"Network error: {exc}")

    async def get_invoice(self, invoice_id: int | str) -> Optional[Dict[str, Any]]:
        """Fetches status of a specific invoice."""
        if not self.is_configured:
            return None

        url = f"{self.base_url}/getInvoices"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    url,
                    headers=self.headers,
                    params={"invoice_ids": str(invoice_id)},
                )
                data = resp.json()
                if not data.get("ok"):
                    return None

                items = data.get("result", {}).get("items", [])
                if items:
                    return items[0]
                return None
        except Exception as exc:
            logger.debug("Error checking CryptoBot invoice %s: %s", invoice_id, exc)
            return None

    async def get_invoices(self, invoice_ids: List[int | str]) -> List[Dict[str, Any]]:
        """Fetches batch of invoices by their IDs."""
        if not self.is_configured or not invoice_ids:
            return []

        ids_str = ",".join(str(i) for i in invoice_ids[:100])
        url = f"{self.base_url}/getInvoices"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    url,
                    headers=self.headers,
                    params={"invoice_ids": ids_str},
                )
                data = resp.json()
                if not data.get("ok"):
                    return []
                return data.get("result", {}).get("items", [])
        except Exception as exc:
            logger.debug("Error batch checking CryptoBot invoices: %s", exc)
            return []


cryptobot_client = CryptoBotClient()
