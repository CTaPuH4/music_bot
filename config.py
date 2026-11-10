from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    bot_token: str = "YOUR_BOT_TOKEN"
    treblo_api_key: str = "YOUR_TREBLO_API_KEY"
    database_path: str = "bot_database.db"

    # Admin Settings
    admin_ids: str = ""
    treblo_low_credits_threshold: int = 500  # Alert admins if remaining Treblo credits < 500

    @property
    def admin_ids_list(self) -> list[int]:
        if not self.admin_ids:
            return []
        res = []
        for part in self.admin_ids.replace(";", ",").split(","):
            part = part.strip()
            if part.isdigit():
                res.append(int(part))
        return res

    # Default settings for balance & limits
    initial_user_credits: int = 3
    generation_cost: int = 1

    # YooKassa Settings
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_base_url: str = "https://api.yookassa.ru/v3"
    referral_reward_percent: int = 10  # 10% bonus to referrer upon purchase

    # Webhook server settings for YooKassa (optional, not needed if using background poller)
    webhook_enabled: bool = False
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8080
    webhook_path: str = "/webhook/yookassa"

    # Background payments poller (checks pending payments without domain or open ports)
    background_poller_interval_sec: int = 15

    # Treblo API URL
    treblo_base_url: str = "https://api.treblo.com/v1"
    polling_interval_sec: float = 4.0
    generation_timeout_sec: int = 300


settings = Settings()
