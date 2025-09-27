from datetime import UTC, datetime

from src.domain.bars import Bar


def test_from_binance_kline_combined_closed():
    payload = {
        "stream": "ethusdt@kline_1m",
        "data": {
            "e": "kline",
            "E": 1726828800123,
            "s": "ETHUSDT",
            "k": {
                "t": 1726828740000,  # open time (ms)
                "T": 1726828800000,  # close time (ms)
                "s": "ETHUSDT",
                "i": "1m",
                "f": 100,
                "L": 200,
                "o": "2500.00",
                "c": "2505.00",
                "h": "2506.00",
                "l": "2499.00",
                "v": "123.45",
                "n": 10,
                "x": True,
                "q": "0",
                "V": "0",
                "Q": "0",
                "B": "0",
            },
        },
    }

    bar = Bar.from_binance_kline(payload)
    assert bar is not None
    assert bar.symbol == "ETHUSDT"
    assert bar.interval == "1m"
    assert bar.close == 2505.0
    assert bar.volume == 123.45

    expected_dt = datetime.fromtimestamp(1726828800, tz=UTC)
    assert bar.close_ts == expected_dt
    assert bar.minute == expected_dt


def test_from_binance_kline_skips_open():
    payload = {
        "e": "kline",
        "E": 1726828800123,
        "s": "BTCUSDT",
        "k": {
            "t": 1726828740000,
            "T": 1726828800000,
            "s": "BTCUSDT",
            "i": "1m",
            "o": "100000.0",
            "c": "100100.0",
            "h": "100200.0",
            "l": "99900.0",
            "v": "10.0",
            "x": False,  # не закрыта — игнорируем
        },
    }

    assert Bar.from_binance_kline(payload) is None


def test_from_binance_kline_raw_closed():
    payload = {
        "e": "kline",
        "E": 1726828800123,
        "s": "BTCUSDT",
        "k": {
            "t": 1726828740000,
            "T": 1726828800000,
            "s": "BTCUSDT",
            "i": "1m",
            "o": "100000.0",
            "c": "100100.0",
            "h": "100200.0",
            "l": "99900.0",
            "v": "10.0",
            "n": 5,
            "x": True,  # закрыта — должна быть распознана
            "q": "0",
            "V": "0",
            "Q": "0",
            "B": "0",
        },
    }

    bar = Bar.from_binance_kline(payload)
    assert bar is not None
    assert bar.symbol == "BTCUSDT"
    assert bar.interval == "1m"
    assert bar.close == 100100.0
