from datetime import UTC, datetime

import pytest

from src.data.cache import BarCache, BarsCacheRegistry
from src.domain.bars import Bar


def _bar(symbol: str, minute: int, close: float) -> Bar:
    dt = datetime.fromtimestamp(minute * 60, tz=UTC)
    return Bar(
        symbol=symbol,
        interval="1m",
        open_ts=dt,
        close_ts=dt,
        minute=dt,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1.0,
    )


@pytest.mark.asyncio
async def test_bar_cache_add_last_lastn():
    cache = BarCache("ETHUSDT", maxlen=3)
    await cache.add(_bar("ETHUSDT", 1, 1.0))
    await cache.add(_bar("ETHUSDT", 2, 2.0))
    await cache.add(_bar("ETHUSDT", 3, 3.0))
    await cache.add(_bar("BTCUSDT", 999, 999.0))  # игнор по символу

    last = await cache.last()
    assert last and last.close == 3.0

    last2 = await cache.last_n(2)
    assert [b.close for b in last2] == [2.0, 3.0]


@pytest.mark.asyncio
async def test_registry_routes_by_symbol():
    reg = BarsCacheRegistry(["ETHUSDT", "BTCUSDT"], maxlen=2)
    await reg.add(_bar("ETHUSDT", 1, 10.0))
    await reg.add(_bar("BTCUSDT", 1, 20.0))

    e = await reg.last("ETHUSDT")
    b = await reg.last("BTCUSDT")
    assert e and e.close == 10.0
    assert b and b.close == 20.0
