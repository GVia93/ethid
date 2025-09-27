import json

import pytest

from src.data.binance_ws import BinanceWsClient
from src.domain.bars import Bar


async def _feed(client: BinanceWsClient, frames: list[dict]) -> list[Bar]:
    bars: list[Bar] = []

    async def on_bar(bar: Bar):
        bars.append(bar)

    client._on_bar = on_bar  # тестовый хук

    for f in frames:
        await client._handle_text(json.dumps(f))

    return bars


@pytest.mark.asyncio
async def test_replay_combined_frames():
    client = BinanceWsClient("wss://example", ["ETHUSDT", "BTCUSDT"])  # URL не используется

    frames = [
        {  # незакрытая — будет проигнорирована
            "stream": "ethusdt@kline_1m",
            "data": {
                "e": "kline",
                "s": "ETHUSDT",
                "k": {
                    "t": 1,
                    "T": 60_000,
                    "s": "ETHUSDT",
                    "i": "1m",
                    "o": "1",
                    "c": "1",
                    "h": "1",
                    "l": "1",
                    "v": "1",
                    "x": False,
                },
            },
        },
        {  # закрытая — должна превратиться в Bar
            "stream": "ethusdt@kline_1m",
            "data": {
                "e": "kline",
                "s": "ETHUSDT",
                "k": {
                    "t": 60_000,  # open = 1m
                    "T": 120_000,  # close = 2m
                    "s": "ETHUSDT",
                    "i": "1m",
                    "o": "1",
                    "c": "2",
                    "h": "2",
                    "l": "1",
                    "v": "3.14",
                    "x": True,
                },
            },
        },
    ]

    bars = await _feed(client, frames)
    assert len(bars) == 1
    assert bars[0].symbol == "ETHUSDT"
    assert bars[0].close == 2.0
