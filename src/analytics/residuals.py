from __future__ import annotations

from collections import deque


def residual(r_eth: float, r_btc: float, alpha: float, beta: float) -> float:
    """Вычислить остаток ε_t = r_eth - (α + β * r_btc)."""
    return r_eth - (alpha + beta * r_btc)


class ResidualAccumulator:
    """Скользящее суммирование остатков за горизонт H (по умолчанию 60 точек).

    Поддерживает инкрементальное обновление: добавили ε_t → получили сумму за последние H.
    """

    def __init__(self, horizon: int = 60) -> None:
        if horizon <= 0:
            raise ValueError("horizon должен быть > 0")
        self.horizon: int = horizon
        self._queue: deque[float] = deque(maxlen=horizon)
        self._sum: float = 0.0

    def push(self, eps: float) -> float:
        """Добавить остаток и вернуть новую кумуляцию за горизонт.

        Args:
            eps: Остаток ε_t.

        Returns:
            Сумма последних `horizon` ε.
        """
        if len(self._queue) == self.horizon:
            # deque с maxlen сам выкинет старый элемент ПОСЛЕ append,
            # поэтому снимем старый вручную для корректного поддержания суммы
            oldest = self._queue[0]
            self._sum -= oldest
        self._queue.append(eps)
        self._sum += eps
        return self._sum

    def value(self) -> float:
        """Текущее значение кумуляции (сумма по окну)."""
        return self._sum

    def reset(self) -> None:
        """Очистить состояние аккумулятора."""
        self._queue.clear()
        self._sum = 0.0
