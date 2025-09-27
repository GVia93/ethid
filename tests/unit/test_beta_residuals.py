from __future__ import annotations

import math
import statistics as stats
from datetime import UTC, datetime, timedelta
from random import Random

from src.analytics.beta import RollingBetaEWMA
from src.analytics.residuals import ResidualAccumulator, residual


def _mk_ts(i: int) -> datetime:
    # удобная метка времени для beta.update(...)
    return datetime(2025, 1, 1, tzinfo=UTC) + timedelta(minutes=i)


def test_residual_accumulator_push_and_reset():
    acc = ResidualAccumulator(horizon=3)

    # push [1, 1, 1] -> сумма 3
    assert acc.push(1.0) == 1.0
    assert acc.push(1.0) == 2.0
    assert acc.push(1.0) == 3.0
    # push ещё 1 -> окно [1,1,1] "сдвинулось", сумма остаётся 3
    assert acc.push(1.0) == 3.0
    assert acc.value() == 3.0

    acc.reset()
    assert acc.value() == 0.0
    # после reset начинаем заново
    assert acc.push(2.0) == 2.0
    assert acc.value() == 2.0


def test_beta_on_synthetic_data_beta_approx_0_8_and_residuals_are_noise():
    """
    Генерируем синтетику: r_eth = 0.8 * r_btc + eps, eps ~ N(0, σ^2) (нестрого, через Random).
    Проверяем, что beta_hat ~ 0.8 и остатки имеют ~нулевое среднее и заметно меньшую дисперсию,
    чем у r_eth (эвристический критерий).
    """
    rnd = Random(12345)

    # параметры синтетики
    true_beta = 0.8
    n = 500
    warmup = 30
    window = 240
    lmbd = 0.94

    # сгенерируем r_btc как небольшой шум вокруг 0,
    # r_eth = beta * r_btc + eps, eps независимый шум
    r_btc_series = [rnd.gauss(0.0, 0.004) for _ in range(n)]
    eps_series = [rnd.gauss(0.0, 0.002) for _ in range(n)]
    r_eth_series = [true_beta * x + e for x, e in zip(r_btc_series, eps_series, strict=False)]

    tracker = RollingBetaEWMA(window=window, ewma_lambda=lmbd, warmup=warmup)

    # подаём последовательность, запоминаем оценки на конце
    last_state = None
    for i, (x, y) in enumerate(zip(r_btc_series, r_eth_series, strict=False)):
        last_state = tracker.update(r_btc=x, r_eth=y, ts=_mk_ts(i))

    assert last_state is not None
    # после прогрева и окна должны быть валидные оценки
    assert last_state.beta_hat is not None
    assert last_state.beta_sm is not None
    # beta_hat близка к 0.8 (с учётом шума допускаем небольшую погрешность)
    assert math.isclose(last_state.beta_hat, true_beta, rel_tol=0.1)
    # сглаженная бета тоже рядом
    assert math.isclose(last_state.beta_sm, true_beta, rel_tol=0.12)

    # посчитаем остатки на всём ряде по финальным оценкам (alpha на beta_sm)
    alpha = last_state.alpha_hat or 0.0
    beta_sm = last_state.beta_sm or true_beta
    residuals = [residual(y, x, alpha=alpha, beta=beta_sm) for x, y in zip(r_btc_series, r_eth_series, strict=False)]

    # у остатков среднее близко к 0
    res_mean = stats.fmean(residuals)
    assert abs(res_mean) < 5e-4

    # дисперсия остатков значительно меньше дисперсии y (эвристика: в 3+ раза слабее)
    var_y = stats.pvariance(r_eth_series)
    var_eps = stats.pvariance(residuals)
    assert var_eps < var_y / 3.0

    # R^2 адекватный (положительный и не крошечный)
    assert last_state.r2 is not None and last_state.r2 > 0.2


def test_property_eth_equals_btc_beta_about_1_and_residuals_near_zero():
    """
    Property-like: если r_eth == r_btc (идеальная зависимость),
    то beta ≈ 1, alpha ≈ 0, а остатки ≈ 0.
    """
    rnd = Random(20250927)

    n = 200
    warmup = 20
    window = 120
    lmbd = 0.94

    # r_btc ~ шум, r_eth == r_btc
    r_btc_series = [rnd.gauss(0.0, 0.003) for _ in range(n)]
    r_eth_series = list(r_btc_series)

    tracker = RollingBetaEWMA(window=window, ewma_lambda=lmbd, warmup=warmup)
    last_state = None
    for i, (x, y) in enumerate(zip(r_btc_series, r_eth_series, strict=False)):
        last_state = tracker.update(r_btc=x, r_eth=y, ts=_mk_ts(i))

    assert last_state is not None
    assert last_state.beta_hat is not None
    assert last_state.beta_sm is not None
    assert last_state.alpha_hat is not None

    # β ≈ 1, α ≈ 0
    assert math.isclose(last_state.beta_hat, 1.0, rel_tol=0.05)
    assert abs(last_state.alpha_hat) < 1e-4

    # Остатки близки к нулю (по финальным оценкам)
    alpha = last_state.alpha_hat or 0.0
    beta_sm = last_state.beta_sm or 1.0
    residuals = [residual(y, x, alpha=alpha, beta=beta_sm) for x, y in zip(r_btc_series, r_eth_series, strict=False)]

    res_mean = stats.fmean(residuals)
    var_res = stats.pvariance(residuals)
    # среднее почти 0, дисперсия очень мала
    assert abs(res_mean) < 1e-6
    assert var_res < 1e-8
