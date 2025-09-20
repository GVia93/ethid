from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BINANCE_API_KEY: str | None = None
    BINANCE_API_SECRET: str | None = None
    DB_URL: str | None = None
    LOG_LEVEL: str = "INFO"

    # методика / параметры по умолчанию
    WINDOW_REG: int = 240        # окно роллинг-OLS (минут)
    WINDOW_WARMUP: int = 120     # минимум баров до сигналов
    WINDOW_CUM: int = 60         # окно кум. остатка (60м)
    EWMA_LAMBDA: float = 0.94    # сглаживание беты
    THRESHOLD_PCT: float = 0.01  # порог 1% для сигнала
    HYSTERESIS_PCT: float = 0.002# гистерезис 0.2%
    COOLDOWN_MIN: int = 30       # кулдаун сигналов
    SYMBOL_ETH: str = "ETHUSDT"
    SYMBOL_BTC: str = "BTCUSDT"
    TIMEFRAME: str = "1m"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
