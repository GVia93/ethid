from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from src.domain.bars import Bar


@dataclass
class BarCache:
    """Кольцевой кэш баров для одного инструмента.

    Поскольку обновления приходят из одного event loop, достаточно одного Lock
    на операции записи/чтения, чтобы избежать гонок при одновременном доступе
    из разных корутин.
    """

    symbol: str
    maxlen: int = 600  # храним не менее 300+, по умолчанию запас

    def __post_init__(self) -> None:
        self._buf: deque[Bar] = deque(maxlen=self.maxlen)
        self._lock = asyncio.Lock()

    def __len__(self) -> int:  # pragma: no cover — тривиально
        return len(self._buf)

    async def add(self, bar: Bar) -> None:
        if bar.symbol != self.symbol:
            return
        async with self._lock:
            self._buf.append(bar)

    async def last(self) -> Bar | None:
        async with self._lock:
            return self._buf[-1] if self._buf else None

    async def last_n(self, n: int) -> Iterable[Bar]:
        if n <= 0:
            return []
        async with self._lock:
            return list(self._buf)[-n:]


class BarsCacheRegistry:
    """Реестр кэшей по символам.

    Пример:
        registry = BarsCacheRegistry(["ETHUSDT", "BTCUSDT"], maxlen=600)
        await registry.add(bar)  # автоматическое распределение по символу
    """

    def __init__(self, symbols: Iterable[str], maxlen: int = 600) -> None:
        self._maxlen = maxlen
        self._caches: dict[str, BarCache] = {}
        # Нормализуем ключи к UPPER, чтобы get("ETHUSDT") всегда находил кеш
        for s in symbols:
            key = s.upper()
            if key not in self._caches:
                self._caches[key] = BarCache(s, maxlen=self._maxlen)

    def get(self, symbol: str) -> BarCache | None:
        return self._caches.get(symbol.upper())

    async def add(self, bar: Bar) -> None:
        key = bar.symbol.upper()
        cache = self._caches.get(key)
        if cache is None:
            cache = BarCache(key, maxlen=self._maxlen)
            self._caches[key] = cache
        await cache.add(bar)

    async def last(self, symbol: str) -> Bar | None:
        cache = self.get(symbol)
        return await cache.last() if cache else None

    async def last_n(self, symbol: str, n: int) -> Iterable[Bar]:
        cache = self.get(symbol)
        return await cache.last_n(n) if cache else []
