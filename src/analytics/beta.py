from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class BetaState:
    """
    Снимок состояния оценок регрессии на текущем шаге.

    Attributes:
        n: Количество наблюдений в роллинг-окне.
        alpha_hat: Оценка свободного члена (используя сглаженную beta_sm).
        beta_hat: Несглаженная моментная оценка беты по окну.
        beta_sm: Сглаженная (EWMA) бета.
        r2: Коэффициент детерминации по текущему окну (на beta_hat).
        var_btc: Неприведённая дисперсия BTC на окне (sum of squares around mean).
        var_eth: Неприведённая дисперсия ETH на окне.
        cov: Неприведённая ковариация BTC-ETH на окне.
        ts: Метка времени последнего наблюдения (как пришло извне).
    """

    n: int
    alpha_hat: float | None
    beta_hat: float | None
    beta_sm: float | None
    r2: float | None
    var_btc: float
    var_eth: float
    cov: float
    ts: datetime | None


class RollingBetaEWMA:
    """
    Онлайновая роллинговая OLS-оценка β, α для регрессии:
        r_eth = α + β * r_btc + ε

    Реализует:
      - Поддержание скользящего окна размера W.
      - Быстрые суммы для расчёта средних/дисперсий/ковариации.
      - EWMA-сглаживание β: beta_sm_t = λ * beta_sm_{t-1} + (1-λ) * beta_hat_t.
      - R² = cov^2 / (var_btc * var_eth) (на моментной beta_hat).
      - Защиту при почти нулевой дисперсии BTC: если var_btc < var_epsilon,
        beta_hat не пересчитываем (сохраняем прошлую), R² = 0.0.

    Примечания:
      - var_* и cov здесь считаются в "сырых" суммах (без деления на n или (n-1)),
        это не влияет на β и R² в таких формулах.
      - alpha оцениваем с использованием сглаженной beta_sm (более стабильная),
        формула: alpha = mean_eth - beta_sm * mean_btc.
      - Если наблюдений меньше warmup, возвращаем состояние без сигналов (оценки могут быть None).
    """

    def __init__(
        self,
        window: int,
        ewma_lambda: float = 0.94,
        warmup: int = 120,
        var_epsilon: float = 1e-12,
    ) -> None:
        if window <= 1:
            raise ValueError("window must be > 1")
        if not (0.0 < ewma_lambda < 1.0):
            raise ValueError("ewma_lambda must be in (0, 1)")
        if warmup < 1:
            raise ValueError("warmup must be >= 1")
        if var_epsilon <= 0.0:
            raise ValueError("var_epsilon must be > 0")

        self.window = window
        self.lmbd = ewma_lambda
        self.warmup = warmup
        self.var_epsilon = var_epsilon

        # Очередь (x=r_btc, y=r_eth)
        self._buf: deque[tuple[float, float]] = deque(maxlen=window)

        # Быстрые суммы для онлайнового пересчёта
        self._sx = 0.0
        self._sy = 0.0
        self._sxx = 0.0
        self._syy = 0.0
        self._sxy = 0.0

        # Оценки/состояние
        self._beta_hat: float | None = None
        self._beta_sm: float | None = None
        self._alpha_hat: float | None = None
        self._r2: float | None = None
        self._last_ts: datetime | None = None

    def update(self, r_btc: float, r_eth: float, ts: datetime | None = None) -> BetaState:
        """
        Обновить оценки роллинг-OLS и EWMA по новому наблюдению (r_btc, r_eth).

        Args:
            r_btc: Лог-доходность BTC за текущую минуту.
            r_eth: Лог-доходность ETH за текущую минуту.
            ts:   Метка времени закрытия свечи (UTC), опционально.

        Returns:
            BetaState: снимок текущего состояния оценок.
        """
        # Если буфер уже заполнен, при добавлении произойдёт pop слева — нужно вычесть старые значения.
        if len(self._buf) == self.window:
            ox, oy = self._buf[0]
            self._sub_from_sums(ox, oy)

        # Добавляем новое наблюдение
        self._buf.append((r_btc, r_eth))
        self._add_to_sums(r_btc, r_eth)
        self._last_ts = ts

        n = len(self._buf)
        # Пока мало данных — возвращаем минимальную диагностику
        if n < 2:
            return self._state(n=n, var_btc=0.0, var_eth=0.0, cov=0.0)

        # Средние и "сырые" дисперсии/ковариация (без деления на n или (n-1))
        mean_x = self._sx / n
        mean_y = self._sy / n

        var_x = self._sxx - n * mean_x * mean_x  # sum (x - mean_x)^2
        var_y = self._syy - n * mean_y * mean_y  # sum (y - mean_y)^2
        cov_xy = self._sxy - n * mean_x * mean_y  # sum (x-mean_x)(y-mean_y)

        # Guard: почти нулевая волатильность BTC -> не пересчитываем beta_hat, R²=0
        if var_x < self.var_epsilon:
            # beta_hat остаётся прежней; beta_sm не трогаем (заморозка)
            # alpha_hat пересчитываем только если beta_sm есть; иначе None
            self._r2 = 0.0
            self._alpha_hat = self._compute_alpha(mean_x, mean_y)  # может вернуть None
            return self._state(n=n, var_btc=var_x, var_eth=var_y, cov=cov_xy)

        # Оценка моментной беты (несглаженной) и R²
        beta_hat = cov_xy / var_x
        self._beta_hat = beta_hat

        # R² = cov^2 / (var_x * var_y), если var_y > 0, иначе 0
        self._r2 = (cov_xy * cov_xy) / (var_x * var_y) if var_y > self.var_epsilon else 0.0

        # EWMA сглаживание: если первая оценка — инициализируем beta_sm равной beta_hat
        if self._beta_sm is None:
            self._beta_sm = beta_hat
        else:
            self._beta_sm = self.lmbd * self._beta_sm + (1.0 - self.lmbd) * beta_hat

        # Оценка альфы — на сглаженной бете
        self._alpha_hat = self._compute_alpha(mean_x, mean_y)

        return self._state(n=n, var_btc=var_x, var_eth=var_y, cov=cov_xy)

    def reset(self) -> None:
        """Полностью сбросить окно и оценки."""
        self._buf.clear()
        self._sx = self._sy = self._sxx = self._syy = self._sxy = 0.0
        self._beta_hat = None
        self._beta_sm = None
        self._alpha_hat = None
        self._r2 = None
        self._last_ts = None

    @property
    def n(self) -> int:
        return len(self._buf)

    @property
    def beta_hat(self) -> float | None:
        return self._beta_hat if self.n >= self.warmup else None

    @property
    def beta_sm(self) -> float | None:
        return self._beta_sm if self.n >= self.warmup else None

    @property
    def alpha_hat(self) -> float | None:
        return self._alpha_hat if self.n >= self.warmup else None

    @property
    def r2(self) -> float | None:
        return self._r2 if self.n >= self.warmup else None

    @property
    def last_ts(self) -> datetime | None:
        return self._last_ts

    def _add_to_sums(self, x: float, y: float) -> None:
        self._sx += x
        self._sy += y
        self._sxx += x * x
        self._syy += y * y
        self._sxy += x * y

    def _sub_from_sums(self, x: float, y: float) -> None:
        self._sx -= x
        self._sy -= y
        self._sxx -= x * x
        self._syy -= y * y
        self._sxy -= x * y

    def _compute_alpha(self, mean_x: float, mean_y: float) -> float | None:
        if self._beta_sm is None:
            return None
        return mean_y - self._beta_sm * mean_x

    def _state(self, n: int, var_btc: float, var_eth: float, cov: float) -> BetaState:
        # Прячет warmup: до набора warmup возвращаем оценки как None
        beta_hat = self._beta_hat if n >= self.warmup else None
        beta_sm = self._beta_sm if n >= self.warmup else None
        alpha_hat = self._alpha_hat if n >= self.warmup else None
        r2 = self._r2 if n >= self.warmup else None

        return BetaState(
            n=n,
            alpha_hat=alpha_hat,
            beta_hat=beta_hat,
            beta_sm=beta_sm,
            r2=r2,
            var_btc=var_btc,
            var_eth=var_eth,
            cov=cov,
            ts=self._last_ts,
        )
