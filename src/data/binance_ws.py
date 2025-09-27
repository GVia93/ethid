from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
from collections.abc import Awaitable, Callable, Iterable

import aiohttp

from src.domain.bars import Bar

logger = logging.getLogger(__name__)

BarHandler = Callable[[Bar], Awaitable[None]]


class BinanceWsClient:
    """Клиент Binance WS для подписки на kline_1m двух символов (ETH/BTC).

    URL базового эндпоинта передаётся снаружи (spot/futures),
    например:
        spot:   wss://stream.binance.com:9443/stream
        futures: wss://fstream.binance.com/stream

    Соединение устойчиво к разрывам: экспоненциальный backoff с джиттером,
    ping/pong через heartbeat.
    """

    def __init__(
        self,
        base_ws_url: str,
        symbols: Iterable[str],
        interval: str = "1m",
        on_bar: BarHandler | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.base_ws_url = base_ws_url.rstrip("/")
        self.symbols = [s.lower() for s in symbols]
        self.interval = interval
        self._on_bar = on_bar
        self._session = session
        self._stop = asyncio.Event()

    def _build_url(self) -> str:
        """
        Сформировать URL для подключения к Binance WebSocket.

        Генерирует строку запроса с комбинированным потоком kline для всех символов,
        используя заданный таймфрейм (`interval`).

        Returns:
            str: Полный URL для ws_connect.
        """
        streams = "/".join(f"{s}@kline_{self.interval}" for s in self.symbols)
        return f"{self.base_ws_url}?streams={streams}"

    async def run(self) -> None:
        """
        Запуск основного цикла работы WS-клиента Binance.

        Устанавливает подключение к WebSocket, слушает поток сообщений и обрабатывает их
        до тех пор, пока не будет выставлен флаг `_stop`. При обрыве соединения выполняется
        повторное подключение с экспоненциальным backoff и случайным джиттером.

        Особенности:
            - Создаёт собственную `aiohttp.ClientSession`, если она не была передана.
            - Поддерживает heartbeat соединения (15 секунд).
            - При получении `CancelledError` или `KeyboardInterrupt` завершает работу.
            - Закрывает созданную сессию при выходе.

        Raises:
            Exception: Любые ошибки в процессе работы приводят к попытке переподключения.
        """
        attempt = 0
        owns_session = False
        session = self._session
        if session is None:
            session = aiohttp.ClientSession()
            owns_session = True
        try:
            while not self._stop.is_set():
                try:
                    url = self._build_url()
                    async with session.ws_connect(url, heartbeat=15) as ws:
                        logger.info("WS connected: %s", url)
                        attempt = 0
                        async for msg in ws:
                            if self._stop.is_set():
                                break
                            await self._handle_message(msg)
                except Exception as e:
                    attempt += 1
                    backoff = min(30.0, 2 ** min(attempt, 5)) + random.uniform(0.0, 0.5)
                    logger.warning("WS reconnect in %.1fs (attempt=%s) due to: %r", backoff, attempt, e)
                    try:
                        await asyncio.wait_for(self._stop.wait(), timeout=backoff)
                    except TimeoutError:
                        pass
                    if self._stop.is_set():
                        break
        except (asyncio.CancelledError, KeyboardInterrupt):
            self._stop.set()
        finally:
            if owns_session:
                with contextlib.suppress(Exception):
                    await session.close()

    async def stop(self) -> None:
        """
        Остановить работу клиента.

        Устанавливает флаг `_stop`, который используется для завершения цикла
        приёма сообщений из WebSocket.
        """
        self._stop.set()

    async def _handle_message(self, msg: aiohttp.WSMessage) -> None:
        """
        Обработка сообщения WebSocket.

        Для текстовых сообщений вызывает внутренний метод `_handle_text`
        для дальнейшего парсинга и обработки свечей.

        Args:
            msg (aiohttp.WSMessage): Сообщение, полученное из WebSocket.
        """
        if msg.type == aiohttp.WSMsgType.TEXT:
            await self._handle_text(msg.data)

    async def _handle_text(self, data: str) -> None:
        """
        Обработка текстового сообщения из Binance WS.

        Декодирует JSON-пакет, извлекает объект kline и при наличии закрытой свечи (k["x"])
        логирует её основные параметры. Преобразует kline в объект `Bar` и, если он валиден,
        передаёт его во внешний обработчик `on_bar`.

        Args:
            data (str): Сырые текстовые данные в формате JSON, полученные по WebSocket.
        """
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            return

        data_obj = payload.get("data", payload)
        k = data_obj.get("k")

        if k and k.get("x"):
            logger.debug(
                "[CLOSED] %s i=%s T=%s close=%s",
                (k.get("s") or data_obj.get("s") or "").upper(),
                k.get("i"),
                k.get("T"),
                k.get("c"),
            )

        bar = Bar.from_binance_kline(payload)
        if bar is None:
            return

        if self._on_bar is not None:
            try:
                await self._on_bar(bar)
            except Exception as e:  # noqa: BLE001 — не роняем сокет из-за обработчика
                logger.exception("on_bar handler failed: %r", e)
