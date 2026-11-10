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

    # Default settings for balance & limits
    initial_user_credits: int = 3
    generation_cost: int = 1

    # Treblo API URL
    treblo_base_url: str = "https://api.treblo.com/v1"
    polling_interval_sec: float = 4.0
    generation_timeout_sec: int = 300


settings = Settings()
