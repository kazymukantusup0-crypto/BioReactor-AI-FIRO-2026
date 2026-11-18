# Протокол Arduino ↔ Raspberry Pi ↔ ноутбук (прошивка bioreactor-1.0)

Цепочка: **датчики и реле → Arduino Mega → USB → Raspberry Pi → сеть → ноутбук**.
Главная защита и автоматика — на Arduino (работают и без Pi). Pi — мост, журнал и вторая проверка.
Ноутбук — страница «Реактор» и ИИ-агент (агент только читает).

Прошивка: `firmware/bioreactor/bioreactor.ino` (FW_VERSION `bioreactor-1.0`).
Код Pi: `raspberry/bioreactor_pi/` (protocol.py, bridge.py, server.py, virtual_arduino.py).

## 1. Железо

| Что | Пин Mega | Примечание |
|---|---|---|
| DS18B20 (температура внутри) | 28 | нет ответа → `temp: null`, тревога `no_temp`, подогрев заблокирован |
| DHT11 (влажность) | 23 | 5 сбоев подряд → `humidity: null` |
| MQ-9 внутри (газ в реакторе) | A12 | **сырое значение 0–1023**, не ppm и не % метана |
| MQ-9 снаружи (утечка) | A11 | сырое значение 0–1023 |
| R1 подогрев | 27 | реле активны по LOW |
| R2 охлаждение | 26 | |
| R3 откачка газа | 24 | |
| R4 шнек (мотор) | 25 | только вручную, не дольше 10 мин подряд |
| Энкодер, кнопка BACK | A8–A10, 22 | BACK 2 с = E-STOP, кнопка энкодера 3 с = сброс тревог |

USB: Mega-клон с чипом CH340 → на Pi это `/dev/ttyUSB0` (`serial.port: "auto"` находит его сам).

## 2. Строки Arduino → Pi (JSON, одна строка = одно сообщение, 115200 бод)

```json
{"type":"boot","fw":"bioreactor-1.0"}
```
Сразу после включения или сброса (открытие USB-порта перезагружает Mega через DTR). Все реле выключены, `auto: true`.

```json
{"type":"status","fw":"bioreactor-1.0","uptime_s":3,"mq_in":199,"mq_out":996,"humidity":15.0,"temp":23.6,
 "relays":{"heat":false,"cool":true,"pump":false,"auger":false},
 "remote":{"heat":false,"cool":false,"pump":false,"auger":false},
 "auto":true,"temp_min":20.0,"temp_max":23.5,"temp_hard_max":45.0,"gas_out_limit":1000,"gas_in_limit":700,
 "alarms":{"estop":false,"leak":false,"overheat":false,"warmup":true,"no_temp":false,"link_lost":false,"auger_timeout":false}}
```
Раз в секунду (это реальная строка, снятая с Mega 18.11.2026).

* `remote.X = true` — реле X включено **командой с Pi** (не автоматикой и не кнопкой на месте).
* `auto` — автоматика Arduino: подогрев ниже `temp_min`, охлаждение выше `temp_max` (гистерезис 0,5 °C), откачка при `mq_in > gas_in_limit` (гистерезис 30).
* Пять порогов хранятся в EEPROM Arduino (меню Limits на её экране).
* `auger_timeout` бывает `true` только в **одной** строке — Pi держит эту тревогу на странице 5 минут.

```json
{"type":"ack","cmd":"RELAY","ok":true}
{"type":"ack","cmd":"RELAY","ok":false,"error":"INTERLOCK"}
```
Ответ на каждую команду, кроме `GET` (на `GET` приходит `status`). Pi сопоставляет ответ по имени команды и шлёт команды строго по одной.

## 3. Команды Pi → Arduino (текст, регистр не важен)

| Команда | Что делает |
|---|---|
| `PING` | «я на связи»; Pi шлёт каждые 2 с, начиная сразу после строки `boot` |
| `GET` | прислать `status` сейчас (Pi так обновляет страницу сразу после команды) |
| `RELAY <1-4> <0\|1>` | 1 подогрев, 2 охлаждение, 3 откачка, 4 шнек. Ручная команда на 1–3 **выключает AUTO** |
| `AUTO <0\|1>` | автоматика; включить нельзя при E-STOP или утечке |
| `SET TMIN\|TMAX\|THARD <°C>` | пороги температуры |
| `SET GOUT\|GIN <50–1000>` | пороги газа (сырое значение MQ-9) |
| `ESTOP` | аварийная остановка: всё выкл, AUTO выкл, держится до `RESET` |
| `RESET` | сброс E-STOP, `link_lost`; утечку — только если газ снаружи уже ниже порога |
| `ALLOFF` | всё выкл и AUTO выкл (Pi эту команду автоматически **не** шлёт) |

Правило порогов (`validSettings()`): `TMIN ≥ 0`, `TMAX ≤ 68`, `TMIN ≤ TMAX − 0,5`, `TMAX + 2 ≤ THARD ≤ 70`, газ 50–1000.

Коды ошибок: `BAD_ARGS`, `UNKNOWN`, `BAD_KEY`, `OUT_OF_RANGE`, `LOCAL_EDIT` (на экране Arduino сейчас правят пороги),
`INTERLOCK`, `NO_TEMP`, `OVERHEAT`, `WARMUP`, `ESTOP`, `LEAK`, `GAS_STILL_HIGH`.
Pi передаёт их дальше в нижнем регистре (`interlock`, `warmup` …), страница пишет причину по-русски/казахски/английски.

## 4. Защита на Arduino (главная)

| Событие | Реакция |
|---|---|
| 60 с после включения (прогрев MQ) | подогрев и откачка заблокированы, утечка не проверяется |
| газ снаружи > `gas_out_limit` 2 измерения подряд | **все реле выкл, AUTO выкл**, тревога `leak` до сброса человеком |
| температура ≥ `temp_hard_max` | подогрев выкл и заблокирован, пока не остынет на 2 °C |
| нет датчика температуры | подогрев выкл и заблокирован |
| подогрев и охлаждение вместе | нельзя (`INTERLOCK`) |
| 10 с без команд от Pi | выключаются **только реле с `remote = true`**, флаг `link_lost`; AUTO продолжает работать |
| шнек > 10 мин непрерывно | шнек выкл, `auger_timeout` |
| E-STOP (команда или BACK 2 с) | всё выкл, AUTO выкл, до сброса |

## 5. Что делает Pi (`raspberry/bioreactor_pi/bridge.py`)

1. Открыл порт → ждёт строку `boot` (до `boot_timeout_s` = 8 с). До неё не шлёт PING и не принимает команды
   (страница: «ARDUINO ЗАПУСКАЕТСЯ»). Если `boot` не пришла, но идут `status` — через 8 с принимает их и пишет в журнал `no_boot_line`.
2. `PING` каждые 2 с — сторож Arduino молчит.
3. Нет `status` дольше 5 с → «НЕТ СВЯЗИ С ARDUINO», все команды отклоняются (кроме E-STOP, пока порт открыт).
4. USB выдернули → переоткрывает порт каждые 3 с, снова ждёт `boot`.
5. **Ноутбук молчит > 15 с → Pi выключает только реле с `remote = true`** (`RELAY n 0`). `ALLOFF` не шлёт:
   он выключил бы и автоматику Arduino. Остановка службы делает то же самое.
6. Перед командой проверяет те же правила, что и Arduino (`safety.refuse_reason`, `protocol.limits_error`),
   чтобы дать понятную причину сразу; последнее слово — за ответом Arduino.
7. Журнал SQLite (`/var/lib/bioreactor-pi/journal.sqlite3`): команды (кто, что, результат), тревоги Arduino (появилась / прошла),
   связь, показания каждые 5 с. Старая база дополняется колонкой `auger` без потери записей.

## 6. HTTP API Pi (порт 8780)

| Запрос | Тело | Подтверждение |
|---|---|---|
| `GET /health`, `/state`, `/history?window=600\|3600`, `/journal?limit=50`, `/events` (SSE) | — | — |
| `POST /relay` | `{"name":"heat\|cool\|pump\|auger","state":1}` | `"confirm": true` |
| `POST /auto` | `{"on":true}` | `"confirm": true` |
| `POST /limit` | `{"name":"temp_min","value":35.5}` | `"confirm": true` |
| `POST /reset` | `{}` | `"confirm": true` |
| `POST /estop` | `{}` | **не нужно** — аварийная остановка не ждёт |
| `POST /simulate` | `{"what":"leak\|usb\|arduino_silent\|temp_sensor","on":true}` | только `--simulate` |

Ноутбук (`src/hardware/api.py`) повторяет это под `/api/reactor/*` (`/relay`, `/auto`, `/limit`, `/estop`, `/alarm/reset`).

## 7. Ноутбук: где Pi

`data/config/reactor_hardware.json`, режим `auto`: по очереди пробует
`http://10.42.0.1:8780` (Wi-Fi точка Pi) → `http://192.168.50.2:8780` (кабель) → `http://bioreactor.local:8780` (общая сеть).
Первый ответивший используется, пока отвечает; страница пишет маршрут: «через Wi-Fi Pi», «через кабель», «через общую сеть».
Переопределить: `BIOREACTOR_SENSORS=simulator|pi|auto`, `BIOREACTOR_PI_URL=http://…` (один фиксированный адрес).

## 8. Симулятор

`raspberry/bioreactor_pi/virtual_arduino.py` — построчный перенос логики скетча (те же функции: `evaluateAlarms`,
`autoControl`, `enforceSafety`, `requestRelay`, `handleCommand`) + простая физика. Используется в `--simulate` на Pi,
в режиме «СИМУЛЯТОР» на ноутбуке и в тестах. Прогрев MQ в симуляторе 20 с (на плате 60 с).

## 9. Проверки

* `tests/test_reactor_hardware.py` — протокол (реальная строка с Mega), правила скетча на виртуальной Arduino,
  Pi с «глупой» Arduino (ожидание boot, PING, отказ без отправки, только remote-реле при потере ноутбука, E-STOP, USB),
  HTTP API, режим auto ноутбука, агент без доступа к командам.
* `tests/test_agent_v10_reactor.py` — советы агента по новым тревогам и порогам.
* `frontend/tests/reactor.test.tsx`, `frontend/tests/reactor-browser.mjs` — страница.
