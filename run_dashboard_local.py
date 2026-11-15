import asyncio
import logging
import sys
from aiohttp import web

from config import settings
from database.db import db
from services.web_dashboard import register_dashboard_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("dashboard_local")


async def main():
    await db.init()

    app = web.Application()
    register_dashboard_routes(app)

    admin_id = settings.admin_ids_list[0] if settings.admin_ids_list else 940290714
    # Create token valid for 2 hours for comfortable local testing
    token = await db.create_magic_token(admin_id, ttl_seconds=7200)

    port = settings.dashboard_port
    local_url = f"http://localhost:{port}/auth?token={token}"

    print("\n" + "=" * 70)
    print("🚀 ЛОКАЛЬНЫЙ ВЕБ-ДАШБОРД TRIVELA MUSIC ЗАПУЩЕН!")
    print("=" * 70)
    print(f"🔑 Администратор ID: {admin_id}")
    print(f"🌐 Ссылка для быстрого входа в браузере:")
    print(f"\n   👉 {local_url}\n")
    print("Просто зажмите Ctrl и кликните по ссылке в терминале (или скопируйте в браузер).")
    print("Для остановки нажмите Ctrl + C.")
    print("=" * 70 + "\n")

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)

    try:
        await site.start()
        # Keep running
        while True:
            await asyncio.sleep(3600)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\nЛокальный сервер остановлен.")
