# Довідник конфігурації (змінні середовища)

Уся конфігурація зберігається в `.env` у корені репозиторію (у `.gitignore`,
права `0600`). Почніть із шаблону:

```bash
python3 scripts/render_config.py init     # копіює .env.example -> .env і генерує внутрішні секрети
```

Після будь-якої зміни: `python3 scripts/render_config.py render` і
`docker compose up -d` (перестворює лише контейнери, налаштування яких змінилися).

Позначення:

- **Секрет** — облікові дані. Ніколи не комітьте, не вставляйте в чати, issues
  чи скриншоти.
- **Приватне** — не облікові дані, але ідентифікує вас (ID, номери телефонів,
  місцезнаходження). Тримайте в `.env`.
- **Обов.** — ✅ обов'язкова, ➖ необов'язкова, 🔁 обов'язкова лише коли функцію увімкнено.
- **Хто читає** — компонент, що використовує значення. Docker передає кожне
  значення лише тому контейнеру, якому воно потрібне (див. `docker-compose.yml`).

## Внутрішні секрети (генерує `init`)

| Змінна | Обов. | Тип | Хто читає | Опис |
| --- | --- | --- | --- | --- |
| `OPENCLAW_GATEWAY_TOKEN` | ✅ | Секрет | openclaw | Токен для Control UI (http://127.0.0.1:18789), CLI всередині контейнера та Gateway RPC. |
| `MCP_INTERNAL_TOKEN` | ✅ | Секрет | openclaw, solax-mcp, weather-mcp, prices-mcp | Спільний bearer-токен між OpenClaw і трьома MCP-серверами. Усередині MCP-контейнерів стає `MCP_AUTH_TOKEN`. |
| `A2A_CLIENT_TOKEN` | ✅ | Секрет | openclaw, `scripts/a2a_client.py` | Bearer-токен A2A-партнера `homework-client` для `/a2a/v1`. |
| `GRAFANA_ADMIN_PASSWORD` | ✅ | Секрет | lgtm | Пароль користувача Grafana `admin` (http://127.0.0.1:3000). |

`init` заповнює лише порожні значення, тож ніколи не замінює токен, який ви вже
використовуєте. Щоб ротувати токен, очистіть його в `.env`, запустіть `init` і
`render`, потім `docker compose up -d`.

## Постачальник моделі

| Змінна | Обов. | Тип | Хто читає | Опис |
| --- | --- | --- | --- | --- |
| `OPENCLAW_MODEL` | ➖ | — | render_config | Посилання на модель для всіх агентів. За замовчуванням `anthropic/claude-sonnet-5`. |
| `ANTHROPIC_API_KEY` | 🔁 | Секрет | openclaw | API-ключ Anthropic. Альтернатива: залиште порожнім і один раз увійдіть через `docker compose exec openclaw openclaw models auth login --provider anthropic` (зберігається в томі `openclaw-state`). |
| `OPENAI_API_KEY` | ➖ | Секрет | openclaw | Лише якщо `OPENCLAW_MODEL` — модель `openai/…`. |

## Дім

| Змінна | Обов. | Тип | Хто читає | Опис |
| --- | --- | --- | --- | --- |
| `HOME_TZ` | ➖ | — | усі | Часовий пояс IANA для звітів, цін і прогнозів. За замовчуванням `Europe/Warsaw`. |
| `HOME_LAT` | ➖ | Приватне | weather-mcp | Широта для прогнозу. Якщо порожня (разом з `HOME_LON`), береться розташування станції Netatmo. Достатньо двох-трьох знаків після коми. |
| `HOME_LON` | ➖ | Приватне | weather-mcp | Довгота для прогнозу. |
| `PV_KWP` | ➖ | — | weather-mcp | Пікова потужність PV-установки в кВт. Вмикає орієнтовний денний `pv_estimate_kwh`. |
| `MORNING_REPORT_CRON` | ➖ | — | setup_automations.sh | Cron-вираз у `HOME_TZ`. За замовчуванням `"0 7 * * *"`. Лапки залиште. |
| `EVENING_REPORT_CRON` | ➖ | — | setup_automations.sh | За замовчуванням `"30 21 * * *"`. Лапки залиште. |

Зміна cron-значення впливає лише на нові завдання. Видаліть старе завдання в
Control UI (Automations) і знову запустіть `scripts/setup_automations.sh`.

## SolaX Cloud (лише dispatcher)

Створіть застосунок на https://developer.solaxcloud.com (client credentials).

| Змінна | Обов. | Тип | Хто читає | Опис |
| --- | --- | --- | --- | --- |
| `SOLAX_CLIENT_ID` | ✅ | Секрет | solax-mcp | OAuth client ID застосунку SolaX Developer Platform. |
| `SOLAX_CLIENT_SECRET` | ✅ | Секрет | solax-mcp | OAuth client secret. |
| `SOLAX_DEVICE_SN` | ✅ | Приватне | solax-mcp | Серійний номер інвертора. |
| `SOLAX_ALLOW_CONTROL` | ➖ | — | solax-mcp, render_config | `true` відкриває `set_battery_self_use_mode` (інакше інструмент прибрано і на MCP-сервері, і в OpenClaw). Dispatcher однаково вимагає вашого явного підтвердження, а заплановані завдання його ніколи не отримують. За замовчуванням `false`. |

## Планування заряду батареї (лише dispatcher)

Використовуються для ранкової пропозиції заряду з мережі та налаштувань TOU
(див. [architecture.md](architecture.md#пропозиція-заряду-та-налаштування-tou)). Без
`BATTERY_CAPACITY_KWH` і `BATTERY_MAX_CHARGE_KW` звіт працює, але пропозиції не буде.

| Змінна | Обов. | Тип | Хто читає | Опис |
| --- | --- | --- | --- | --- |
| `BATTERY_CAPACITY_KWH` | 🔁 | — | solax-mcp | Корисна ємність батареї, кВт·год. |
| `BATTERY_MAX_CHARGE_KW` | 🔁 | — | solax-mcp | Максимальна потужність заряду з мережі, кВт. Визначає тривалість вікна заряду. |
| `BATTERY_MIN_SOC` | ➖ | — | solax-mcp | Нижня межа розряду в налаштуваннях інвертора та розрахунках, %. За замовчуванням `15`. |
| `BATTERY_TARGET_SOC` | ➖ | — | solax-mcp | До якого рівня заряджати з мережі (`charge_upper_soc`), %. За замовчуванням `90`. |
| `HOME_DAILY_CONSUMPTION_KWH` | 🔁 | — | solax-mcp | Типове добове споживання будинку, кВт·год. Використовується, доки в `memory/energy-log.md` менше трьох вечірніх записів; далі dispatcher бере середнє за 7 днів. |

## Netatmo (лише weather-cast)

Створіть застосунок на https://dev.netatmo.com/apps з redirect URI
`http://localhost:8765/callback`, потім запустіть `python3 scripts/netatmo_auth.py`.

| Змінна | Обов. | Тип | Хто читає | Опис |
| --- | --- | --- | --- | --- |
| `NETATMO_CLIENT_ID` | ✅ | Секрет | weather-mcp, netatmo_auth.py | Client ID застосунку Netatmo. |
| `NETATMO_CLIENT_SECRET` | ✅ | Секрет | weather-mcp, netatmo_auth.py | Client secret застосунку Netatmo. |
| `NETATMO_REFRESH_TOKEN` | ✅ | Секрет | weather-mcp | Початковий refresh-токен (scope `read_station`), який записує `netatmo_auth.py`. Netatmo його ротує; поточний токен зберігається в томі `weather-state`, тож це значення використовується лише під час першого запуску або після видалення тому. |
| `NETATMO_DEVICE_ID` | ➖ | Приватне | weather-mcp | MAC-адреса базової станції, якщо в обліковому записі їх кілька. |

## Discord (за бажанням, окремий бот для кожного агента)

Developer Mode у Discord → правий клік → *Copy ID*. Бот dispatcher-а обов'язковий,
щойно налаштовано будь-якого бота; бот без токена пропускається.

| Змінна | Обов. | Тип | Хто читає | Опис |
| --- | --- | --- | --- | --- |
| `DISCORD_GUILD_ID` | 🔁 | Приватне | render_config | ID сервера (guild). |
| `DISCORD_OWNER_USER_ID` | 🔁 | Приватне | render_config | Ваш user ID; єдина людина, якій дозволено спілкуватися з ботами. |
| `DISCORD_TEAM_CHANNEL_ID` | 🔁 | Приватне | render_config | Спільний канал; боти відповідають на @згадки і передають задачі одне одному тут. |
| `DISCORD_REPORT_CHANNEL_ID` | ➖ | Приватне | render_config, setup_automations.sh | Канал для запланованих звітів (може збігатися з командним). |
| `DISCORD_DISPATCHER_BOT_TOKEN` | 🔁 | Секрет | openclaw | Токен бота застосунку Dispatcher. |
| `DISCORD_DISPATCHER_APPLICATION_ID` | 🔁 | Приватне | render_config | Application ID (General Information). |
| `DISCORD_DISPATCHER_BOT_USER_ID` | 🔁 | Приватне | render_config | User ID самого бота (для аліасів @згадок і allowlist). |
| `DISCORD_DISPATCHER_CHANNEL_ID` | ➖ | Приватне | render_config | Необов'язкова власна кімната, де бот відповідає без згадки. |
| `DISCORD_WEATHER_BOT_TOKEN` | ➖ | Секрет | openclaw | Токен бота застосунку WeatherCast. |
| `DISCORD_WEATHER_APPLICATION_ID` | 🔁 | Приватне | render_config | Обов'язкова, якщо задано токен WeatherCast. |
| `DISCORD_WEATHER_BOT_USER_ID` | 🔁 | Приватне | render_config | Обов'язкова, якщо задано токен WeatherCast. |
| `DISCORD_WEATHER_CHANNEL_ID` | ➖ | Приватне | render_config | Необов'язкова власна кімната. |
| `DISCORD_TRADER_BOT_TOKEN` | ➖ | Секрет | openclaw | Токен бота застосунку Trader. |
| `DISCORD_TRADER_APPLICATION_ID` | 🔁 | Приватне | render_config | Обов'язкова, якщо задано токен Trader. |
| `DISCORD_TRADER_BOT_USER_ID` | 🔁 | Приватне | render_config | Обов'язкова, якщо задано токен Trader. |
| `DISCORD_TRADER_CHANNEL_ID` | ➖ | Приватне | render_config | Необов'язкова власна кімната. |

## WhatsApp (за бажанням, маршрутизується до dispatcher-а)

| Змінна | Обов. | Тип | Хто читає | Опис |
| --- | --- | --- | --- | --- |
| `WHATSAPP_ENABLED` | ➖ | — | render_config, setup_automations.sh | `true` вмикає канал. Під'єднання через QR: `docker compose exec -it openclaw openclaw channels login --channel whatsapp`. Сесія зберігається в томі `openclaw-state` і є обліковими даними. |
| `WHATSAPP_ALLOW_FROM` | 🔁 | Приватне | render_config | Номери у форматі E.164 через кому, яким дозволено писати боту, наприклад `+48500000000`. |
| `WHATSAPP_REPORT_TO` | ➖ | Приватне | setup_automations.sh | Номер, на який надходять заплановані звіти. |

## Observability

| Змінна | Обов. | Тип | Хто читає | Опис |
| --- | --- | --- | --- | --- |
| `OTEL_CAPTURE_CONTENT` | ➖ | — | render_config | `true` додає промпти, відповіді та дані інструментів у трейси. Вимкнено за замовчуванням, бо звіти містять дані про дім. |
| `OTEL_ENDPOINT` | ➖ | — | render_config | OTLP/HTTP-endpoint. За замовчуванням `http://lgtm:4318` (вбудований Grafana LGTM). Вкажіть, щоб надсилати телеметрію в інший колектор. |

## Docker і версії

| Змінна | Обов. | Тип | Хто читає | Опис |
| --- | --- | --- | --- | --- |
| `HOST_UID` / `HOST_GID` | ➖ | — | docker compose | Користувач, від імені якого працює контейнер OpenClaw; має володіти `.local/`. На Linux — `id -u` / `id -g`. За замовчуванням `1000`. |
| `OPENCLAW_IMAGE_TAG` | ➖ | — | docker compose | Тег образу Gateway. За замовчуванням `2026.9.6-browser`. |
| `OPENCLAW_PLUGIN_VERSION` | ➖ | — | openclaw-init | Версія плагінів Discord, WhatsApp і diagnostics-otel. Має збігатися з версією Gateway. За замовчуванням `2026.9.6`. |
| `LGTM_IMAGE_TAG` | ➖ | — | docker compose | Тег `grafana/otel-lgtm`. За замовчуванням `0.35.0`. |

## Встановлюються Docker Compose (не додавайте в `.env`)

Наведено для запуску MCP-серверів поза Docker (stdio або HTTP).

| Змінна | За замовчуванням | Опис |
| --- | --- | --- |
| `MCP_TRANSPORT` | `stdio` (у Docker: `http`) | `stdio` або `http` (streamable HTTP). |
| `MCP_AUTH_TOKEN` | — (Секрет) | Обов'язковий bearer-токен у режимі HTTP; Docker бере його з `MCP_INTERNAL_TOKEN`. |
| `MCP_ALLOW_NO_AUTH` | не задано | `1` дозволяє режим HTTP без токена. Лише для локальних експериментів. |
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `8000` | Адреса прослуховування HTTP. |
| `HOME_MCP_STATE_DIR` | `~/.local/state/home-mcp` (у Docker: `/data`) | Ротований токен Netatmo і кеш цін. |
| `PRICES_API_URL` | `https://godzinowe.pl/api.php` | Базова URL API цін (тести спрямовують її на локальну заглушку). |
| `LOG_LEVEL` | `INFO` | Рівень логування MCP-серверів. |
| `OPENCLAW_CONFIG_PATH`, `OPENCLAW_STATE_DIR`, `OPENCLAW_HOME`, `HOME`, `TZ` | див. compose | Шляхи та часовий пояс усередині контейнера OpenClaw. |
| `A2A_BASE_URL` | `http://127.0.0.1:18789` | URL Gateway для `scripts/a2a_client.py`. |

## Де зберігаються секрети

| Секрет | Де зберігається |
| --- | --- |
| Усе, що вище позначено як *Секрет* | Лише `.env`. Згенерований конфіг містить посилання `${VAR}` / `{source: env}`, а не значення. |
| Ротований refresh/access-токен Netatmo | Том Docker `weather-state` (`/data/netatmo-token.json`, права 0600). |
| Вхід до моделі (якщо використовували `models auth login`), сесія WhatsApp, встановлені плагіни | Том Docker `openclaw-state`. |
| Дані Grafana | Том Docker `lgtm-data`. |

Перед комітом запускайте `python3 scripts/check_secrets.py`. Скрипт завершується
з помилкою, якщо будь-яке значення секретної чи приватної змінної з `.env`
трапляється у файлі, який git закомітить.
