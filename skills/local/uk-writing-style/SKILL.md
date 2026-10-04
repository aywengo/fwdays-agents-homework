---
name: uk-writing-style
description: Write and polish user-facing Ukrainian text for the home-energy team (reports, answers, proposals). Use before sending any message to the user, together with no-ai-slop. Covers Ukrainian slop patterns, calques and russianisms, the fixed energy glossary, number and unit formatting, and how to apply no-ai-slop inside fixed report templates.
---

# Ukrainian writing style for the home-energy team

The user reads short messages in Discord or WhatsApp, usually on a phone. Write
plain, concrete Ukrainian: numbers first, one idea per line, no filler.

## How this combines with no-ai-slop
- Apply the **no-ai-slop** rules to every user-facing message, silently. Do **not**
  add its "What changed" section and do not explain the edit, unless the user
  explicitly asked you to edit or audit a text (`/no-ai-slop`).
- Fixed report templates (morning/evening report, TOU proposal) are the user's
  chosen format: keep their emoji line prefixes and line order. Apply the rules
  to the free text inside them (the advice line, reasons, explanations).
- no-ai-slop's word lists are English. Use the Ukrainian list below as well.

## Ukrainian patterns to cut
- Empty openers and fillers: «Варто зазначити, що», «Слід підкреслити», «Важливо
  розуміти», «Як відомо», «Отже, підсумовуючи», «У сучасному світі», «На сьогоднішній день»
  (→ «сьогодні»), «Давайте розберемося».
- Binary contrasts: «Це не просто X, а Y», «Йдеться не про X, а про Y». State Y.
- Puffery: «відіграє ключову роль», «є невід'ємною частиною», «надзвичайно важливо»,
  «справжній прорив». Give the number instead.
- Bureaucratic verb phrases: «здійснити зарядку» → «зарядити», «провести аналіз» →
  «проаналізувати», «надати рекомендацію» → «порадити», «у зв'язку з тим, що» → «бо».
- Passive and impersonal chains: «Було прийнято рішення» → who decided.
- Fake-profound endings and recaps («Тож майбутнє вже тут», «Загалом, …»). End on
  the last concrete point or the question to the user.

## Calques and russianisms to avoid
| Avoid | Use |
| --- | --- |
| приймати участь | брати участь |
| на протязі дня | протягом дня |
| в залежності від | залежно від |
| слідуючий | наступний |
| співпадати | збігатися |
| являється | є |
| згідно графіку | згідно з графіком / за графіком |
| вірно (meaning correct) | правильно |
| получати | отримувати |
| підводити підсумки | підбивати підсумки |
| о 7-ій ранку | о 7:00 / о сьомій |

## Glossary (use these terms consistently, do not cycle synonyms)
| Concept | Ukrainian |
| --- | --- |
| battery SOC | заряд батареї, % |
| SOH | стан батареї (SOH), % |
| PV, solar production | сонячні панелі; генерація / вироблено |
| grid import / export | імпорт з мережі / експорт у мережу |
| self-consumption | власне споживання |
| inverter | інвертор |
| TOU settings, charge window | налаштування TOU; вікно заряду |
| grid charging | заряд з мережі |
| evening peak | вечірній пік |
| RCE price | ціна RCE |
| net-billing | net-billing (нетто-білінг) |
| irradiation | сонячне опромінення, кВт·год/м² |
| forecast | прогноз |

## Numbers and units
- Decimal comma is fine in prose («6,5 кВт·год»); keep times as `HH:MM` and ranges
  with an en dash: «12:00–14:00».
- Units: кВт·год, кВт, %, °C, мм, км/год, zł/кВт·год (prices) or «zł» for money.
- Round consistently: energy and % to one decimal, prices to two («≈0,03 zł/кВт·год»),
  money to whole złoty unless under 10 zł.
- Say «≈» for estimates (PV forecast, consumption, savings). Never present an
  estimate as a measurement.

## Tone
- Address the user as «ви» in reports; follow the user's lead in chat.
- One emoji per line at most, only where the template has it.
- If data is missing, say what is missing in one short sentence («Немає вечірнього
  знімка, тому нічне споживання пропускаю.»), do not apologise at length.
