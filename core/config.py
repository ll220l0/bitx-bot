from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    BOT_TOKEN: str | None = None
    ADMIN_CHAT_ID: int | None = None
    MANAGER_CHAT_IDS: str | None = None
    BOT_MODE: str = "polling"
    WEBHOOK_PATH: str = "/telegram/webhook"
    WEBHOOK_SECRET_TOKEN: str | None = None
    PUBLIC_BASE_URL: str | None = None
    META_GRAPH_API_VERSION: str = "v20.0"
    WHATSAPP_ACCESS_TOKEN: str | None = None
    WHATSAPP_PHONE_NUMBER_ID: str | None = None
    INSTAGRAM_ACCESS_TOKEN: str | None = None
    INSTAGRAM_PAGE_ID: str | None = None
    INSTAGRAM_SEND_API_URL: str | None = None
    DATABASE_URL: str = "sqlite+aiosqlite:///./bitx.db"
    API_BASE: str = "http://127.0.0.1:8000"
    ASSISTANT_ENABLED: bool = True
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4.1-mini"
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    ASSISTANT_HISTORY_MESSAGES: int = 10
    ASSISTANT_MAX_HISTORY_CHARS: int = 6000
    ASSISTANT_MAX_TOKENS: int = 350
    SALES_MAX_DISCOUNT_PCT: int = 15
    AUTO_LEAD_CAPTURE_ENABLED: bool = True
    AUTO_LEAD_MIN_MESSAGES: int = 3
    AUTO_LEAD_MIN_DETAILS_CHARS: int = 60
    AUTO_LEAD_MIN_CONTEXT_SCORE: int = 5
    LEAD_FOLLOW_UP_AFTER_MESSAGES: int = 3
    LEAD_FOLLOW_UP_EVERY_N_MESSAGES: int = 3
    LEAD_FOLLOW_UP_DETAILS_AFTER_MESSAGES: int = 7

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def notification_chat_ids(self) -> list[int]:
        ids: list[int] = []
        if self.ADMIN_CHAT_ID is not None:
            ids.append(self.ADMIN_CHAT_ID)
        raw = (self.MANAGER_CHAT_IDS or "").strip()
        if not raw:
            return ids

        for part in raw.replace(";", ",").split(","):
            token = part.strip()
            if not token:
                continue
            try:
                value = int(token)
            except ValueError:
                continue
            if value not in ids:
                ids.append(value)
        return ids

settings = Settings()
