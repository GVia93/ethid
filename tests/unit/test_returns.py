import math
from math import isclose

from src.domain.returns import ReturnsTracker, cumulative_return, log_return, winsorize


def test_log_return_with_zero_or_negative_prices():
    # prev_close = 0 → должны вернуть 0.0
    assert log_return(0.0, 100.0) == 0.0
    # curr_close = 0 → тоже 0.0
    assert log_return(100.0, 0.0) == 0.0
    # отрицательные значения → безопасно 0.0
    assert log_return(-100.0, 110.0) == 0.0
    assert log_return(100.0, -110.0) == 0.0
    # оба отрицательные → тоже 0.0
    assert log_return(-100.0, -200.0) == 0.0


def test_cumulative_during_warmup_uses_short_window():
    """
    Пока n < window_size, cum60_pct должен отражать фактическое короткое окно,
    а не None/0. Проверяем на последовательности +1% за бар.
    """
    window = 4
    t = ReturnsTracker(window_size=window)

    prices = [100.0, 101.0, 102.01, 103.0301, 104.060401]  # каждый шаг ~ +1%
    outs = []
    for p in prices:
        outs.append(t.update("ETHUSDT", p))

    # outs[0]: первая цена — прогрев, n=0, cum60_pct=None
    assert outs[0]["n"] == 0
    assert outs[0]["cum60_pct"] is None

    # outs[1]: появится 1 лог-доходность
    assert outs[1]["n"] == 1
    assert math.isclose(outs[1]["cum60_pct"], 1.01**1 - 1.0, rel_tol=1e-9)

    # outs[2]: 2 лог-доходности
    assert outs[2]["n"] == 2
    assert math.isclose(outs[2]["cum60_pct"], 1.01**2 - 1.0, rel_tol=1e-9)

    # outs[3]: 3 лог-доходности (всё ещё < window)
    assert outs[3]["n"] == 3
    assert math.isclose(outs[3]["cum60_pct"], 1.01**3 - 1.0, rel_tol=1e-9)

    # outs[4]: 4 лог-доходности, окно заполнено (== window)
    assert outs[4]["n"] == 4
    assert math.isclose(outs[4]["cum60_pct"], 1.01**4 - 1.0, rel_tol=1e-9)


def test_winsorize_basic():
    data = [-10.0, -0.2, -0.1, 0.0, 0.1, 0.2, 10.0]
    w = winsorize(data, p_low=0.10, p_high=0.90)  # подрежем ~10% хвосты
    # нижний хвост подтянут не ниже 10-го перцентиля (~ -0.2 / -0.1), верхний — не выше ~0.2
    assert min(w) >= -0.2
    assert max(w) <= 0.2

    # монотонность границ: при p_low=0, p_high=1 список не меняется
    w2 = winsorize(data, 0.0, 1.0)
    assert w2 == [float(v) for v in data]


def test_log_return_and_cum():
    assert isclose(log_return(100, 110), 0.0953102, rel_tol=1e-6)
    assert log_return(0, 110) == 0.0

    r = [log_return(100, 105), log_return(105, 100)]
    pct = cumulative_return(r)
    assert isclose(pct, 0.0, abs_tol=1e-12)


def test_tracker_flow():
    t = ReturnsTracker(window_size=3)
    # первая цена — только инициализация
    out = t.update("ETHUSDT", 100.0)
    assert out["n"] == 0

    out = t.update("ETHUSDT", 105.0)
    assert out["n"] == 1
    assert out["last_lr"] is not None
    assert out["cum60_pct"] is not None
