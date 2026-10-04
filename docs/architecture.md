# Архітектура

```mermaid
flowchart LR
  subgraph Користувачі
    D[Discord<br/>3 боти]:::ch
    W[WhatsApp]:::ch
    X[Зовнішній A2A-клієнт<br/>scripts/a2a_client.py]:::ch
    C[Cron 07:00 / 21:30]:::ch
  end
  subgraph OpenClaw Gateway 2026.9.6
    DI[☀️ dispatcher<br/>агент за замовчуванням]
    WC[🌦️ weather-cast]
    TR[💹 trader]
    MEM[(workspace + memory/<br/>.local/workspaces)]
  end
  subgraph MCP-сервери - приватна мережа, bearer-автентифікація
    S[solax-cloud<br/>upstream mouldiwarp/solax-cloud-mcp]
    N[netatmo-weather<br/>Netatmo + Open-Meteo]
    P[rce-prices<br/>godzinowe.pl + кеш]
  end
  LGTM[Grafana LGTM<br/>Tempo / Prometheus / Loki]
  D --> DI & WC & TR
  W --> DI
  X -- A2A 1.0 JSON-RPC --> DI
  C --> DI
  DI -- sessions_spawn --> WC & TR
  TR -- sessions_send --> WC
  DI --> S
  WC --> N
  TR --> P
  DI & WC & TR --- MEM
  DI & WC & TR -. OTLP трейси/метрики/логи .-> LGTM
  classDef ch fill:#eef,stroke:#88a
```

## Агенти та межі доступу

| Агент | Роль | MCP-інструменти | Інші інструменти | Заборонено |
| --- | --- | --- | --- | --- |
| `dispatcher` | Точка входу, звіти, статистика SolaX та (за потреби) зміна режимів | `solax-cloud__*` | пам'ять, read/write у власному workspace, `sessions_spawn`/`yield`/`send` | `netatmo-weather__*`, `rce-prices__*`, exec, web, browser, messaging, automation |
| `weather-cast` | Показники станції, прогноз, прогноз генерації PV | `netatmo-weather__*` | пам'ять, власний workspace, `sessions_send` | `solax-cloud__*`, `rce-prices__*`, `sessions_spawn`, `subagents` + глобальні заборони |
| `trader` | Аналіз цін RCE та поради щодо часу використання енергії | `rce-prices__*` | пам'ять, власний workspace, `sessions_send` (запити до weather-cast) | `solax-cloud__*`, `netatmo-weather__*`, `sessions_spawn`, `subagents` + глобальні заборони |

Рівні, що забезпечують межі (усе генерує `scripts/render_config.py`):

1. **Глобальна політика інструментів**: `tools.profile: minimal` плюс явний список
   `alsoAllow`; групи exec, web, browser, messaging, automation і media
   заборонені; файлові інструменти обмежені власним workspace агента.
2. **Списки заборон для кожного агента**: кожен агент забороняє MCP-сервери інших
   агентів через глоби `server__*`, тож агент не може дістатися чужого джерела
   даних, навіть якщо його про це попросять.
3. **Allowlist агент-агент**: `tools.agentToAgent.allow` містить лише трьох
   агентів; запускати субагентів може тільки dispatcher (`subagents.allowAgents`).
4. **На боці MCP-сервера**: `set_battery_self_use_mode` видаляється із сервера
   SolaX, якщо не встановлено `SOLAX_ALLOW_CONTROL=true`, і `toolFilter` в OpenClaw
   теж його приховує. Інструмент позначено `destructiveHint`, тож OpenClaw також
   вважає його дією, що потребує підтвердження. Інструменти читання мають `readOnlyHint`.
5. **Заплановані завдання** створюються з обмеженням `--tools`, яке виключає
   керування батареєю.
6. **Мережа**: MCP-сервери не мають опублікованих портів і вимагають bearer-токен
   (`MCP_INTERNAL_TOKEN`); Gateway і Grafana слухають лише на `127.0.0.1`.

## Агент-агент (A2A)

Два механізми, що доповнюють один одного:

- **Усередині Gateway**: dispatcher делегує через `sessions_spawn` і збирає
  результати через `sessions_yield`; trader консультується з weather-cast через
  `sessions_send`. У Discord (окремий бот для кожного агента) передачі задач також
  видно як @згадки в командному каналі.
- **Стандартний протокол A2A 1.0** (`channels.a2a`): Gateway публікує Agent Card
  за адресою `/.well-known/agent-card.json` з окремим skill для кожного агента і
  приймає автентифіковані JSON-RPC-виклики `SendMessage`/`GetTask` на `/a2a/v1`.
  Зовнішні агенти (або `scripts/a2a_client.py`) можуть передати задачу команді;
  задача маршрутизується до dispatcher-а, який далі делегує всередині.

## Постійна пам'ять

Пам'ять OpenClaw — це звичайний Markdown у workspace кожного агента, змонтований
з `.local/workspaces/<agent>`, тож вона переживає перезапуск контейнерів і нові сесії:

- `MEMORY.md` — тривкі факти та вподобання («запам'ятай, мінімальний SOC 20%»),
  завантажуються на початку кожної сесії.
- `memory/energy-log.md` — вечірні та ранкові знімки SolaX від dispatcher-а.
  Ранковий звіт рахує нічне споживання та зміну заряду батареї з вечірнього знімка
  попереднього дня, тобто залежить від пам'яті, записаної в попередньому запуску.
- `memory/YYYY-MM-DD.md` — щоденні нотатки (погодні події, денні підсумки цін),
  доступні для пошуку через `memory_search`.

`render_config.py render` оновлює файли інструкцій (`AGENTS.md`, `SOUL.md`,
`IDENTITY.md`, `TOOLS.md`) з `agents/`, але ніколи не перезаписує `MEMORY.md`,
`USER.md` чи `memory/`.

## Звіти

| Завдання | Розклад за замовчуванням | Зміст |
| --- | --- | --- |
| Ранковий | `0 7 * * *` Europe/Warsaw | Заряд батареї після ночі, споживання вночі, погода та прогноз генерації на сьогодні, ціни на сьогодні, одна порада |
| Вечірній | `30 21 * * *` | Вироблено за день, імпорт/експорт з мережі, споживання за день, заряд батареї перед ніччю, погода та ціни на завтра |

Завдання виконуються в ізольованих сесіях і надсилають фінальну відповідь у
Discord та/або WhatsApp (`scripts/setup_automations.sh`).

## Джерела даних

| Джерело | Доступ | Примітки |
| --- | --- | --- |
| SolaX Developer Platform (`openapi-eu.solaxcloud.com`) | OAuth2 client credentials | Лише дані в реальному часі (без історії); денні показники беруться з лічильників `today*` і збережених знімків. Ліміт upstream — 100 викликів/хв. |
| Netatmo (`api.netatmo.com`) | OAuth2, `read_station` | Refresh-токени ротуються; поточний зберігається в томі `weather-state`. |
| Open-Meteo | без автентифікації | Прогноз, сонячні години, інсоляція для місця розташування будинку. |
| API godzinowe.pl | без автентифікації (безкоштовно для приватного використання) | Погодинні ціни PSE RCE; відповіді кешуються по днях; при 429 повертається кеш. |
