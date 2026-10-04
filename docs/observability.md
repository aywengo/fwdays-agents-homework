# Observability

OpenClaw's `diagnostics-otel` plugin exports **traces, metrics and logs** over
OTLP/HTTP to the `grafana/otel-lgtm` container (OpenTelemetry Collector + Tempo +
Prometheus + Loki + Grafana). The dashboard **Home energy agents** is provisioned
as Grafana's home page: http://127.0.0.1:3000.

| Panel group | Source | Shows |
| --- | --- | --- |
| Overview | Prometheus | agent turns, tool calls, blocked tool calls, tokens (last hour) |
| Agents and A2A | Prometheus | turns by agent and trigger (user / cron / agent handoff), `sessions_*` handoff rate, messages by channel incl. `a2a` |
| Tools and MCP | Prometheus | calls and p95 latency per tool (`solax-cloud__*`, `netatmo-weather__*`, `rce-prices__*`), errors by category, calls blocked by policy |
| Model | Prometheus | run duration, tokens by agent, estimated cost |
| Traces | Tempo (TraceQL) | recent runs, error spans, MCP tool calls, A2A handoffs and A2A channel traffic |
| Logs | Loki | gateway warnings and errors, correlated with traces by `traceId` |

Useful TraceQL queries in **Explore → Tempo**:

```
{resource.service.name="home-energy-agents" && name="openclaw.run"}
{resource.service.name="home-energy-agents" && status=error}
{name="openclaw.tool.execution" && span.openclaw.toolName=~"sessions_.*"}
{name="openclaw.tool.execution" && span.openclaw.outcome="blocked"}
```

Span catalogue: `openclaw.run` → `openclaw.model.call` / `openclaw.tool.execution`
(tool name, source, outcome, error category, denial reason) /
`openclaw.message.processed` / `openclaw.message.delivery`.

Privacy: prompt and tool content is **not** exported unless
`OTEL_CAPTURE_CONTENT=true`. The OpenClaw Control UI (Sessions, Automations →
run history) is the second, content-level view of what each agent did.
