# Скіли (skills)

Скіл — це папка з `SKILL.md`: інструкції, які агент читає, коли задача їх
потребує. OpenClaw показує моделі лише назву й опис скіла, а повний текст агент
читає інструментом `read` перед використанням.

## Використані скіли

| # | Скіл | Джерело | dispatcher | weather-cast | trader | Коли застосовується | Що дає |
| --- | --- | --- | :-: | :-: | :-: | --- | --- |
| 1 | `no-ai-slop` | [petergyang/no-ai-slop](https://github.com/petergyang/no-ai-slop) @ `000650b`, MIT | ✅ | ✅ | ✅ | кожне повідомлення користувачу; `/no-ai-slop <текст>` | Прибирає «AI-шаблони» з тексту, зберігаючи голос автора |
| 2 | `uk-writing-style` | `skills/local/` | ✅ | ✅ | ✅ | кожне повідомлення користувачу | Українські шаблони-«вода», кальки й русизми, глосарій енергетики, формат чисел і одиниць; як застосовувати no-ai-slop до фіксованих шаблонів звітів |
| 3 | `memory-hygiene` | `skills/local/` | ✅ | ✅ | ✅ | кожен запис у пам'ять; `MEMORY_MAINTENANCE` (щомісяця) | Формати файлів пам'яті, що не можна зберігати; щомісячна архівація журналів «копія → перевірка → перезапис» і стиснення `MEMORY.md` |
| 4 | `energy-history-analysis` | `skills/local/` | ✅ | | | питання про минулі періоди й тренди | Підсумки за день/тиждень/місяць з різниці накопичувальних лічильників: виробіток, споживання, власне споживання, самодостатність, цикли батареї; перевірка пропусків і скидань лічильників |
| 5 | `pv-forecast-reading` | `skills/local/` | | ✅ | | кожен прогноз | Як читати прогноз для генерації PV: опромінення, години 10–15, сезон; однакові мітки «сонячний день / мінлива хмарність…» |
| 6 | `weather-alerts` | `skills/local/` | | ✅ | | кожен прогноз; `WEATHER_ALERT_CHECK` (кожні 3 год) | Пороги й рівні попереджень (ℹ️/⚠️/🚨): вітер, мороз, спека, злива, сніг на панелях, модулі станції; без повторів у межах каналу; готові рядки для звітів |
| 7 | `net-billing-advice` | `skills/local/` | | | ✅ | поради щодо експорту, накопичення, заряду з мережі | Механіка net-billing (RCE, експорт проти власного споживання) і правила порад |

Разом: dispatcher — 4 скіли, weather-cast — 5, trader — 4. Вбудовані скіли
OpenClaw (близько 20, наприклад github чи weather) для агентів приховані.

Розподіл задано в `AGENT_SKILLS` у `scripts/render_config.py`. Він потрапляє в
конфіг як allowlist `agents.entries.<agent>.skills`: агент бачить **лише** свої скіли.
Перевірити, що бачить агент:

```bash
docker compose exec openclaw openclaw skills check --agent dispatcher   # розділ «Ready and visible to model»
```

У звітах no-ai-slop застосовується мовчки: шаблон звіту (емодзі, порядок рядків)
лишається, редагується лише вільний текст, а розділ «What changed» не додається.
Щоб відредагувати власний текст, напишіть агенту в Discord: `/no-ai-slop <текст>`
або `$no-ai-slop чи це AI-текст? <текст>`.

## Скіли в автоматизаціях

| Завдання | Агент | Розклад | Скіли | Доставка |
| --- | --- | --- | --- | --- |
| Morning energy report | dispatcher | `MORNING_REPORT_CRON` (07:00) | uk-writing-style, no-ai-slop; weather-cast додає рядки з weather-alerts | Discord / WhatsApp |
| Evening energy report | dispatcher | `EVENING_REPORT_CRON` (21:30) | те саме | Discord / WhatsApp |
| Weather alert check | weather-cast | `WEATHER_ALERT_CRON` (кожні 3 год, 06:15–21:15) | weather-alerts | Лише нові або посилені ⚠️/🚨; інакше `NO_REPLY` і нічого не надсилається |
| Memory maintenance | кожен агент | `MEMORY_MAINTENANCE_CRON` (1-го числа, 03:30) | memory-hygiene | Без доставки; результат у `memory/maintenance-log.md` та історії запусків |

Створюються командою `scripts/setup_automations.sh`. Звіти й перевірка погоди
створюються окремо для кожного каналу (OpenClaw доставляє завдання в один канал),
тому записи в пам'ять ідемпотентні: один знімок на день і тип, одна пропозиція TOU
на день, попередження дедуплікуються в межах каналу.

## Структура

```
skills/
  sources.json        зовнішні скіли: repo + повний SHA коміту + шлях + ліцензія
  skills.lock.json    sha256 кожного файлу зовнішніх скілів (генерується)
  vendor/<name>/      копії зовнішніх скілів (у git, з LICENSE і SOURCE.md)
  local/<name>/       власні скіли проєкту
```

`python3 scripts/render_config.py render` копіює скіли кожного агента в
`.local/workspaces/<agent>/skills/` — найпріоритетніше джерело скілів OpenClaw, яке
агент може прочитати своїм `read` з обмеженням на workspace. Скрипт видаляє лише ті
папки, які сам встановив (`.managed-by-render.json`).

## Додати зовнішній скіл

1. Перегляньте `SKILL.md` і все, що поруч. Скіл — це промпт, який працює з
   інструментами агента; ставтеся до нього як до коду від третьої сторони.
2. Переконайтеся, що скіл не потребує `exec`, браузера чи вебдоступу: у цих агентів
   таких інструментів немає (свідома межа доступу). Скіли-обгортки над CLI тут не
   працюватимуть; для нових джерел даних краще додати MCP-сервер.
3. Додайте запис у `skills/sources.json` з **повним** SHA коміту (не гілкою).
4. `python3 scripts/sync_skills.py sync` — завантажить, скопіює в `skills/vendor/`, оновить lock.
5. Додайте назву скіла агентам у `AGENT_SKILLS` (`scripts/render_config.py`).
6. `python3 scripts/render_config.py render && docker compose restart openclaw`.
7. Перевірте `openclaw skills check --agent <agent>`.

Оновити до свіжого коміту: `python3 scripts/sync_skills.py update no-ai-slop`, потім
`git diff skills/vendor/` перед комітом.

## Додати власний скіл

1. `skills/local/<name>/SKILL.md` з frontmatter `name: <name>` (збігається з назвою
   папки) і `description:` — коли саме його використовувати. Опис — це те, за чим
   модель вирішує, чи читати скіл, тож пишіть його конкретно.
2. Додайте `<name>` у `AGENT_SKILLS` і рядок в інструкції агента (`agents/<agent>/AGENTS.md`,
   розділ Skills), виконайте render і перезапуск.
3. `python3 scripts/sync_skills.py verify` перевіряє frontmatter, унікальність назв
   і відповідність vendor-файлів lock-файлу (це ж робить CI).

## ClawHub і Skill Workshop

- Скіли з ClawHub (`openclaw skills search/install`) встановлюються в стан
  контейнера, а не в репозиторій. Для цього проєкту краще вендорити їх через
  `sources.json`, щоб версія була зафіксована й видна в git.
- OpenClaw створює щотижневі завдання «Skill collection review» (Skill Workshop),
  де агенти пропонують нові скіли. Пропозиції не застосовуються без вашого
  схвалення: `docker compose exec openclaw openclaw skills workshop list`. Якщо не
  потрібні, видаліть ці завдання в Control UI (Automations).
