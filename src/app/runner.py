import asyncio
import contextlib
import logging
import signal
from math import exp

from src.analytics.beta import RollingBetaEWMA
from src.analytics.residuals import ResidualAccumulator, residual
from src.app.app_logging import setup_logger
from src.config import settings
from src.data.binance_ws import BinanceWsClient
from src.data.cache import BarsCacheRegistry
from src.data.storage import create_all, init_engine
from src.domain.bars import Bar
from src.domain.returns import ReturnsTracker

logger = logging.getLogger(__name__)

SYMBOLS = [settings.SYMBOL_ETH, settings.SYMBOL_BTC]
BASE_WS_URL = settings.BINANCE_WS_URL
INTERVAL = settings.TIMEFRAME  # "1m" по умолчанию

registry = BarsCacheRegistry(SYMBOLS, maxlen=600)
returns_tracker = ReturnsTracker(window_size=settings.WINDOW_CUM)  # 60 по умолчанию
beta_tracker = RollingBetaEWMA(
    window=settings.WINDOW_REG,
    ewma_lambda=settings.EWMA_LAMBDA,
    warmup=settings.WINDOW_WARMUP,
)
residual_acc = ResidualAccumulator(horizon=settings.RESIDUAL_WINDOW)

_stop = asyncio.Event()


async def on_bar(bar: Bar) -> None:
    """
    Обработчик закрытой минутной свечи (Bar) для ETHUSDT или BTCUSDT.

    Основные шаги:
      1. Добавляет бар в реестр кэшей (in-memory).
      2. Обновляет трекер лог-доходностей (`ReturnsTracker`).
      3. Для ETH логирует кумулятивную доходность за 60 минут (cum60_pct).
      4. Извлекает последние доходности ETH и BTC, подаёт их в
         роллинговую регрессию (`RollingBetaEWMA`).
      5. При достаточном прогреве окна логирует оценки беты/альфы/R².

    Args:
        bar (Bar): Объект закрытой свечи, нормализованный из Binance WS.

    Side Effects:
        - Заполняет кэши свечей для ETHUSDT и BTCUSDT.
        - Модифицирует внутреннее состояние трекеров доходностей и беты.
        - Пишет диагностические сообщения в лог:
            * [RETURNS] ... cum60_pct=... для ETH.
            * [BETA] n=... beta_hat=... beta_sm=... alpha=... R2=... при наличии оценки.

    Notes:
        - Для расчёта регрессии требуется наличие доходностей по обоим символам.
        - До набора окна прогрева (`settings.WINDOW_WARMUP`) оценки β/α/R² не выводятся.
        - В лог пишутся значения с безопасной подстановкой (0.0 для None).
    """
    await registry.add(bar)

    diag = returns_tracker.update(bar.symbol, bar.close)

    if bar.symbol.upper() == settings.SYMBOL_ETH and diag["cum60_pct"] is not None:
        logger.info(
            "[RETURNS] %s %s cum60_pct=%.4f",
            bar.symbol,
            bar.minute.isoformat(),
            diag["cum60_pct"],
            extra={"symbol": bar.symbol, "cum60_pct": diag["cum60_pct"]},
        )

    r_eth = returns_tracker.last_return(settings.SYMBOL_ETH)
    r_btc = returns_tracker.last_return(settings.SYMBOL_BTC)

    if r_eth is not None and r_btc is not None:
        state = beta_tracker.update(r_btc=r_btc, r_eth=r_eth, ts=bar.minute)

        if state.beta_sm is not None:
            logger.info(
                "[BETA] n=%s beta_hat=%.4f beta_sm=%.4f alpha=%.6f R2=%.3f",
                state.n,
                state.beta_hat or 0.0,
                state.beta_sm or 0.0,
                state.alpha_hat or 0.0,
                state.r2 or 0.0,
                extra={
                    "beta_hat": state.beta_hat,
                    "beta_sm": state.beta_sm,
                    "alpha": state.alpha_hat,
                    "r2": state.r2,
                },
            )

        # считать остаток только если оценки готовы
        if state.alpha_hat is not None and state.beta_sm is not None:
            eps = residual(r_eth, r_btc, state.alpha_hat, state.beta_sm)
            res_sum = residual_acc.push(eps)
            res_pct = exp(res_sum) - 1.0
            logger.info(
                "[RESIDUAL] %s %s own_move60=%.4f",
                settings.SYMBOL_ETH,
                bar.minute.isoformat(),
                res_pct,
                extra={"own_move60": res_pct},
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
        init_engine()  # возьмёт DATABASE_URL и параметры пула из Settings
        create_all()  # создаст таблицы, когда модели появятся
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
