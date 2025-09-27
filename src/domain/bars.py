from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Bar:
    """OHLCV-бар (минутка) для инструмента с канонизацией времени и валидацией.

    Attributes:
    symbol: Тикер (например, "ETHUSDT"), всегда UPPER.
    interval: Интервал ("1m").
    open_ts: Время открытия свечи (UTC, aware).
    close_ts: Время закрытия свечи (UTC, aware) из биржевого поля T (ms).
    minute: Каноническая минутная метка закрытия (секунды=0, микросекунды=0).
    open, high, low, close, volume: Ценовые поля и объём.
    quote_volume, trades, taker_buy_base, taker_buy_quote: Доп. поля (если доступны).
    """

    symbol: str
    interval: str
    open_ts: datetime
    close_ts: datetime
    minute: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float | None = None
    trades: int | None = None
    taker_buy_base: float | None = None
    taker_buy_quote: float | None = None

    @staticmethod
    def _to_dt(ms: int) -> datetime:
        return datetime.fromtimestamp(ms / 1000, tz=UTC)

    @staticmethod
    def _to_minute_from_close_ms(close_ms: int) -> datetime:
        """Нормализует время закрытия к началу минуты (сек=0, мс=0).
        Binance даёт T=...59999 (последняя мс). Берём (T+1) и отбрасываем остаток минут.
        """

        minute_epoch = ((close_ms + 1) // 60000) * 60  # секунды
        return datetime.fromtimestamp(minute_epoch, tz=UTC)

    @classmethod
    def from_binance_kline(cls, payload: dict[str, Any]) -> Bar | None:
        """Преобразует WS kline Binance в `Bar`.
        Поддерживаются оба формата:
          1) combined stream: {"stream": "...", "data": {"e":"kline","s":"ETHUSDT","k":{...}}}
          2) raw stream:      {"e":"kline","s":"ETHUSDT","k":{...}}

        Возвращает None, если свеча не закрыта (k["x"] is False) или данные неконсистентны.
        """

        data = payload.get("data", payload)
        k = data.get("k")
        if not isinstance(k, dict) or not k.get("x", False):
            return None

        try:
            symbol = (k.get("s") or data.get("s") or "").upper()
            if not symbol:
                return None

            interval = k.get("i") or "1m"
            open_ms = int(k["t"])
            close_ms = int(k["T"])

            open_ts = cls._to_dt(open_ms)
            close_ts = cls._to_dt(close_ms)
            minute = cls._to_minute_from_close_ms(close_ms)

            o = float(k["o"])
            h = float(k["h"])
            low = float(k["l"])
            c = float(k["c"])
            v = float(k["v"])
            q = float(k["q"]) if k.get("q") is not None else None
            n = int(k["n"]) if k.get("n") is not None else None
            tb = float(k["V"]) if k.get("V") is not None else None
            tq = float(k["Q"]) if k.get("Q") is not None else None
        except Exception:
            return None

        if not (low <= min(o, c) <= max(o, c) <= h):
            return None

        return cls(
            symbol=symbol,
            interval=interval,
            open_ts=open_ts,
            close_ts=close_ts,
            minute=minute,
            open=o,
            high=h,
            low=low,
            close=c,
            volume=v,
            quote_volume=q,
            trades=n,
            taker_buy_base=tb,
            taker_buy_quote=tq,
        )

    @classmethod
    def from_binance_rest(cls, row: list[Any], symbol: str, interval: str = "1m") -> Bar | None:
        """Парсит строку REST klines Binance в `Bar`.

        Формат строки (упрощённо):
        [ openTime, open, high, low, close, volume,
        closeTime, quoteAssetVolume, numberOfTrades,
        takerBuyBase, takerBuyQuote, ignore ]
        """

        try:
            open_ms = int(row[0])
            close_ms = int(row[6])
            o = float(row[1])
            h = float(row[2])
            low = float(row[3])
            c = float(row[4])
            v = float(row[5])
            q = float(row[7]) if row[7] is not None else None
            n = int(row[8]) if row[8] is not None else None
            tb = float(row[9]) if row[9] is not None else None
            tq = float(row[10]) if row[10] is not None else None
        except Exception:
            return None

        if not (low <= min(o, c) <= max(o, c) <= h):
            return None

        return cls(
            symbol=symbol.upper(),
            interval=interval,
            open_ts=cls._to_dt(open_ms),
            close_ts=cls._to_dt(close_ms),
            minute=cls._to_minute_from_close_ms(close_ms),
            open=o,
            high=h,
            low=low,
            close=c,
            volume=v,
            quote_volume=q,
            trades=n,
            taker_buy_base=tb,
            taker_buy_quote=tq,
        )

    def key(self) -> tuple[str, str, datetime]:
        """Уникальный ключ бара для кэша/БД."""

        return (self.symbol, self.interval, self.minute)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "interval": self.interval,
            "open_ts": self.open_ts.isoformat(),
            "close_ts": self.close_ts.isoformat(),
            "minute": self.minute.isoformat(),
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "quote_volume": self.quote_volume,
            "trades": self.trades,
            "taker_buy_base": self.taker_buy_base,
            "taker_buy_quote": self.taker_buy_quote,
        }
