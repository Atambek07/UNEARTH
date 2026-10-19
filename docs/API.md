# UNEARTH — Справочник REST API

Полная спецификация API симулятора **UNEARTH — Smart LFG-to-Energy & Computational Grid Simulator**.
Версия API: **v0.2.2** (октябрь 2026). Все примеры ответов в документе — реальные вызовы работающего
сервиса (дефолты Бишкека, `seed = 42`, live-провайдер CoinGecko/mempool.space на момент съёмки).

- Базовый URL: `http://localhost:8000`
- Формат: JSON (UTF-8); запросы — `POST` с `Content-Type: application/json`
- Swagger UI: `http://localhost:8000/docs`
- Машиночитаемая спека OpenAPI 3.1: [`docs/openapi.json`](openapi.json) — импортируется в Postman/Insomnia
- Аутентификация: отсутствует (MVP); CORS открыт для всех источников
- Детерминизм: все ML/Монте-Карло расчёты фиксируются параметром `seed`

> Симуляционные данные, не инвестиционная рекомендация. Фискальный блок — упрощённая модель,
> не налоговая консультация (см. §10).

---

## Содержание

1. [Общие правила](#1-общие-правила)
2. [Конфигурация окружения](#2-конфигурация-окружения)
3. [Ошибки и валидация](#3-ошибки-и-валидация)
4. [GET /api/health](#4-get-apihealth)
5. [GET /api/market/current](#5-get-apimarketcurrent)
6. [POST /api/forecast](#6-post-apiforecast)
7. [POST /api/optimize](#7-post-apioptimize)
8. [POST /api/optimize/path](#8-post-apioptimizepath)
9. [POST /api/maintenance](#9-post-apimaintenance)
10. [POST /api/finance](#10-post-apifinance)
11. [POST /api/carbon](#11-post-apicarbon)
12. [POST /api/sectors](#12-post-apisectors)
13. [Сценарии и БД](#13-сценарии-и-бд)
14. [POST /api/simulation/run](#14-post-apisimulationrun)
15. [Приложение A. Формулы](#15-приложение-a-формулы)
16. [Приложение B. Конвейер интеграции](#16-приложение-b-конвейер-интеграции)
17. [Приложение C. Изменения v0.1 → v0.2](#17-приложение-c-изменения-v01--v02)

---

## 1. Общие правила

| Правило | Значение |
|---|---|
| Префикс всех маршрутов | `/api` |
| Формат чисел | float; в ответах округление до 1–3 знаков (деньги — до цента) |
| Единицы | мощность — МВт (в плане также кВт·ч/сутки в марже), энергия — МВт·ч, газ — м³, деньги — USD |
| Время | горизонт строится от первого месяца после текущей даты; `fetched_at` — ISO-8601 UTC |
| Детерминизм | `seed` (по умолчанию 42) фиксирует ML-модель, синтетику рынка и Монте-Карло |
| Ограничения длин | `forecast`: 3–25 лет; `optimize/path`: 3–600 месяцев; `carbon`: длина кратна 12; `finance`: `horizon_years × 12` |
| Идемпотентность | `POST` не меняет состояние, кроме `/api/scenarios` (запись в БД) |
| Rate limit | не реализован (MVP); live-рынок кэшируется на 10 минут |

**Быстрый старт (PowerShell)**

```powershell
$body = @{ horizon_years = 5; seed = 42 } | ConvertTo-Json
Invoke-RestMethod -Uri 'http://localhost:8000/api/forecast' -Method Post `
  -ContentType 'application/json' -Body $body
```

---

## 2. Конфигурация окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `UNEARTH_DB_PATH` | `backend/data/unearth.db` | Файл SQLite для сценариев (создаётся автоматически) |
| `UNEARTH_DB_URL` | — | PostgreSQL DSN (`postgres://…`); требует `pip install "psycopg[binary]"`. Приоритетнее файла |

Константы, влияющие на сеть и кэш (меняются в `backend/app/config.py`):

| Константа | Значение | Смысл |
|---|---|---|
| `MARKET_TTL_SECONDS` | 600 | TTL кэша live-котировок |
| `MARKET_HTTP_TIMEOUT_S` | 5.0 | Таймаут каждого источника |
| `GPU_RENT_DEFAULT` | 2.0 | Рента GPU, $/GPU·ч — **справочная величина**, live-API для неё нет |

---

## 3. Ошибки и валидация

| Код | Когда | Тело |
|---|---|---|
| 200 / 201 | Успех (201 — создание сценария) | JSON из разделов ниже |
| 404 | Сценарий не найден | `{"detail": "сценарий не найден"}` |
| 422 | Нарушены ограничения Pydantic или бизнес-правила | `{"detail": [...]}` (pydantic v2) либо `{"detail": "текст"}` |
| 500 | Непредвиденная ошибка движка | `{"detail": "…"}` |

**Пример 422 (несовпадение длин в плане)**

```json
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body"],
      "msg": "Value error, monthly_moisture должен совпадать по длине с monthly_power_mw",
      "input": { "monthly_power_mw": [13.0, 13.0, 13.0], "monthly_moisture": [1.0] }
    }
  ]
}
```

**Пример 422 (базовый тип поля)**

```json
{
  "detail": [
    { "type": "greater_than", "loc": ["body", "available_mw"],
      "msg": "Input should be greater than 0", "input": -5, "ctx": { "gt": 0.0 } }
  ]
}
```

---

## 4. GET /api/health

Живость сервиса и наличие опционального Prophet.

```json
{ "status": "ok", "prophet_available": false, "version": "0.2.2" }
```

| Поле | Тип | Описание |
|---|---|---|
| `status` | string | `"ok"` |
| `prophet_available` | bool | Установлен ли пакет Prophet |
| `version` | string | Версия пакета `app` |

---

## 5. GET /api/market/current

Текущее состояние рынка: live-котировки BTC и хешрейта сети либо синтетика, плюс ML-прогноз
доходности на 3 месяца. **Внимание:** рента GPU — справочная константа (2 $/GPU·ч), не live.

### Query-параметры

| Параметр | Тип | По умолчанию | Описание |
|---|---|---|---|
| `provider` | string | `auto` | `auto` — live с откатом на синтетику; `live` — только live (при сбое — дефолты с пометкой); `synthetic` — детерминированная синтетика |
| `seed` | int | 42 | Seed ML-модели прогноза доходности |

### Ответ

```json
{
  "provider_requested": "auto",
  "source": "live",
  "btc_price_usd": 82800.0,
  "network_hashrate_ths": 1020230400.1,
  "network_hashrate_default_ths": null,
  "gpu_rent_usd_per_gpu_hour": 2.0,
  "predicted_3m_return": 0.0346,
  "miner_margin_multiplier": 1.017,
  "regime": "neutral",
  "fetched_at": "2026-10-19T06:41:36Z",
  "notes": ["из кэша (TTL 10 мин)"],
  "disclaimer": "Симуляционные данные, не инвестиционная рекомендация."
}
```

| Поле | Описание |
|---|---|
| `source` | `live` — данные получены из публичных API; `synthetic` — откат |
| `btc_price_usd` | Курс BTC, USD |
| `network_hashrate_ths` | Хешрейт сети, TH/s (live); `null` для синтетики |
| `network_hashrate_default_ths` | Константа 7·10⁸ TH/s, если live-значения нет |
| `gpu_rent_usd_per_gpu_hour` | Рента GPU (константа) |
| `predicted_3m_return` | ML-прогноз доходности BTC на 3 мес |
| `miner_margin_multiplier` | Риск-дисконт маржи майнинга (0.25–1.5) |
| `regime` | `bearish` / `neutral` / `bullish` |
| `fetched_at` | Время live-снимка (UTC) или `null` |
| `notes` | Причины отката, кэш и прочие пометки |

**Источники и порядок отката**

| Поле | Основной | Резерв | Дефолт |
|---|---|---|---|
| BTC | CoinGecko `simple/price` | Coinbase `prices/BTC-USD/spot` | 65 000 $ |
| Хешрейт | mempool.space `/mining/hashrate/3d` | blockchain.info `difficulty × 2³² / 600` | 7·10⁸ TH/s |

> `provider=auto` отдаёт live, если оба поля получены; иначе — синтетика с пометкой в `notes`.
> `provider=live` возвращает `source: "live"` даже при частичном сбое, если хотя бы одно поле живое,
> а `notes` перечисляет, что именно упало.

---

## 6. POST /api/forecast

Модуль 1. Физическая кривая LandGEM (EPA, first-order decay) + ML-сезонность с 95 % CI.

### Тело запроса (`ForecastRequest`)

| Поле | Тип | По умолчанию | Ограничения | Описание |
|---|---|---|---|---|
| `total_legacy_tonnes` | float | 20 000 000 | > 0 | Накопленные ТБО, т |
| `annual_inflow_tonnes` | float | 375 000 | ≥ 0 | Приток, т/год |
| `lo_m3_per_tonne` | float | 75 | > 0 | L₀, м³ CH₄/т |
| `k_per_year` | float | 0.03 | 0.001–0.5 | Скорость разложения, 1/год |
| `methane_fraction` | float | 0.52 | (0, 1) | Доля CH₄ в газе |
| `horizon_years` | int | 15 | 3–25 | Горизонт, лет |
| `collection_efficiency` | float | 0.75 | (0, 1] | Доля отбора газа |
| `genset_availability` | float | 0.92 | (0, 1] | Готовность ГПУ |
| `kwh_per_m3_ch4` | float | 3.5 | > 0 | кВт·ч эл. на м³ CH₄ |
| `use_prophet` | bool | false | — | Пробовать Prophet, если установлен |
| `seed` | int | 42 | ≥ 0 | Детерминизм ML |

### Ответ (реальный вызов, горизонт 5 лет)

```json
{
  "meta": {
    "model": "builtin-seasonal-ar1",
    "prophet_used": false,
    "history_months": 48,
    "ar1_rho": 0.535,
    "sigma_innov": 0.0174,
    "seasonal_index": [0.925, 0.931, 0.935, 0.938, 0.977, 0.98, 0.998, 1.028, 1.146, 1.138, 1.048, 0.957],
    "seed": 42,
    "notes": []
  },
  "annual": [
    { "year": 1, "label": "2026",
      "landgem_ch4_m3": 50101324.4, "forecast_ch4_m3": 49946579.0,
      "ci_lower": 47882139.3, "ci_upper": 52100442.9,
      "energy_mwh": 120621.0, "avg_power_mw": 13.77 }
  ],
  "monthly": [
    { "idx": 0, "label": "2026-11", "year": 2026, "month": 11,
      "landgem_ch4_m3": 4200396.3, "forecast_ch4_m3": 4327198.2,
      "ci_lower": 4180683.4, "ci_upper": 4478847.7,
      "moisture_index": 1.087, "energy_mwh": 10450.2, "avg_power_mw": 14.315 }
  ],
  "summary": {
    "year1_avg_power_mw": 13.77,
    "year1_energy_mwh": 120621.0,
    "year5_avg_power_mw": 13.131,
    "year_last_avg_power_mw": 13.131,
    "peak_power_mw": 15.748,
    "horizon_total_ch4_m3": 244084020.2,
    "horizon_total_energy_mwh": 589462.9
  }
}
```

| Поле | Описание |
|---|---|
| `meta.model` | `builtin-seasonal-ar1` или `prophet` |
| `meta.seasonal_index[12]` | Индексы по месяцам (среднее = 1); сентябрь–октябрь ≈ 1.14–1.15 — осенний пик |
| `annual[].landgem_ch4_m3` | Чистая физика (базовая кривая), м³ CH₄/год |
| `annual[].forecast_ch4_m3` | Гибридный прогноз, м³ CH₄/год |
| `annual[].ci_lower/ci_upper` | Границы 95 % CI |
| `annual[].energy_mwh` | Электроэнергия года, МВт·ч |
| `annual[].avg_power_mw` | Средняя мощность года (`energy_mwh / 8760`) |
| `monthly[]` | Месячный ряд + `moisture_index` (влажность массива) |
| `summary` | Мощность года 1/5/последнего, пик, суммарные объёмы |

---

## 7. POST /api/optimize

Модуль 2а. Одномоментный балансировщик: распределяет мощность между ИИ-серверами и Antminer S19 Pro
по марже на кВт·день. Учитывает качество газа, ML-прогноз BTC и ёмкость рынка аренды GPU.

### Тело запроса (`OptimizeRequest`)

| Поле | Тип | По умолчанию | Ограничения | Описание |
|---|---|---|---|---|
| `available_mw` | float | — | 0 < x ≤ 500 | Доступная мощность, МВт |
| `ch4_fraction` | float | 0.52 | (0, 1) | Доля CH₄ |
| `h2s_ppm` | float | 30 | 0–1000 | H₂S → derate мощности |
| `btc_price` | float \| null | null | > 0 | Курс; `null` → из провайдера рынка. **Явное значение перекрывает live** |
| `gpu_rent_usd_per_gpu_hour` | float \| null | null | > 0 | Рента GPU; `null` → константа 2.0 |
| `market_provider` | string | `synthetic` | `auto`/`live`/`synthetic` | Источник рынка |
| `mode` | string | `auto` | `auto`/`manual` | Режим распределения |
| `manual_miners` | int | 0 | 0–100 000 | Парк ASIC в ручном режиме |
| `manual_ai_servers` | int | 0 | 0–100 000 | Парк ИИ-серверов в ручном режиме |
| `gpu_demand_cap` | int | 1000 | 0–1 000 000 | Ёмкость рынка аренды GPU, шт |
| `seed` | int | 42 | ≥ 0 | Seed ML-модели |

### Ответ (реальный вызов: `available_mw=13.77`, `h2s_ppm=45`, синтетика)

```json
{
  "available_mw": 13.77,
  "allocatable_mw": 10.135,
  "quality": { "ch4_fraction": 0.52, "h2s_ppm": 45.0,
               "stability": 0.8, "h2s_penalty": 0.0,
               "derate_factor": 0.8, "stable": true },
  "market": { "btc_price": 65000.0, "gpu_rent_usd_per_gpu_hour": 2.0,
              "predicted_3m_return": 0.0346, "miner_margin_multiplier": 1.017,
              "regime": "neutral", "source": "synthetic", "fetched_at": null,
              "network_hashrate_ths": null,
              "notes": ["Синтетический рынок (по ТЗ MVP)"] },
  "margins": { "mining_usd_per_kw_day": 1.0, "ai_usd_per_kw_day": 63.58 },
  "allocation": [
    { "node_type": "ai_server", "label": "ИИ-сервер (2×GPU, 1.5 кВт)",
      "count": 500, "unit_power_kw": 1.5, "power_mw": 0.862,
      "revenue_usd_day": 48000.0, "margin_usd_day": 47685.0,
      "margin_per_kw_day": 63.58, "status": "running" },
    { "node_type": "antminer_s19_pro", "label": "Antminer S19 Pro (110 TH/s, 3.25 кВт)",
      "count": 2480, "unit_power_kw": 3.25, "power_mw": 9.269,
      "revenue_usd_day": 11228.16, "margin_usd_day": 7842.96,
      "margin_per_kw_day": 1.0, "status": "running" }
  ],
  "used_mw": 10.131,
  "curtailed_mw": 0.004,
  "overcommitted": false,
  "manual": false,
  "shutdown_order": ["Antminer S19 Pro (110 TH/s, 3.25 кВт)", "ИИ-сервер (2×GPU, 1.5 кВт)"],
  "rationale": [
    "Доступно 13.77 МВт; derate по качеству газа ×0.80 (CH4 52 %, H2S 45 ppm)",
    "Собственные нужды (скрубберы, насосы) −8 %, PUE ЦОД 1.15 → распределяется по ИТ-нагрузке",
    "ML-прогноз BTC на 3 мес: +3.5% → множитель маржи майнинга ×1.02",
    "Маржа на кВт·день: ИИ $63.58 против майнинга $1.00",
    "Ёмкость рынка аренды: 1000 GPU → максимум 500 ИИ-серверов"
  ]
}
```

| Поле | Описание |
|---|---|
| `allocatable_mw` | `available_mw × derate × 0.92` (8 % — собственные нужды) |
| `quality.derate_factor` | Стабильность горения (CH₄ ≥ 40 %) × штраф за H₂S (> 50 ppm) |
| `market.source` | Какой рынок реально применён (`live`/`synthetic`) и его пометки |
| `allocation[].count` | Количество узлов; порядок — по убыванию маржи |
| `margin_per_kw_day` | $ на кВт в сутки — критерий ранжирования |
| `overcommitted` | `true` в ручном режиме, если парк превышает `allocatable_mw` |
| `shutdown_order` | Порядок отключения при падении мощности/качества (по возрастанию маржи) |

> Формулы маржи, амортизации и derate — [Приложение A](#15-приложение-a-формулы).

---

## 8. POST /api/optimize/path

Модуль 2а+. **Упреждающий план на горизонт** (динамическое программирование по месяцам).
На каждом шаге кандидаты — «жадный план под текущую мощность» и «удержать прошлый план, обрезанный
под мощность»; переход между планами стоит фиксированную сумму за узел. Резерв мощности закладывается
заранее по влажности **следующего** месяца — под осенний пик бахчевых. Помесячный путь цены BTC
позволяет удержать парк в временном провале, если потеря маржи дешевле переключений.

### Тело запроса (`OptimizePathRequest`)

| Поле | Тип | По умолчанию | Ограничения | Описание |
|---|---|---|---|---|
| `monthly_power_mw` | float[] | — | 3–600 значений, > 0 | Доступная мощность по месяцам |
| `monthly_moisture` | float[] \| null | null | длина = мощности | Индекс влажности по месяцам |
| `monthly_btc_price` | float[] \| null | null | длина = мощности, > 0 | Ожидаемый путь BTC |
| `ch4_fraction` | float | 0.52 | (0, 1) | Доля CH₄ |
| `h2s_ppm` | float | 30 | 0–1000 | H₂S |
| `btc_price` | float \| null | null | > 0 | Базовая цена (если нет пути) |
| `gpu_rent_usd_per_gpu_hour` | float \| null | null | > 0 | Рента GPU |
| `market_provider` | string | `synthetic` | — | Источник рынка |
| `gpu_demand_cap` | int | 1000 | 0–1 000 000 | Ёмкость аренды GPU |
| `seed` | int | 42 | ≥ 0 | Seed ML |
| `switching_cost_miner_usd` | float | 20.0 | 0–100 000 | Стоимость переключения одного ASIC |
| `switching_cost_ai_usd` | float | 150.0 | 0–1 000 000 | Стоимость переключения ИИ-сервера |

### Ответ (фрагмент реального вызова; 12 месяцев, H₂S 45 ppm)

```json
{
  "months": 12,
  "quality": { "derate_factor": 0.8, "stable": true, "…": "…" },
  "market": { "btc_price": 65000.0, "predicted_3m_return": 0.0346,
              "miner_margin_multiplier": 1.017, "regime": "neutral",
              "source": "synthetic", "notes": ["Синтетический рынок (по ТЗ MVP)"] },
  "margins": { "mining_usd_per_kw_day": 1.0, "ai_usd_per_kw_day": 63.58 },
  "plan": [
    { "month": 1, "ai_servers": 500, "miners": 2429, "used_mw": 9.941,
      "allocatable_mw": 9.944, "reserve_share": 0.056, "moisture_next": 1.027,
      "margin_usd_day": 55553.62, "plan": "greedy" },
    { "month": 10, "ai_servers": 500, "miners": 2204, "used_mw": 9.1,
      "allocatable_mw": 9.104, "reserve_share": 0.126, "moisture_next": 1.143,
      "margin_usd_day": 54824.75, "plan": "greedy" },
    { "month": 11, "ai_servers": 500, "miners": 2459, "used_mw": 10.053,
      "allocatable_mw": 10.056, "reserve_share": 0.132, "moisture_next": 1.154,
      "margin_usd_day": 55650.81, "plan": "greedy" }
  ],
  "switch_events": [
    { "month": 2, "added_miners": 0, "removed_miners": 172,
      "added_ai": 0, "removed_ai": 0, "cost_usd": 3440.0 },
    { "month": 11, "added_miners": 255, "removed_miners": 0,
      "added_ai": 0, "removed_ai": 0, "cost_usd": 5100.0 }
  ],
  "switching_costs": { "per_miner_usd": 20.0, "per_ai_usd": 150.0, "total_usd": 139240.0 },
  "totals": {
    "optimized_margin_usd": 20131401.76,
    "optimized_switch_cost_usd": 139240.0,
    "optimized_net_usd": 19992161.76,
    "naive_margin_usd": 20131401.76,
    "naive_switch_cost_usd": 139240.0,
    "naive_net_usd": 19992161.76,
    "improvement_usd": 0.0
  },
  "reserve_policy": { "base_share": 0.04, "max_share": 0.16, "moisture_scale": 0.2 },
  "disclaimer": "Симуляционные данные, не инвестиционная рекомендация."
}
```

| Поле | Описание |
|---|---|
| `plan[].reserve_share` | Доля резерва под нестабильность следующего месяца (0.04 → 0.16 линейно по влажности) |
| `plan[].plan` | `greedy` — план пересчитан под месяц; `hold` — удержан прошлый (дешевле переключений) |
| `plan[].margin_usd_day` | Маржа плана, $/сутки |
| `switch_events[]` | Изменения парка относительно прошлого месяца и их стоимость |
| `totals.improvement_usd` | Выигрыш DP против наивного помесячного greedy (может быть 0, если пути совпали) |
| `reserve_policy` | Параметры политики резерва из `config.py` |

> Стоимость переключений в DP сравнивается с **месячной** маржой (маржа дня × 30.44) — иначе
> разовые затраты визуально «перевешивали» бы и парк не отключался в провалах.

---

## 9. POST /api/maintenance

Модуль 2б. Износ ГПУ от H₂S, ресурс скрубберов, OPEX.

### Тело запроса (`MaintenanceRequest`)

| Поле | Тип | По умолчанию | Ограничения | Описание |
|---|---|---|---|---|
| `installed_mw` | float | — | 0 < x ≤ 500 | Установленная мощность ГПУ |
| `ch4_m3_month` | float | — | > 0 | CH₄ на ГПУ за месяц, м³ |
| `h2s_ppm` | float | 30 | 0–1000 | H₂S на входе |
| `methane_fraction` | float | 0.52 | (0, 1) | Доля CH₄ (пересчёт LFG) |
| `months_operated` | int | 6 | 0–600 | Наработка парка, мес |
| `genset_availability` | float | 0.92 | (0, 1] | Готовность ГПУ |
| `kwh_per_m3_ch4` | float | 3.5 | > 0 | Удельная отдача |

### Ответ (фрагмент, H₂S 45 ppm)

```json
{
  "installed_mw": 13.77, "genset_count": 14, "genset_rating_mw": 1.0,
  "wear_pct_month": 0.77,
  "gas": { "lfg_flow_m3_month": 6241158.97, "h2s_ppm": 45.0, "sulfur_load_kg_month": 432.23 },
  "generators": [
    { "id": "JEN-01", "health_score": 98.5, "wear_pct_month": 0.77,
      "rul_months": 107.8, "failure_risk_12m": 0.05, "status": "healthy" }
  ],
  "fleet_health_score": 92.3,
  "scrubber": { "beds": 14, "bed_capacity_kg": 900.0, "total_capacity_kg": 12600.0,
                "load_kg_month": 432.23, "life_months": 29.2,
                "replacements_per_year": 0.41, "cost_per_replacement_usd": 28000.0,
                "annual_cost_usd": 11526.16 },
  "energy_mwh_month": 11132.9,
  "opex_monthly_usd": {
    "scrubbing_usd": 13447.18, "consumables_usd": 47025.83,
    "labor_usd": 11666.67, "insurance_usd": 17909.58,
    "plant_depreciation_usd": 149246.53, "overhaul_reserve_usd": 10500.0,
    "total_usd": 249795.79
  },
  "opex_variable_annual_usd": 851676.13,
  "opex_fixed_annual_usd": 2145873.41,
  "opex_annual_usd": 2997549.54
}
```

| Поле | Описание |
|---|---|
| `wear_pct_month` | `0.35 %/мес × (H₂S/25)^1.35` |
| `generators[]` | Health = 100 − износ × наработка (разброс ±4 мес); RUL; риск отказа 12 мес; статус |
| `scrubber.life_months` | Ёмкость всех загрузок / месячная загрузка серы |
| `opex_variable_annual_usd` | Переменная часть OPEX — вход для `/api/finance` |
| `opex_fixed_annual_usd` | ФОТ + страхование + амортизация станции |

---

## 10. POST /api/finance

Модуль 2в. CAPEX по статьям, Монте-Карло рынка, P10/P50/P90, дисконтированный поток (WACC 10 %),
окупаемость, IRR, CO₂, Фонд озеленения, **фискальный блок КР** и **валютный блок**.

### Тело запроса (`FinanceRequest`)

| Поле | Тип | По умолчанию | Ограничения | Описание |
|---|---|---|---|---|
| `horizon_years` | int | — | 3–25 | Горизонт |
| `monthly_power_mw` | float[] | — | длина = `horizon×12` | Мощность по месяцам |
| `monthly_ch4_m3_delivered` | float[] | — | длина = той же | CH₄ на ГПУ по месяцам |
| `miners_count` | int | — | ≥ 0 | Парк ASIC |
| `ai_servers_count` | int | — | ≥ 0 | Парк ИИ-серверов |
| `btc_price` | float | 65 000 | > 0 | Стартовый курс BTC |
| `gpu_rent_usd_per_gpu_hour` | float | 2.0 | > 0 | Рента GPU |
| `opex_variable_annual_usd` | float | 0 | ≥ 0 | Переменный OPEX (из maintenance) |
| `opex_fixed_annual_usd` | float | 0 | ≥ 0 | Постоянный OPEX (из maintenance) |
| `seed` | int | 42 | ≥ 0 | Seed Монте-Карло |
| `n_sims` | int | 400 | 50–2000 | Траекторий |
| `fiscal_regime` | string | `kr_htp` | `none`/`kr_general`/`kr_htp`/`kz_aifc` | Налоговый режим (КР или Astana Hub) |
| `fx` | object \| null | null | см. §10.1 | Валютный блок: курс, спред, репатриация, хедж |

### Ответ (реальный вызов, 5 лет, ПВТ)

```json
{
  "capex_total_usd": 34853584,
  "capex_breakdown": [
    { "item": "Скважины и система газосбора", "usd": 1900000 },
    { "item": "Газопоршневые ГПУ (14 × 1 МВт)", "usd": 10327500 }
  ],
  "annual": [
    { "year": 1,
      "revenue_p10_usd": 20303403, "revenue_p50_usd": 21756384, "revenue_p90_usd": 23941293,
      "opex_usd": 2997550,
      "net_profit_p10_usd": 17305854, "net_profit_p50_usd": 18758834, "net_profit_p90_usd": 20943744,
      "cumulative_cashflow_p50_usd": -17800098,
      "co2_avoided_t": 780765.0, "green_fund_usd": 937942, "trees_planted": 234485 }
  ],
  "chart": [
    { "label": "Y0", "capex_usd": 34853584, "opex_usd": 0,
      "net_profit_p50_usd": 0, "cumulative_cashflow_p50_usd": -34853584 }
  ],
  "payback_years": 2.2,
  "irr": 0.443,
  "wacc": 0.1,
  "revenue_split": { "mining_p50_usd": [3948763], "ai_p50_usd": [17807620] },
  "totals": {
    "net_profit_p50_usd": 91151216,
    "co2_avoided_t": 3670047.3,
    "…": "…"
  },
  "fiscal": {
    "regime": "kr_htp",
    "years": [
      { "regime": "kr_htp",
        "lines": [
          { "item": "Взнос в дирекцию ПВТ (1 % выручки IT)", "base_usd": 17807620.0,
            "rate": 0.01, "amount_usd": 178076.2, "note": "вместо налога на прибыль/НДС/налога с продаж" },
          { "item": "Налог на майнинг (10 % от стоимости э/э)", "base_usd": 4895537.03,
            "rate": 0.1, "amount_usd": 489553.7, "note": "майнинг вне профильной деятельности ПВТ" },
          { "item": "Подоходный налог с ФОТ (ПВТ, 5 %)", "base_usd": 140000.0,
            "rate": 0.05, "amount_usd": 7000.0, "note": "упрощённо с ФОТ" },
          { "item": "Плата за загрязнение ОС", "base_usd": 15000.0,
            "rate": 1.0, "amount_usd": 15000.0, "note": "годовой параметр (ASSUMPTION)" }
        ],
        "assumptions": { "mining_tariff_kgs_per_kwh": 6.06, "usd_kgs_rate": 87.4,
                         "tariff_usd_per_kwh": 0.06934, "env_fee_usd_year": 15000.0 },
        "taxes_total_usd": 689629.9,
        "net_profit_after_fiscal_usd": 18069204.1,
        "notes": ["Упрощённая фискальная модель; не налоговая консультация. …"] }
    ],
    "totals": { "taxes_total_usd": 3476347.92, "net_profit_after_fiscal_usd": 87674868.08 },
    "disclaimer": "Симуляционные данные, не инвестиционная рекомендация."
  },
  "fx": {
    "params": { "usd_kgs_rate": 87.4, "conversion_spread": 0.015,
                "repatriation_share": 1.0, "repatriation_cost_share": 0.005,
                "hedging_cost_share": 0.01 },
    "annual": [
      { "year": 1, "gross_usd": 21756384, "conversion_cost_usd": 326345.76,
        "repatriated_usd": 21756384.0, "repatriation_cost_usd": 108781.92,
        "hedging_cost_usd": 217563.84, "net_usd": 21103692.48,
        "kgs_received": 1844462722.75 }
    ],
    "totals": { "gross_usd": 106138963, "conversion_cost_usd": 1592084.44,
                "repatriation_cost_usd": 530694.81, "hedging_cost_usd": 1061389.63,
                "net_usd": 102954794.11, "kgs_received": 8998249005.21, "cost_share": 0.03 },
    "notes": ["Валютное регулирование КР параметризовано: …"],
    "disclaimer": "Симуляционные данные, не инвестиционная рекомендация."
  }
}
```

| Поле | Описание |
|---|---|
| `annual[].*_p10/p50/p90_usd` | Квантили Монте-Карло (400 траекторий BTC GBM + крэши, рента OU) |
| `annual[].cumulative_cashflow_p50_usd` | Дисконтированный поток (WACC 10 %), CAPEX в Y0 |
| `annual[].co2_avoided_t` | CH₄ × 0.716 кг/м³ × GWP-28 |
| `annual[].green_fund_usd` | 5 % положительной прибыли; `trees_planted` — по 4 $/саженец |
| `revenue_split` | Выручка AI/майнинг (P50) — база фискального блока |
| `fiscal.years[].lines[]` | Налоговые строки: база, ставка, сумма, пояснение |
| `fiscal.years[].assumptions` | Тариф майнинга в сомах, курс, тариф в USD, эко-платёж |
| `fiscal.totals` | Итог налогов и прибыль после налогов за горизонт |
| `fx.annual[].kgs_received` | Получено сомов после конвертации и издержек |

**Фискальные режимы**

| Режим | Что моделируется | Статус |
|---|---|---|
| `none` | Налоги не начисляются (pretax, как в v0.1) | — |
| `kr_general` | Налог на прибыль 10 % + налог на майнинг 10 % от стоимости э/э + плата за загрязнение ОС | КР, общий |
| `kr_htp` | ПВТ: взнос 1 % выручки IT, подоходный 5 % с ФОТ, майнинг отдельно (10 % от стоимости э/э), эко-платёж | КР, ПВТ |
| `kz_aifc` | Astana Hub (КЗ): 0 % КПН по IT-прибыли, КПН 20 % по майнинговой доле | Казахстан |

> Модель упрощённая и **не является налоговой консультацией**. Ставки и применимость
> режимов подтверждайте у консультанта; для `kz_aifc` действует отдельное предупреждение
> о риске постоянного представительства в КР.

### 10.1. Валютный блок

Два способа получить расчёт: поле `fx` в `/api/finance` (для выручки проекта по годам)
или отдельный эндпоинт `POST /api/currency` (для произвольного графика сумм).

**Тело запроса (`CurrencyRequest`)**

| Поле | Тип | По умолчанию | Ограничения | Описание |
|---|---|---|---|---|
| `annual_usd` | float[] | — | 1–30, ≥ 0 | Суммы по годам, USD |
| `usd_kgs_rate` | float | 87.4 | > 0, ≤ 1000 | Курс, сомов за 1 USD |
| `conversion_spread` | float | 0.015 | 0–0.2 | Спред конвертации |
| `repatriation_share` | float | 1.0 | 0–1 | Доля выручки, возвращаемая в КР |
| `repatriation_cost_share` | float | 0.005 | 0–0.2 | Стоимость репатриации/контроля |
| `hedging_cost_share` | float | 0.01 | 0–0.2 | Хеджирование валютного риска |

**Пример**

```json
// запрос: {"annual_usd": [1000000, 2000000]}
{
  "params": { "usd_kgs_rate": 87.4, "conversion_spread": 0.015,
              "repatriation_share": 1.0, "repatriation_cost_share": 0.005,
              "hedging_cost_share": 0.01 },
  "annual": [
    { "year": 1, "gross_usd": 1000000.0, "conversion_cost_usd": 15000.0,
      "repatriated_usd": 1000000.0, "repatriation_cost_usd": 5000.0,
      "hedging_cost_usd": 10000.0, "net_usd": 970000.0, "kgs_received": 84778000.0 },
    { "year": 2, "gross_usd": 2000000.0, "conversion_cost_usd": 30000.0,
      "repatriated_usd": 2000000.0, "repatriation_cost_usd": 10000.0,
      "hedging_cost_usd": 20000.0, "net_usd": 1940000.0, "kgs_received": 169556000.0 }
  ],
  "totals": { "gross_usd": 3000000.0, "conversion_cost_usd": 45000.0,
              "repatriation_cost_usd": 15000.0, "hedging_cost_usd": 30000.0,
              "net_usd": 2910000.0, "kgs_received": 254334000.0, "cost_share": 0.03 },
  "notes": ["Валютное регулирование КР параметризовано: …", "Курс и спред — входные параметры сценария, не прогноз."],
  "disclaimer": "Симуляционные данные, не инвестиционная рекомендация."
}
```

> Требования репатриации/обязательной продажи валютной выручки именно для КР
> **не подтверждены** в рамках этого обзора: модуль считает сценарии, а не
> юридическую обязанность. Проверяйте по действующей редакции закона и договору с банком.

### 10.2. Сравнение налоговых режимов

`POST /api/fiscal/compare` — одинаковый набор показателей, все четыре режима, выбор лучшего
по сумме налогов.

| Поле | Тип | По умолчанию | Описание |
|---|---|---|---|
| `profit_before_tax_usd` | float | 10 000 000 | Прибыль до налогов |
| `ai_revenue_usd` | float | 0 | Выручка ИИ-сегмента (база взноса ПВТ) |
| `mining_revenue_usd` | float | 0 | Выручка майнинга |
| `miners_energy_kwh_year` | float | 0 | Электроэнергия майнеров, кВт·ч/год |
| `labor_usd_year` | float | 0 | ФОТ (база 5 % ПВТ) |
| `fx_rate_kgs_per_usd` | float \| null | null | Курс для пересчёта тарифа |
| `pe_risk_share` | float \| null | 0.5 | Доля прибыли КЗ-юрлица, относимая к КР (риск ПП) |

**Реальный ответ (сокращённо)**

```json
{
  "assumptions": { "usd_kgs_rate": 87.4, "tariff_kgs_per_kwh": 6.06,
                    "tariff_usd_per_kwh": 0.06934, "kz_pe_profit_share": 0.5 },
  "regimes": [
    { "regime": "none", "taxes_total_usd": 0.0, "net_profit_after_fiscal_usd": 10000000.0 },
    { "regime": "kr_general", "taxes_total_usd": 1075738.67, "net_profit_after_fiscal_usd": 8924261.33 },
    { "regime": "kr_htp", "taxes_total_usd": 222738.67, "net_profit_after_fiscal_usd": 9777261.33 },
    { "regime": "kz_aifc", "taxes_total_usd": 1012683.12, "net_profit_after_fiscal_usd": 8987316.88 }
  ],
  "best_regime": "kr_htp",
  "notes": ["Сравнение по сумме налогов; не учитывает требования к структуре выручки…"],
  "disclaimer": "Симуляционные данные, не инвестиционная рекомендация."
}
```

В каждом режиме есть `lines[]` (по строкам налогов) и `notes[]` с применимыми
оговорками — их удобно показывать в интерфейсе рядом с выбором режима.

Для `kz_aifc` риск постоянного представительства в КР моделируется параметром
`pe_risk_share` (по умолчанию 50 %): эта доля прибыли казахстанского юрлица
облагается КПН КР 10 %, плюс начисляются майнинг-налог и доля эко-платежа.
Зачёт иностранного налога (foreign tax credit) не моделируется — оценка
консервативная.

## 11. POST /api/carbon

Карбоновый модуль: предотвращённые выбросы и углеродные кредиты по логике CDM ACM0001.
Базовая линия — вентирование метана; проект уничтожает CH₄ в ГПУ; CO₂e = масса CH₄ × GWP-28;
из выпуска вычитается буфер пула (20 %); кредиты года Y выпускаются с лагом верификации 12 мес;
учтены валидация, верификация, мониторинг и комиссия за выпуск; цены — P10/P50/P90.

### Тело запроса (`CarbonRequest`)

| Поле | Тип | По умолчанию | Ограничения | Описание |
|---|---|---|---|---|
| `monthly_ch4_m3_delivered` | float[] | — | ≥ 12, длина кратна 12, ≥ 0 | Уничтоженный CH₄ по месяцам |
| `gwp` | float | 28 | 0–100 | Потенциал глобального потепления |
| `buffer_share` | float | 0.20 | 0 ≤ x < 1 | Буферный вычет пула |
| `verification_lag_months` | int | 12 | 0–36, кратно 12 | Лаг выпуска кредитов |
| `price_p10` / `price_p50` / `price_p90` | float | 8 / 15 / 25 | > 0 | Цены кредитов, $/т |
| `validation_cost_usd` | float | 25 000 | ≥ 0 | Разовые затраты валидации |
| `verification_cost_usd_year` | float | 12 000 | ≥ 0 | Верификация, $/год |
| `monitoring_cost_usd_year` | float | 8 000 | ≥ 0 | Мониторинг, $/год |
| `issuance_fee_usd_per_credit` | float | 0.10 | ≥ 0 | Комиссия за выпуск, $/кредит |
| `discount_rate` | float | 0.10 | 0–0.5 | Ставка дисконтирования NPV |

### Ответ (реальный вызов, 5 лет)

```json
{
  "methodology": "CDM ACM0001 (landfill gas destruction), упрощённая модель",
  "params": { "gwp": 28.0, "buffer_share": 0.2, "verification_lag_months": 12,
              "discount_rate": 0.1, "issuance_fee_usd_per_credit": 0.1,
              "validation_cost_usd": 25000.0, "verification_cost_usd_year": 12000.0,
              "monitoring_cost_usd_year": 8000.0 },
  "annual": [
    { "year": 1, "ch4_destroyed_m3": 37459934.3, "ch4_destroyed_t": 26821.3,
      "baseline_co2e_t": 750996.8, "buffer_credits_t": 150199.4, "net_credits_t": 600797.4 }
  ],
  "totals": { "ch4_destroyed_t": 131073.1, "baseline_co2e_t": 3670047.3,
              "net_credits_t": 2936037.9, "buffer_credits_t": 734009.5 },
  "scenarios": {
    "p10": { "price_usd_per_t": 8.0, "npv_usd": 0.0, "total_revenue_usd": 0.0 },
    "p50": { "price_usd_per_t": 15.0, "npv_usd": 33141888.04,
             "total_revenue_usd": 43746964.22, "total_cash_usd": 43621964.22 },
    "p90": { "price_usd_per_t": 25.0, "npv_usd": 0.0, "total_revenue_usd": 0.0 }
  },
  "notes": [
    "Базовая линия — вентирование метана; проект уничтожает CH4 в ГПУ.",
    "Вытеснение электроэнергии сети не учитывается (проект off-grid).",
    "Буфер 20% и цены кредитов — допущения, настраиваются.",
    "Кредиты выпускаются с лагом верификации; выручка сдвинута.",
    "Карбоновая выручка не входит в /api/finance и не дублирует Фонд озеленения (5 % прибыли — отдельная ESG-программа)."
  ],
  "disclaimer": "Симуляционные данные, не инвестиционная рекомендация."
}
```

| Поле | Описание |
|---|---|
| `annual[].baseline_co2e_t` | Уничтоженный CH₄ (т) × GWP |
| `buffer_credits_t` | Буферный вычет (20 % по умолчанию) |
| `net_credits_t` | Кредиты к выпуску после буфера |
| `scenarios.p50.npv_usd` | NPV денежного потока кредитов при цене 15 $/т (лаг учтён) |
| `scenarios.*.cashflow_usd[]` | Поток по годам: [0] — валидация; далее — выпуск с комиссией минус верификация/мониторинг |

> Это расчёт **потенциала**, а не верифицированный выпуск: регистрация (VCS/Gold Standard/CDM),
> валидация и MRV выполняются внешними органами. Модуль не учитывает смещение выбросов сети
> (проект off-grid) и изменение запасов углерода.

---

## 12. POST /api/sectors

Карта секторов полигона: поток газа, H₂S, возраст массива и ML-прогноз нестабильности.

### Тело запроса (`SectorsRequest`)

| Поле | Тип | По умолчанию | Ограничения | Описание |
|---|---|---|---|---|
| `ch4_m3_delivered_month` | float | — | > 0 | CH₄ из секторов за месяц, м³ |
| `month` | int | 10 | 1–12 | Календарный месяц (осенний пик) |
| `rows` / `cols` | int | 6 / 8 | 2–20 | Размер сетки |
| `seed` | int | 42 | ≥ 0 | Seed модели |

### Ответ (фрагмент)

```json
{
  "rows": 6, "cols": 8, "month": 10,
  "sectors": [
    { "id": "S01", "row": 0, "col": 0, "age_class": "old",
      "ch4_flux_m3_h": 26.4, "h2s_ppm": 11.6, "instability_proba": 0.56,
      "status": "depleted", "note": "Старый сектор: генерация газа практически выработана" }
  ],
  "summary": { "green": 3, "amber": 29, "red": 5, "depleted": 11 }
}
```

| Поле | Описание |
|---|---|
| `age_class` | `fresh` / `mid` / `old` |
| `instability_proba` | Вероятность нестабильности (RandomForestClassifier) |
| `status` | `green` — стабильно; `amber` — H₂S > 25 ppm или риск > 0.4; `red` — H₂S > 60 ppm или риск > 0.7; `depleted` — поток < 40 м³/ч |

---

## 13. Сценарии и БД

Хранилище: SQLite по умолчанию (файл `backend/data/unearth.db`, путь — `UNEARTH_DB_PATH`),
PostgreSQL через `UNEARTH_DB_URL`. Схема создаётся автоматически:

```sql
CREATE TABLE scenarios (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,   -- BIGSERIAL в Postgres
    name         TEXT NOT NULL,
    notes        TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    inputs_json  TEXT NOT NULL,
    results_json TEXT NOT NULL DEFAULT '{}'
);
```

Сохраняются **параметры** сценария и **дайджест** результатов (не полные ряды). Ключи дайджеста:
`year1_avg_power_mw`, `peak_power_mw`, `ai_servers`, `miners`, `used_mw`, `daily_margin_usd`,
`fleet_health_score`, `opex_annual_usd`, `capex_total_usd`, `payback_years`, `irr`,
`net_profit_p50_usd`, `co2_avoided_t`, `green_fund_usd`, `trees_planted`.

### 13.1. POST /api/scenarios (201)

Тело (`ScenarioCreate`):

| Поле | Тип | Обязательно | Описание |
|---|---|---|---|
| `name` | string | да | 1–200 символов |
| `notes` | string | нет | до 2000 символов |
| `inputs` | `ScenarioInputs` | да | Полные входы сценария (см. ниже) |
| `run` | bool | нет (true) | `true` — прогнать цепочку и сохранить дайджест |
| `results` | object | нет | Готовые результаты при `run=false`; при `run=true` пишется полный payload |

`ScenarioInputs`: все поля `ForecastRequest` (кроме `use_prophet`) плюс
`h2s_ppm`, `mode`, `manual_miners`, `manual_ai_servers`, `btc_price` (nullable),
`gpu_rent_usd_per_gpu_hour` (nullable), `market_provider`, `seed`.

```json
{ "id": 1, "name": "DEMO: H2S 45 ppm", "created_at": "2026-10-19T06:41:39.751052+00:00" }
```

### 13.2. GET /api/scenarios?limit=100

```json
{
  "items": [
    { "id": 2, "name": "DEMO: H2S 90 ppm", "notes": "…",
      "created_at": "2026-10-19T06:41:39.866403+00:00" }
  ],
  "count": 1
}
```

`limit` зажимается в диапазон 1–500. Полные результаты не отдаются — только карточки.

### 13.3. GET /api/scenarios/{id}

```json
{
  "id": 7, "name": "DEMO: H2S 45 ppm", "notes": "…", "created_at": "2026-10-19T09:12:00+00:00",
  "inputs": { "horizon_years": 5, "h2s_ppm": 45, "mode": "auto", "seed": 42, "…": "…" },
  "results": {
    "digest": { "capex_total_usd": 35504248, "payback_years": 2.4, "irr": 0.395, "…": "…" },
    "generated_at": "2026-10-19T09:12:00+00:00",
    "payload_version": 1,
    "payload": {
      "forecast": { "…": "как §6" },
      "optimize": { "…": "как §7" },
      "plan": { "months": 12, "…": "как §8" },
      "maintenance": { "…": "как §9" },
      "carbon": { "…": "как §11" },
      "finance": { "…": "как §10, включая fiscal и fx" },
      "sectors": { "…": "как §12" }
    }
  }
}
```

Полный `payload` пишется при `run=true`, поэтому загрузка сценария в дашборде
восстанавливает все графики без пересчёта модели. `digest` остаётся лёгким
и используется только для сравнения метрик.

### 13.4. DELETE /api/scenarios/{id}

```json
{ "deleted": 1 }
```

404, если сценария нет.

### 13.5. POST /api/scenarios/compare

Тело: `{"ids": [5, 6]}` (2–10 существующих сценариев).

```json
{
  "comparison": [
    { "id": 5, "name": "DEMO: H2S 45 ppm", "created_at": "2026-10-19T08:07:52+00:00",
      "metrics": { "year1_avg_power_mw": 13.77, "ai_servers": 500, "miners": 2480,
                   "fleet_health_score": 92.3, "capex_total_usd": 35504248,
                   "payback_years": 2.4, "irr": 0.395,
                   "net_profit_p50_usd": 85021507, "co2_avoided_t": 3670047.3 } },
    { "id": 6, "name": "DEMO: H2S 90 ppm", "created_at": "2026-10-19T08:07:52+00:00",
      "metrics": { "year1_avg_power_mw": 13.77, "ai_servers": 500, "miners": 1758,
                   "fleet_health_score": 80.3, "capex_total_usd": 33482648,
                   "payback_years": 2.4, "irr": 0.393,
                   "net_profit_p50_usd": 80347094, "co2_avoided_t": 3670047.3 } }
  ],
  "best": { "year1_avg_power_mw": 5, "daily_margin_usd": 5, "fleet_health_score": 5,
            "opex_annual_usd": 5, "capex_total_usd": 6, "payback_years": 5,
            "irr": 5, "net_profit_p50_usd": 5, "co2_avoided_t": 5,
            "green_fund_usd": 5, "trees_planted": 5 },
  "missing_ids": [],
  "disclaimer": "Симуляционные данные, не инвестиционная рекомендация."
}
```

`best` — id лучшего сценария по каждой метрике; направление оптимизации задано в бэкенде:

| Метрика | Лучше |
|---|---|
| `year1_avg_power_mw`, `daily_margin_usd`, `fleet_health_score`, `irr`, `net_profit_p50_usd`, `co2_avoided_t`, `green_fund_usd`, `trees_planted` | больше |
| `opex_annual_usd`, `capex_total_usd`, `payback_years` | меньше |

> Сравнивать можно только существующие сценарии: если найдено меньше двух — 422 с перечнем
> отсутствующих id. `missing_ids` в успешном ответе — не найденные из запроса.

---

## 14. POST /api/simulation/run

Полный прогон: **forecast → optimize → plan → maintenance → carbon → finance → sectors**.
Тело — `ForecastRequest` (как в §6). Ответ — объект из семи секций:

```json
{
  "forecast": { "…": "как §6" },
  "optimize": { "…": "как §7, mode=auto" },
  "plan": { "…": "как §8 (12 месяцев)" },
  "maintenance": { "…": "как §9" },
  "carbon": { "…": "как §11" },
  "finance": { "…": "как §10, включая fiscal и fx" },
  "sectors": { "…": "как §12, месяц = первый месяц горизонта" }
}
```

Реальный прогон (5 лет, дефолты): мощность года 1 — 13.77 МВт, CAPEX — 35 504 248 $,
окупаемость — 2.4 года, чистая прибыль P50 за горизонт — 85 274 350 $, 48 секторов.

> В цепочке используется рынок из входов (по умолчанию синтетический) и режим `auto`;
> НДС и налоги считаются в `finance.fiscal` по режиму `kr_htp`.

## 15. Приложение A. Формулы

**Майнинг.** `доход/сут = 144 × 3.125 BTC / hashrate_TH × 110 TH × BTC × (1 − 0.015)`.

**ИИ-сервер.** `доход/сут = рента × 24 ч × 2 GPU`.

**Амортизация.** `мощность_кВт × 24 × 0.0175 $/кВт·ч` (1.5–2 ¢ из досье).

**Маржа на кВт·день.** `(доход/сут × ML-множитель − амортизация) / мощность_кВт`.

**Derate газа.** `clip((CH₄ − 0.40)/0.15) × (1 − clip((H₂S − 50)/150, 0, 0.45))`.

**Резерв плана.** `0.04 + 0.12 × clip((влажность_след_месяца − 1)/0.20)`.

**Износ ГПУ.** `0.35 %/мес × (H₂S/25)^1.35`; `Health = 100 − износ × наработка`, пол 15 %.

**Сера.** `кг/мес = расход LFG × ppm × 1e-6 × 1.539`; ресурс = ёмкость / загрузка.

**Карбон.** `ER = CH₄(т) × GWP`; `кредиты = ER × (1 − буфер)`; `NPV` — по потоку с лагом.

**Налог на майнинг КР.** `база = кВт·ч × тариф (6.06 сома / курс)`; `налог = 10 %`.
**Валюта.** `net = gross × (1 − спред − доля_репатриации × стоимость − хедж)`; `KGS = net × курс`.

**Green Tracker.** `CO₂ = CH₄(м³) × 0.716 / 1000 × 28`; фонд = `0.05 × max(прибыль, 0)`; дерево 4 $.

**Окупаемость/IRR.** Дисконтированный поток при WACC 10 %; IRR — бисекция на (-0.9, 3.0].

---

## 16. Приложение B. Конвейер интеграции

```text
1. GET  /api/market/current?provider=auto      → рынок и прогноз доходности BTC
2. POST /api/forecast                          → summary.year1_avg_power_mw, monthly[]
3. POST /api/optimize        (available_mw)    → allocation[].count (парк «сейчас»)
4. POST /api/optimize/path   (12 месяцев)      → помесячный план, резерв, переключения
5. POST /api/maintenance     (мощность, CH₄)   → OPEX (variable/fixed), износ
6. POST /api/carbon          (CH₄ по месяцам)  → кредиты, NPV (P10/P50/P90)
7. POST /api/finance         (парк, OPEX, ряды)→ окупаемость, IRR, фискальный блок
8. POST /api/sectors         (CH₄ за месяц)    → карта секторов
9. POST /api/scenarios       (inputs, run=true)→ сохранение и сравнение
```

Шаги 3–6 и 8 независимы после прогноза; 7 требует результатов 3 и 5.

Пример (PowerShell):

```powershell
$f = Invoke-RestMethod -Uri 'http://localhost:8000/api/forecast' -Method Post `
  -ContentType 'application/json' -Body (@{ horizon_years = 5 } | ConvertTo-Json)

$plan = Invoke-RestMethod -Uri 'http://localhost:8000/api/optimize/path' -Method Post `
  -ContentType 'application/json' -Body (@{
    monthly_power_mw = $f.monthly[0..11].avg_power_mw
    monthly_moisture = $f.monthly[0..11].moisture_index
    h2s_ppm = 45
  } | ConvertTo-Json)

$plan.totals
```

---

## 17. Приложение C. Изменения v0.1 → v0.2.2

| Что | v0.1 | v0.2 |
|---|---|---|
| Рынок | только синтетика | `market_provider`: live (CoinGecko/mempool.space) с кэшем 10 мин и откатом |
| Балансировщик | одномоментный greedy | + `POST /api/optimize/path`: DP с резервом, переключениями и путём BTC |
| Карбон | только CO₂ в финансах | `POST /api/carbon`: кредиты ACM0001, буфер, лаг, NPV P10/P50/P90 |
| Налоги | pretax | `fiscal_regime` (`none`/`kr_general`/`kr_htp`) в `/api/finance` |
| Сценарии | — | SQLite/Postgres: CRUD + сравнение метрик с `best` |
| Хешрейт сети | константа | live-значение в оптимизации и финансах |
| Контракты | `market` без источника | `market.source`, `market.notes`, `network_hashrate_ths` |
| Валюта | — | `POST /api/currency` + блок `fx` в финансах |
| Налоги | 3 режима КР | + `kz_aifc` (Astana Hub) и `POST /api/fiscal/compare` |
| Тариф майнинга | 0.032 $ (занижен) | 6.06 сома/кВт·ч по курсу (проверено) |
| Доход майнинга | BTC/день без курса | USD/день (исправлен масштаб ×65 000) |
| Риск ПП в КЗ | не учитывался | `pe_risk_share` (50 %) → КПН КР 10 % с доли прибыли |
| Сценарии | дайджест метрик | полный payload: загрузка без пересчёта |

*Документ сгенерирован по фактическим ответам сервиса v0.2 (октябрь 2026).
Схемы: `backend/app/schemas.py`; маршруты: `backend/app/api/routes.py`; OpenAPI: `docs/openapi.json`.*
