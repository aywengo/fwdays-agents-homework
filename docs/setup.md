# Встановлення

Вимоги: Docker з Compose v2, Python 3.11+ на хості (для допоміжних скриптів),
обліковий запис постачальника моделі (за замовчуванням Anthropic), застосунок у
SolaX Developer Platform, застосунок Netatmo. Discord і WhatsApp — за бажанням.

## 1. Секрети та конфігурація

```bash
python3 scripts/render_config.py init     # створює .env (0600) зі згенерованими внутрішніми токенами
$EDITOR .env                              # заповніть SolaX, Netatmo, модель, Discord/WhatsApp
python3 scripts/netatmo_auth.py           # одноразова згода в браузері -> NETATMO_REFRESH_TOKEN
python3 scripts/render_config.py render   # -> .local/openclaw/openclaw.json + .local/workspaces/*
```

`render` можна безпечно запускати повторно після кожної зміни `.env` чи
`agents/*.md`; пам'ять агентів зберігається. На Linux встановіть
`HOST_UID`/`HOST_GID` у значення `id -u`/`id -g`.
Кожну змінну описано в [configuration.md](configuration.md).

## 2. Запуск

```bash
docker compose up -d --build
docker compose logs -f openclaw-init   # встановлює плагіни discord/whatsapp/diagnostics-otel (зафіксовані версії)
scripts/smoke_test.sh                  # health, автентифікація A2A, конфіг, MCP probe, Grafana
```

Якщо ви не вказали API-ключ, один раз увійдіть до постачальника моделі:

```bash
docker compose exec openclaw openclaw models auth login --provider anthropic
```

Control UI: http://127.0.0.1:18789 (gateway-токен з `.env`). Grafana:
http://127.0.0.1:3000 (`admin` / `GRAFANA_ADMIN_PASSWORD`).

## 3. Канали

### Discord (окремий бот для кожного агента)
1. Створіть три застосунки в Discord Developer Portal (Dispatcher, WeatherCast,
   Trader), увімкніть intent **Message Content**, запросіть кожного бота на свій
   сервер з правами Send Messages / Read Message History.
2. Увімкніть Developer Mode і скопіюйте ID сервера, свій user ID, ID командного
   каналу та каналу для звітів (може бути той самий), а також application ID і
   bot user ID кожного бота.
3. Внесіть токени та ID у `.env` (`DISCORD_*`). Обов'язковий лише бот
   dispatcher-а; боти без токена пропускаються.
4. `python3 scripts/render_config.py render && docker compose up -d openclaw`.
5. Напишіть боту в DM або @згадайте його в командному каналі. Кожен бот відповідає
   без згадки у своїй (необов'язковій) кімнаті (`DISCORD_<ROLE>_CHANNEL_ID`).

### WhatsApp (dispatcher)
1. Встановіть `WHATSAPP_ENABLED=true`, `WHATSAPP_ALLOW_FROM=+48…` (та
   `WHATSAPP_REPORT_TO` для звітів), потім виконайте render і перезапуск.
2. Під'єднайте обліковий запис через QR-код (рекомендовано окремий номер):
   `docker compose exec -it openclaw openclaw channels login --channel whatsapp`

## 4. Заплановані звіти

```bash
scripts/setup_automations.sh          # створює ранкове та вечірнє завдання для кожного каналу звітів
scripts/setup_automations.sh --list
docker compose exec openclaw openclaw automations run <job-id>   # перевірити зараз
```

Перший ранковий звіт не має попереднього вечірнього знімка; нічні показники
з'являються з другого дня.

## 5. A2A ззовні

```bash
python3 scripts/a2a_client.py card
python3 scripts/a2a_client.py send "Який зараз заряд батареї і чи варто ввечері економити?"
```

## Без Docker (нативно)

MCP-сервери також працюють через stdio (`MCP_TRANSPORT=stdio rce-prices-mcp`).
Якщо запускаєте їх через HTTP на тому ж хості, використовуйте
`http://127.0.0.1:<port>/mcp` або ім'я `*.localhost` у `mcp.servers`: SSRF-захист
OpenClaw довіряє точно налаштованому origin, але блокує довільне ім'я хоста, яке
резолвиться в loopback.

## Усунення несправностей

| Симптом | Що перевірити |
| --- | --- |
| `openclaw mcp probe` не проходить | health контейнерів `*-mcp` у `docker compose ps`; однаковий `MCP_INTERNAL_TOKEN` з обох боків (render + перезапуск) |
| `mcp doctor` попереджає про literal-заголовок Authorization | Очікувано: заголовки — це рядки; значення `${MCP_INTERNAL_TOKEN}` підставляється зі змінних середовища контейнера |
| Netatmo `token refresh failed` | Повторіть `scripts/netatmo_auth.py`, потім `docker compose rm -sf weather-mcp && docker volume rm <project>_weather-state && docker compose up -d weather-mcp` |
| Prices `rate limit` | Зачекайте кілька хвилин; закешовані дні все одно віддаються |
| Звіт не доставлено | `openclaw automations runs <job-id>`; бот Discord має бачити канал звітів |
