from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Конфигурация приложения, загружаемая из `.env` или переменных окружения.

    Содержит ключи API Binance, параметры подключения к БД, настройки логирования,
    а также методические константы для анализа сигналов.

    Атрибуты:
        BINANCE_API_KEY (str | None): Ключ API Binance.
        BINANCE_API_SECRET (str | None): Секрет API Binance.
        BINANCE_WS_URL (str): URL WebSocket для Binance Futures.
        DATABASE_URL (str | None): URL подключения к БД (SQLAlchemy).
        DB_POOL_SIZE (int): Размер пула подключений.
        DB_MAX_OVERFLOW (int): Допустимое превышение пула.
        DB_ECHO (bool): Включение логирования SQL-запросов.
        LOG_LEVEL (str): Уровень логирования (INFO, DEBUG и т.д.).
        LOG_JSON (bool): Логировать в формате JSON.

        WINDOW_REG (int): Размер окна роллинг-OLS (в минутах).
        WINDOW_WARMUP (int): Минимальное число баров перед генерацией сигналов.
        WINDOW_CUM (int): Окно для кумулятивного остатка (в минутах).
        EWMA_LAMBDA (float): Коэффициент сглаживания для беты (EWMA).
        THRESHOLD_PCT (float): Порог изменения цены ETH для сигнала (в долях).
        HYSTERESIS_PCT (float): Гистерезис для фильтрации сигналов.
        COOLDOWN_MIN (int): Минимальный кулдаун между сигналами (в минутах).
        SYMBOL_ETH (str): Символ ETH (по умолчанию ETHUSDT).
        SYMBOL_BTC (str): Символ BTC (по умолчанию BTCUSDT).
        TIMEFRAME (str): Таймфрейм анализа (по умолчанию 1m).
    """
    BINANCE_API_KEY: str | None = None
    BINANCE_API_SECRET: str | None = None
    BINANCE_WS_URL: str = Field(default="wss://fstream.binance.com/stream")
    DATABASE_URL: str | None = None
    DB_POOL_SIZE: int = Field(default=5)
    DB_MAX_OVERFLOW: int = Field(default=10)
    DB_ECHO: bool = Field(default=False)
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = Field(default=False)

    # методика / параметры по умолчанию
    WINDOW_REG: int = 240
    WINDOW_WARMUP: int = 120
    WINDOW_CUM: int = 60
    EWMA_LAMBDA: float = 0.94
    THRESHOLD_PCT: float = 0.01
    HYSTERESIS_PCT: float = 0.002
    COOLDOWN_MIN: int = 30
    SYMBOL_ETH: str = "ETHUSDT"
    SYMBOL_BTC: str = "BTCUSDT"
    TIMEFRAME: str = "1m"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
