# Observability

Плагін OpenClaw `diagnostics-otel` експортує **трейси, метрики та логи** через
OTLP/HTTP у контейнер `grafana/otel-lgtm` (OpenTelemetry Collector + Tempo +
Prometheus + Loki + Grafana). Дашборд **Home energy agents** підключено як
домашню сторінку Grafana: http://127.0.0.1:3000.

| Група панелей | Джерело | Що показує |
| --- | --- | --- |
| Overview | Prometheus | ходи агентів, виклики інструментів, заблоковані виклики, токени (за останню годину) |
| Agents and A2A | Prometheus | ходи за агентом і тригером (користувач / cron / передача між агентами), частота передач `sessions_*`, повідомлення за каналами, включно з `a2a` |
| Tools and MCP | Prometheus | виклики та p95-затримка для кожного інструмента (`solax-cloud__*`, `netatmo-weather__*`, `rce-prices__*`), помилки за категоріями, виклики, заблоковані політикою |
| Model | Prometheus | тривалість запусків, токени за агентом, орієнтовна вартість |
| Traces | Tempo (TraceQL) | останні запуски, спани з помилками, виклики MCP-інструментів, передачі A2A та трафік каналу A2A |
| Logs | Loki | попередження та помилки gateway, пов'язані з трейсами через `traceId` |

Корисні TraceQL-запити в **Explore → Tempo**:

```
{resource.service.name="home-energy-agents" && name="openclaw.run"}
{resource.service.name="home-energy-agents" && status=error}
{name="openclaw.tool.execution" && span.openclaw.toolName=~"sessions_.*"}
{name="openclaw.tool.execution" && span.openclaw.outcome="blocked"}
```

Каталог спанів: `openclaw.run` → `openclaw.model.call` / `openclaw.tool.execution`
(назва інструмента, джерело, результат, категорія помилки, причина відмови) /
`openclaw.message.processed` / `openclaw.message.delivery`.

Приватність: вміст промптів та інструментів **не** експортується, якщо не
встановлено `OTEL_CAPTURE_CONTENT=true`. Control UI OpenClaw (Sessions,
Automations → історія запусків) — другий погляд на те, що робив кожен агент,
уже на рівні вмісту.
