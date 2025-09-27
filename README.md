# ETH Own‑Move Detector

Реалтайм‑сервис на Python 3.11 для выделения **собственного движения ETHUSDT**, очищенного от влияния BTCUSDT. При изменении очищенной цены ETH на **≥ 1%** за последние **60 минут** сервис печатает сигнал в консоль (и в структурный лог), продолжая работу непрерывно.

PostgreSQL используется **сразу** (для баров, коэффициентов β/α, метрик и сигналов). Управление зависимостями — **Poetry**. Контейнеризация — **Docker Compose** (поднимает `app` и `db`).

---

## Содержание

* [1. Методика](#1-методика)

  * [1.1. Модель и формулы](#11-модель-и-формулы)
  * [1.2. Параметры и обоснование](#12-параметры-и-обоснование)
  * [1.3. Альтернатива: бета‑нейтрализация цены](#13-альтернатива-бетанейтрализация-цены)
* [2. Архитектура](#2-архитектура)
* [3. Установка и запуск](#3-установка-и-запуск)

  * [3.1. Быстрый старт (Poetry + локально, DB в Docker)](#31-быстрый-старт-poetry--локально-db-в-docker)
  * [3.2. Docker / Docker Compose (app+db)](#32-docker--docker-compose-appdb)
  * [3.3. Переменные окружения](#33-переменные-окружения)
* [4. Использование](#4-использование)
* [5. Качество кода: типы, докстринги, линтеры](#5-качество-кода-типы-докстринги-линтеры)
* [6. Тестирование](#6-тестирование)
* [7. Логи и формат сигналов](#7-логи-и-формат-сигналов)
* [8. Roadmap и допущения](#8-roadmap-и-допущения)
* [9. Лицензия](#9-лицензия)

---

## 1. Методика

**Цель:** удалить компоненту движения ETH, объяснимую движением BTC, и мониторить остаточное (собственное) движение.

### 1.1. Модель и формулы

Работаем на минутных свечах (`kline_1m`). Используем лог‑доходности:

`r_t = ln(P_t / P_{t-1})`

Роллинг‑регрессия (окно `W`):

`r_eth_t = alpha_t + beta_t * r_btc_t + eps_t`,  для t ∈ \[t-W+1, t]

Оценки OLS:

`beta_hat_t = Cov(r_btc, r_eth) / Var(r_btc)`
`alpha_hat_t = mean(r_eth) - beta_hat_t * mean(r_btc)`

Стабилизация беты экспоненциальным сглаживанием (EWMA, λ ∈ (0,1)):

`beta_sm_t = λ * beta_sm_{t-1} + (1-λ) * beta_hat_t`

Остаток:

`eps_t = r_eth_t - (alpha_hat_t + beta_sm_t * r_btc_t)`

Кумулятивное очищенное изменение за 60 минут в лог‑пространстве:

`Delta_res_60 = sum_{i=t-59}^{t} eps_i`
Процент: `pct = exp(Delta_res_60) - 1`

**Сигнал:** если `abs(pct) ≥ 1%`, то печатаем событие.

### 1.2. Параметры и обоснование

* **Таймфрейм:** 1m — компромисс между задержкой и устойчивостью (тик‑данные слишком шумные).
* **Окно OLS `W` = 240 баров (\~4 ч):** даёт устойчивую оценку беты, но остаётся достаточно адаптивным к дрейфу режимов.
* **Прогрев:** минимум 120 наблюдений — до этого сигналы не выдаются.
* **EWMA:** `λ = 0.94` (эффективная память \~16 баров) — сглаживает скачки.
* **Winsorize доходностей:** 1‑й и 99‑й перцентили — уменьшаем влияние выбросов без тяжёлых робастных регрессий.
* **Метрика 60 мин:** скользящая сумма остатков — фокус на «внутреннем» тренде ETH за последний час.
* **Порог, гистерезис и кулдаун:** порог 1%, гистерезис 0.2%, кулдаун 30 мин — снижает дребезг на границе.
* **Заморозка беты:** при Var(r\_btc) ≈ 0 на окне — удерживаем последнюю валидную β.

### 1.3. Альтернатива: бета‑нейтрализация цены

Для валидации и удобства интерпретации можно строить синтетическую цену ETH, нейтрализованную по BTC:

`P*_eth_t = P_eth_t / (P_btc_t ^ beta_t)`

Тогда проверяем: `abs(P*_t / P*_{t-60} - 1) ≥ 1%`. На практике даёт те же моменты, что и метод остатков.

---

## 2. Архитектура

```
Binance WS (kline_1m ETH,BTC)
        │
        ▼
  Parser/Normalizer  →  In‑Memory Ring Buffers (ETH,BTC, ≥300 баров)
        │                                │
        │                                ├─ Returns (log, winsorize)
        │                                └─ Rolling OLS (W=240) + EWMA β
        │                                               │
        ▼                                               ▼
     Orchestrator ─────────► Residuals ε_t ──► Cum(60m) ──► Signal Engine
                                                │               │
                                         PostgreSQL (SQLAlchemy)  Console + JSON log
```

Модули:

* `data/binance_ws.py` — подписка WS, reconnect, ping/pong, backoff.
* `domain/bars.py` — нормализация и валидации 1m‑свечей.
* `domain/returns.py` — расчёт лог‑доходностей и winsorization.
* `analytics/beta.py` — роллинг‑OLS, EWMA, метрики R², контроль деградации.
* `analytics/residuals.py` — остатки и кумулятивные изменения 60m.
* `analytics/signal.py` — порог, гистерезис, кулдаун, формат сообщения.
* `data/storage.py` — **SQLAlchemy ORM для PostgreSQL**, батч‑вставки, авто‑создание таблиц при старте.
* `app/runner.py` — точка входа, цикл обработки событий.

Все публичные функции и классы снабжены **docstring** и **аннотациями типов**.

---

## 3. Установка и запуск

### 3.1. Быстрый старт (Poetry + локально, DB в Docker)

```bash
# 1) Клонируем репозиторий
git clone <this-repo-url> && cd <repo>

# 2) Poetry и окружение
poetry env use 3.11
poetry install --no-root

# 3) Конфиг
cp .env.example .env
# при необходимости правим DATABASE_URL на localhost:5432

# 4) Поднимаем PostgreSQL отдельно через compose
docker compose up -d db

# 5) Запускаем приложение локально
poetry run python -m src.app.runner
```

### 3.2. Docker / Docker Compose (app+db)

```bash
# Полный запуск (приложение + база)
docker compose up --build
```

Приложение инициализирует схемы БД (SQLAlchemy `create_all`) при старте.

### 3.3. Переменные окружения

`.env.example`:

```
# Binance
BINANCE_WS_URL=wss://stream.binance.com:9443/stream
BINANCE_STREAMS=ethusdt@kline_1m/btcusdt@kline_1m

# Параметры методики
WINDOW_OLS=240
WARMUP_MIN=120
EWMA_LAMBDA=0.94
RESID_WINDOW_MIN=60
SIGNAL_THRESHOLD_PCT=1.0
HYSTERESIS_PCT=0.2
COOLDOWN_MIN=30

# БД (compose)
POSTGRES_DB=ethid
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# SQLAlchemy URL (psycopg3)
DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/ethid
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_ECHO=False

# Логи
LOG_LEVEL=INFO
LOG_JSON=true
```

---

## 4. Использование

После запуска сервис подписывается на минутные свечи ETHUSDT и BTCUSDT, на каждом закрытии 1‑минутной свечи:

1. обновляет буферы и доходности;
2. пересчитывает β по роллинг OLS и сглаживает EWMA;
3. получает остаток ε\_t и кумулятив Δ\_res\_60;
4. проверяет порог 1% (с гистерезисом/кулдауном);
5. печатает событие при срабатывании и сохраняет в PostgreSQL (таблица `signals`).

Остановка — `Ctrl+C`. При обрыве WS выполняется авто‑переподключение с экспоненциальным backoff.

---

## 5. Качество кода: типы, докстринги, линтеры

Проект придерживается **PEP 8**, обязательные **аннотации типов** и **docstring** (Google‑style или NumPy‑style). Включены:

Команды (Poetry):

```bash
# Форматирование (Ruff formatter)
poetry run ruff format .

# Линт + авто-исправления (flake8 + isort правила)
poetry run ruff check --fix .

# Типы
poetry run mypy src

# Тесты
poetry run pytest -q --cov=src --cov-report=term-missing
```

Конфигурации:

```ini
# pyproject.toml (фрагмент)
[tool.poetry]
packages = [{ include = "src", from = "." }]

[tool.ruff]
line-length = 119
target-version = "py311"
exclude = ["tests/fixtures"]

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "UP", "ANN"]
ignore = ["E203"]
fixable = ["ALL"]

[tool.ruff.lint.isort]
known-first-party = ["src", "ethid"]
combine-as-imports = true

[tool.mypy]
python_version = "3.11"
strict_optional = true
warn_unused_ignores = true
warn_redundant_casts = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
no_implicit_optional = true
plugins = []

[tool.pytest]
addopts = "-q --cov=src --cov-report=term-missing"
testpaths = ["tests"]
asyncio_mode = "auto"
```

---

## 6. Тестирование

* **Unit‑тесты:** парсинг kline→bar, лог‑доходности, winsorize, OLS/β, EWMA, остатки, кумулятив 60m, логика сигнала.
* **Property‑тесты:** синтетика `ETH = 0.8 * BTC + шум(σ)` → при σ→0 остатки→0, β→0.8.
* **Интеграционные:** record\&replay WS, разрывы соединения, пропуски/дубликаты свечей, freeze β при Var≈0.

Запуск:

```bash
poetry run pytest -q --cov=src --cov-report=term-missing
```

Coverage‑цель: **≥ 75%**.

---

## 7. Логи и формат сигналов

Короткая строка в консоль и JSON‑лог (если `LOG_JSON=true`). Пример:

```json
{
  "ts": "2025-09-20T12:31:00Z",
  "event": "ETH_OWN_MOVE",
  "window_min": 60,
  "res_change_pct": 1.27,
  "beta": 0.78,
  "r2": 0.64,
  "cooldown_active": false
}
```

Консоль:

```
[ETH OWN MOVE] +1.27% за 60м | beta=0.78 R2=0.64 | t=2025-09-20 12:31Z
```

---

## 8. Roadmap и допущения

* Робастные регрессии (Huber/Quantile) для хвостов.
* Коинтеграция/спред‑модели как альтернатива/усложнение.
* Экспорт метрик в Prometheus/Grafana.
* Алёрты в Telegram/webhook.

**Допущения:** работаем на закрытиях 1‑мин свечей; публичный WS достаточен; при Var(BTC)≈0 β замораживается; **PostgreSQL обязателен** (таблицы создаются автоматически при старте).

---

## 9. Лицензия

MIT (или укажите иную подходящую).
