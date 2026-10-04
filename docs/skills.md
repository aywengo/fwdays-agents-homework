# Скіли (skills)

Скіл — це папка з `SKILL.md`: інструкції, які агент читає, коли задача їх
потребує. OpenClaw показує моделі лише назву й опис скіла, а повний текст агент
читає інструментом `read` перед використанням.

## Які скіли має кожен агент

| Скіл | Джерело | dispatcher | weather-cast | trader | Навіщо |
| --- | --- | :-: | :-: | :-: | --- |
| `no-ai-slop` | [petergyang/no-ai-slop](https://github.com/petergyang/no-ai-slop), MIT, зафіксований коміт | ✅ | ✅ | ✅ | Прибирає «AI-шаблони» з тексту, зберігаючи голос автора |
| `uk-writing-style` | `skills/local/` | ✅ | ✅ | ✅ | Українська частина no-ai-slop: шаблони, кальки й русизми, глосарій енергетики, формат чисел; як застосовувати no-ai-slop до фіксованих шаблонів звітів |
| `pv-forecast-reading` | `skills/local/` | | ✅ | | Як читати прогноз для генерації PV: опромінення, години 10–15, сезон, мітки «сонячний день / мінлива хмарність…» |
| `net-billing-advice` | `skills/local/` | | | ✅ | Механіка net-billing (RCE, експорт проти власного споживання) і правила порад |

Розподіл задано в `AGENT_SKILLS` у `scripts/render_config.py`. Він потрапляє в
конфіг як allowlist `agents.entries.<agent>.skills`: агент бачить **лише** свої скіли,
а вбудовані скіли OpenClaw (github, weather тощо) для нього приховані.

У звітах no-ai-slop застосовується мовчки: шаблон звіту (емодзі, порядок рядків)
лишається, редагується лише вільний текст, а розділ «What changed» не додається.
Щоб відредагувати власний текст, напишіть агенту в Discord: `/no-ai-slop <текст>`
або `$no-ai-slop чи це AI-текст? <текст>`.

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
2. Додайте запис у `skills/sources.json` з **повним** SHA коміту (не гілкою).
3. `python3 scripts/sync_skills.py sync` — завантажить, скопіює в `skills/vendor/`, оновить lock.
4. Додайте назву скіла агентам у `AGENT_SKILLS` (`scripts/render_config.py`).
5. `python3 scripts/render_config.py render && docker compose restart openclaw`.
6. Перевірка: `docker compose exec openclaw openclaw skills check --agent dispatcher`
   (розділ «Ready and visible to model»).

Оновити до свіжого коміту: `python3 scripts/sync_skills.py update no-ai-slop`, потім
`git diff skills/vendor/` перед комітом.

## Додати власний скіл

1. `skills/local/<name>/SKILL.md` з frontmatter `name: <name>` (збігається з назвою
   папки) і `description:` — коли саме його використовувати. Опис — це те, за чим
   модель вирішує, чи читати скіл, тож пишіть його конкретно.
2. Додайте `<name>` у `AGENT_SKILLS`, виконайте render і перезапуск.
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
