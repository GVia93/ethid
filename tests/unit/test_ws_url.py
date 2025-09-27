from src.data.binance_ws import BinanceWsClient


def test_build_url_combined():
    c = BinanceWsClient("wss://fstream.binance.com/stream", ["ETHUSDT", "BTCUSDT"])
    url = c._build_url()
    assert url in {
        "wss://fstream.binance.com/stream?streams=ethusdt@kline_1m/btcusdt@kline_1m",
        "wss://fstream.binance.com/stream?streams=btcusdt@kline_1m/ethusdt@kline_1m",
    }
