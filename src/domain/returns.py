from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Iterable, MutableMapping
from dataclasses import dataclass, field
from math import exp, isfinite, log


def winsorize(values: Iterable[float], p_low: float = 0.01, p_high: float = 0.99) -> list[float]:
    """
    Простое winsorize по квантилям p_low/p_high (0..1).
    Не использует numpy — работает на чистом Python.

    Шаги:
      1) фильтруем нечисловые/нефинитные значения;
      2) считаем индексы квантилей на отсортированном массиве;
      3) «прижимаем» значения к [q_low, q_high].

    Возвращает новый список (исходный не меняется).
    """
    if not (0.0 <= p_low <= p_high <= 1.0):
        raise ValueError("p_low and p_high must satisfy 0 <= p_low <= p_high <= 1")

    vals = [float(v) for v in values if isfinite(v)]
    if not vals:
        return []

    srt = sorted(vals)
    n = len(srt)
    # используем ближайший индекс квантиля (интерполяция не обязательна для winsorize)
    i_low = max(0, min(n - 1, int(round(p_low * (n - 1)))))
    i_high = max(0, min(n - 1, int(round(p_high * (n - 1)))))
    q_low, q_high = srt[i_low], srt[i_high]

    return [min(max(v, q_low), q_high) for v in vals]


def log_return(prev_close: float, curr_close: float) -> float:
    """
    Лог-доходность между двумя закрытиями: r = ln(P_t / P_{t-1}).
    Если цена некорректна (<=0) → 0.0.
    """
    if prev_close <= 0 or curr_close <= 0:
        return 0.0
    return log(curr_close / prev_close)


def cumulative_return(log_returns: Iterable[float]) -> float:
    """
    Кумулятивная доходность по лог-доходностям:
    pct = exp(sum(r_i)) - 1
    Возвращает долю (0.01 == +1%).
    """
    return exp(sum(log_returns)) - 1.0


@dataclass
class _SeriesState:
    last_close: float | None = None
    window: deque[float] = field(default_factory=deque)


class ReturnsTracker:
    """
    Накопитель лог-доходностей по символам.
    Хранит окно (по умолчанию 60) для вычисления cumret.

    update(symbol, close) → dict с диагностикой:
        n — число значений в окне,
        last_lr — последняя лог-доходность,
        cum60_pct — кумулятив за <=60 баров (в долях), либо None.
    """

    def __init__(self, window_size: int = 60) -> None:
        if window_size <= 0:
            raise ValueError("window_size must be > 0")
        self.window_size = window_size
        self._state: MutableMapping[str, _SeriesState] = defaultdict(
            lambda: _SeriesState(last_close=None, window=deque(maxlen=self.window_size))
        )

    def reset(self, symbol: str) -> None:
        self._state.pop(symbol.upper(), None)

    def update(self, symbol: str, close: float) -> dict[str, float | int | None]:
        sym = symbol.upper()
        st = self._state[sym]
        last_lr: float | None = None

        if st.last_close is not None and close > 0:
            r = log_return(st.last_close, close)
            st.window.append(r)
            last_lr = r
        if close > 0:
            st.last_close = close

        cum = cumulative_return(st.window) if st.window else None

        return {"n": len(st.window), "last_lr": last_lr, "cum60_pct": cum}

    def last_return(self, symbol: str) -> float | None:
        """
        Возвращает последнюю лог-доходность для символа,
        либо None, если данных нет.
        """
        sym = symbol.upper()
        st = self._state.get(sym)
        if st is None or not st.window:
            return None
        return st.window[-1]
