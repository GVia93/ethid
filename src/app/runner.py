import asyncio
import contextlib
import logging
import signal

from src.app.app_logging import setup_logger
from src.config import settings
from src.data.binance_ws import BinanceWsClient
from src.data.cache import BarsCacheRegistry
from src.data.storage import init_engine, create_all
from src.domain.bars import Bar

logger = logging.getLogger(__name__)

SYMBOLS = [settings.SYMBOL_ETH, settings.SYMBOL_BTC]
BASE_WS_URL = settings.BINANCE_WS_URL
INTERVAL = settings.TIMEFRAME  # "1m" по умолчанию

registry = BarsCacheRegistry(SYMBOLS, maxlen=600)
_stop = asyncio.Event()


async def on_bar(bar: Bar) -> None:
    """
    Обработчик закрытой свечи (Bar).

    Добавляет бар в реестр кэшей и логирует его параметры.
    Используется в раннере как callback для Binance WS-клиента.

    Args:
        bar (Bar): Объект свечи, полученной из потока Binance.
    """
    await registry.add(bar)
    last = await registry.last(bar.symbol)
    if last:
        logger.info(
            "%s %s close=%s",
            bar.symbol,
            bar.minute.isoformat(),
            bar.close,
            extra={"symbol": bar.symbol, "minute": bar.minute.isoformat(), "close": bar.close},
        )


def _setup_signals(loop: asyncio.AbstractEventLoop) -> None:
    """
    Настроить обработчики системных сигналов для корректного завершения приложения.

    Добавляет в цикл событий перехват SIGINT и SIGTERM (если они доступны),
    чтобы при их получении вызывалось событие `_stop.set()`.
    На платформах, где сигнал не поддерживается, обработчик пропускается.

    Args:
        loop (asyncio.AbstractEventLoop): Активный цикл событий asyncio.
    """
    for sig in (getattr(signal, "SIGINT", None), getattr(signal, "SIGTERM", None)):
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, _stop.set)
        except NotImplementedError:
            pass


async def main() -> None:
    """
    Точка входа в приложение.

    Выполняет настройку логгера, инициализацию подключения к БД (если указана DATABASE_URL),
    запуск Binance WS-клиента и регистрацию системных сигналов для корректного завершения.

    Цикл работы продолжается до получения события `_stop` или прерывания клавиатурой.
    При завершении останавливает клиента и корректно отменяет задачу.

    Raises:
        asyncio.CancelledError: Может быть подавлена при отмене фоновой задачи клиента.
    """
    setup_logger(settings.LOG_LEVEL, settings.LOG_JSON)

    try:
        init_engine()      # возьмёт DATABASE_URL и параметры пула из Settings
        create_all()       # создаст таблицы, когда модели появятся
    except AssertionError as e:
        logger.warning("DB init skipped: %s", e)

    client = BinanceWsClient(BASE_WS_URL, SYMBOLS, interval=INTERVAL, on_bar=on_bar)

    loop = asyncio.get_running_loop()
    _setup_signals(loop)

    task = asyncio.create_task(client.run())
    try:
        await _stop.wait()
    except KeyboardInterrupt:
        pass
    finally:
        await client.stop()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


if __name__ == "__main__":
    asyncio.run(main())
