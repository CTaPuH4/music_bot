import logging
import uuid
from typing import Any, Dict, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


class YooKassaError(Exception):
    """Base exception for YooKassa API errors."""
    pass


class YooKassaClient:
    def __init__(
        self,
        shop_id: str = settings.yookassa_shop_id,
        secret_key: str = settings.yookassa_secret_key,
        base_url: str = settings.yookassa_base_url,
    ):
        self.shop_id = shop_id
        self.secret_key = secret_key
        self.base_url = base_url.rstrip("/")

    @property
    def is_configured(self) -> bool:
        return bool(self.shop_id and self.secret_key)

    async def create_payment(
        self,
        amount_rub: float,
        description: str,
        return_url: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Creates a payment in YooKassa.
        Returns the YooKassa payment object containing id, status, confirmation_url, etc.
        """
        if not self.is_configured:
            raise YooKassaError(
                "ЮKassa не настроена! Укажите YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY в .env"
            )

        url = f"{self.base_url}/payments"
        idempotence_key = str(uuid.uuid4())

        payload = {
            "amount": {
                "value": f"{amount_rub:.2f}",
                "currency": "RUB",
            },
            "confirmation": {
                "type": "redirect",
                "return_url": return_url,
            },
            "capture": True,
            "description": description,
        }
        if metadata:
            payload["metadata"] = metadata

        headers = {
            "Idempotence-Key": idempotence_key,
            "Content-Type": "application/json",
        }

        auth = (self.shop_id, self.secret_key)

        logger.info(
            "Creating YooKassa payment for amount %s RUB, idempotence=%s",
            amount_rub,
            idempotence_key,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                    auth=auth,
                )
            except httpx.RequestError as exc:
                logger.error("HTTP network error connecting to YooKassa: %s", exc)
                raise YooKassaError(f"Ошибка связи с платёжным шлюзом ЮKassa: {exc}") from exc

            if response.status_code >= 400:
                logger.error(
                    "YooKassa API error [%s]: %s",
                    response.status_code,
                    response.text,
                )
                try:
                    err_data = response.json()
                    desc = err_data.get("description") or err_data.get("code") or response.text
                except Exception:
                    desc = response.text
                raise YooKassaError(f"Ошибка ЮKassa ({response.status_code}): {desc}")

            data = response.json()
            logger.info("YooKassa payment created: id=%s, status=%s", data.get("id"), data.get("status"))
            return data

    async def get_payment(self, payment_id: str) -> Dict[str, Any]:
        """
        Fetches payment status and details from YooKassa.
        """
        if not self.is_configured:
            raise YooKassaError(
                "ЮKassa не настроена! Укажите YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY в .env"
            )

        url = f"{self.base_url}/payments/{payment_id}"
        auth = (self.shop_id, self.secret_key)

        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                response = await client.get(url, auth=auth)
            except httpx.RequestError as exc:
                logger.error("Error checking payment %s: %s", payment_id, exc)
                raise YooKassaError(f"Ошибка проверки статуса платежа: {exc}") from exc

            if response.status_code >= 400:
                logger.error("YooKassa get_payment error [%s]: %s", response.status_code, response.text)
                raise YooKassaError(f"Не удалось получить данные платежа ({response.status_code})")

            return response.json()


yookassa_client = YooKassaClient()
