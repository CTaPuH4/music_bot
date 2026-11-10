import asyncio
import logging
from typing import Any, Callable, Dict, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


class TrebloAPIError(Exception):
    """Base exception for Treblo API errors."""
    pass


class TrebloCreditsError(TrebloAPIError):
    """Raised when Treblo account has insufficient credits."""
    pass


class TrebloTimeoutError(TrebloAPIError):
    """Raised when task polling times out."""
    pass


class TrebloClient:
    def __init__(
        self,
        api_key: str = settings.treblo_api_key,
        base_url: str = settings.treblo_base_url,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "TelegramMusicBot/1.0",
        }

    async def create_generation(
        self,
        prompt: str,
        instrumental: bool = False,
        lyrics: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> str:
        """
        Create a music generation task using Treblo Melodia v3.
        Returns task_id.
        """
        url = f"{self.base_url}/generations/v3"
        payload: Dict[str, Any] = {
            "prompt": prompt,
            "instrumental": instrumental,
        }
        if lyrics:
            payload["lyrics"] = lyrics
        if tags:
            payload["tags"] = tags

        logger.info(
            "Sending Treblo generation request: prompt='%s', instrumental=%s",
            prompt[:50],
            instrumental,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(url, headers=self._headers, json=payload)
            except httpx.RequestError as exc:
                logger.error("HTTP network error contacting music generation service: %s", exc)
                raise TrebloAPIError("Ошибка соединения с сервисом генерации музыки.") from exc

            if response.status_code == 401:
                logger.error("Invalid API Key for generation service: %s", response.text)
                raise TrebloAPIError("Ошибка авторизации сервиса генерации.")

            if response.status_code == 402:
                logger.error("Generation credits exhausted: %s", response.text)
                raise TrebloCreditsError("Недостаточно кредитов сервиса генерации.")

            # If service rejects arbitrary tags with 422, retry immediately without tags
            if response.status_code == 422 and "tags" in response.text.lower() and "tags" in payload:
                logger.warning(
                    "Generation service returned 422 on tags (%s). Retrying generation without tags parameter...",
                    response.text,
                )
                retry_payload = {k: v for k, v in payload.items() if k != "tags"}
                response = await client.post(url, headers=self._headers, json=retry_payload)

            if response.status_code >= 400:
                logger.error(
                    "Generation service API error [%s]: %s", response.status_code, response.text
                )
                try:
                    err_json = response.json()
                    detail = err_json.get("detail") or err_json.get("message") or response.text
                except Exception:
                    detail = response.text
                raise TrebloAPIError(f"Ошибка сервиса генерации ({response.status_code}): {detail}")

            data = response.json()
            task_id = data.get("task_id")
            if not task_id:
                raise TrebloAPIError(f"В ответе сервиса отсутствует task_id: {data}")

            logger.info("Generation task created successfully: %s", task_id)
            return task_id

    async def get_status(self, task_id: str) -> str:
        """
        Check task status. Returns e.g. 'PENDING', 'GENERATING', 'SUCCESS', 'FAILURE'.
        """
        url = f"{self.base_url}/generations/status/{task_id}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(url, headers=self._headers)
            except httpx.RequestError as exc:
                logger.warning("Error fetching task status %s: %s", task_id, exc)
                return "PENDING"

            if response.status_code >= 400:
                logger.warning("Status check returned %s: %s", response.status_code, response.text)
                return "PENDING"

            try:
                data = response.json()
                if isinstance(data, str):
                    return data.upper()
                if isinstance(data, dict):
                    return str(data.get("status", "PENDING")).upper()
            except Exception:
                text = response.text.strip().strip('"').upper()
                return text or "PENDING"

            return "PENDING"

    async def get_generation(self, task_id: str) -> Dict[str, Any]:
        """
        Fetch completed generation metadata including audio_url, image_url, etc.
        """
        url = f"{self.base_url}/generations/{task_id}"

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(url, headers=self._headers)
            except httpx.RequestError as exc:
                raise TrebloAPIError(f"Ошибка при получении трека: {exc}") from exc

            if response.status_code >= 400:
                raise TrebloAPIError(
                    f"Не удалось получить данные трека ({response.status_code}): {response.text}"
                )

            data = response.json()
            if isinstance(data, dict):
                # Normalize audio_url from song_paths if missing
                if not data.get("audio_url"):
                    paths = data.get("song_paths") or data.get("audio_paths")
                    if isinstance(paths, list) and len(paths) > 0 and isinstance(paths[0], str):
                        data["audio_url"] = paths[0]
                # Normalize image_url if missing
                if not data.get("image_url"):
                    img_paths = data.get("image_paths") or data.get("cover_paths")
                    if isinstance(img_paths, list) and len(img_paths) > 0 and isinstance(img_paths[0], str):
                        data["image_url"] = img_paths[0]
                    elif data.get("image_path"):
                        data["image_url"] = data["image_path"]
            return data

    async def get_account_balance(self) -> Dict[str, Any]:
        """
        Get remaining credit balance on the Treblo account.
        """
        url = f"{self.base_url}/credits/balance"

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                response = await client.get(url, headers=self._headers)
                if response.status_code == 200:
                    return response.json()
                return {"error": response.text, "status_code": response.status_code}
            except Exception as exc:
                return {"error": str(exc)}

    async def poll_until_complete(
        self,
        task_id: str,
        timeout: int = settings.generation_timeout_sec,
        poll_interval: float = settings.polling_interval_sec,
        status_callback: Optional[Callable[[str], Any]] = None,
    ) -> Dict[str, Any]:
        """
        Polls the status endpoint until SUCCESS or FAILURE.
        Calls status_callback(status) if provided.
        Returns the finalized generation dictionary.
        """
        elapsed = 0.0
        last_status = None

        while elapsed < timeout:
            status = await self.get_status(task_id)

            if status != last_status:
                last_status = status
                logger.info("Task %s status changed to: %s", task_id, status)
                if status_callback:
                    try:
                        res = status_callback(status)
                        if asyncio.iscoroutine(res):
                            await res
                    except Exception as e:
                        logger.warning("Error in status_callback: %s", e)

            if status == "SUCCESS":
                return await self.get_generation(task_id)
            elif status in ("FAILURE", "FAILED", "ERROR"):
                raise TrebloAPIError("Генерация музыки завершилась ошибкой со стороны сервера нейросети.")

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval

        raise TrebloTimeoutError(f"Превышено время ожидания генерации ({timeout} сек).")


treblo_client = TrebloClient()
