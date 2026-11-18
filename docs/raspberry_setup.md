# Raspberry Pi: настройка (без интернета)

Цепочка: Arduino ──USB──► Raspberry Pi ──Ethernet-кабель──► ноутбук. Протокол и защита описаны в `docs/hardware_protocol.md`.

## 0. Что нужно

- Raspberry Pi 3/4/5 с Raspberry Pi OS **Bookworm** (Lite достаточно), Python 3.11 уже есть в системе;
- Ethernet-кабель ноутбук ↔ Pi (обычный: современные порты сами разбираются с перекрёстным);
- папка `raspberry/` из проекта. Интернет **не нужен**: pyserial лежит в `raspberry/wheels/`.

## Наша Pi (проверено 18.11.2026)

- Raspberry Pi 5, **Debian 13 trixie** (не Bookworm), Python 3.13.5, пользователь `bio`, имя `bioreactor.local`.
- Вход с ноутбука по ключу `~/.ssh/id_ed25519_bioreactor` (без пароля); в `~/.ssh/config` короткое имя `bioreactor`.
  Имя `.local` в точке доступа iPhone находится не всегда — тогда по IP (`ssh bio@172.20.10.3`, адрес может меняться).
- Код: `~/BioReactor_AI` (ветка `reactor-hardware`, клон без истории), venv `raspberry/.venv` с pyserial из `wheels/`.
- `sudo` на Pi без пароля, SSH только по ключу (с 18.11.2026, см. «Вход на Pi» ниже).
- Ручная проверка без Arduino и без sudo (когда службы ещё нет): код на Pi обновляется `scripts\deploy_to_pi.ps1`
  (скрипт появился в коммите c1435c7), затем `~/BioReactor_AI/raspberry/run_simulated.sh start` → на ноутбуке
  `BIOREACTOR_SENSORS=pi BIOREACTOR_PI_URL=http://<адрес Pi>:8780`, страница показывает
  «RASPBERRY PI (<адрес>) → ВИРТУАЛЬНЫЙ ARDUINO» (`docs/reactor/real_pi_virtual_arduino.png`).
- Ручной запуск и служба `bioreactor-pi` делят порт 8780 — одновременно работать не могут.
  Перед установкой службы: `~/BioReactor_AI/raspberry/run_simulated.sh stop` (install.sh теперь делает это сам).
  Установка (пароль sudo вводит человек):
  `ssh -t bioreactor "cd ~/BioReactor_AI && git pull && cd raspberry && ./run_simulated.sh stop; sudo ./install.sh --simulate"`
- 18.11 служба установлена с `--simulate` и работает (`systemctl status bioreactor-pi` → active (running)).
- Trixie: сетевые профили создаёт netplan (`netplan-eth0`, `netplan-wlan0-…`), управляет ими NetworkManager.

## Как это работает сейчас (с 18.11.2026)

**Pi всегда раздаёт свою Wi-Fi сеть «BioReactor-Pi»** (режим `always`): при каждом включении питания
NetworkManager сам поднимает её примерно через 30–60 с, iPhone не нужен. Адрес Pi в этой сети — **10.42.0.1**, интернета в ней нет.
Профиль iPhone остался, но сам больше не подключается.

| Режим ноутбука | Как подключён | Интернет у ноутбука | Адрес Pi |
|---|---|---|---|
| **Защита / демо** | Wi-Fi **BioReactor-Pi** (кабель не нужен) | нет (и не нужен) | 10.42.0.1 |
| **Разработка** | школьный Wi-Fi + **кабель** к Pi | есть, через Wi-Fi | 192.168.50.2 |

Проверено 18.11.2026 в режиме разработки: маршрут по умолчанию у ноутбука один — через Wi-Fi (192.168.1.1), Pi — через
Ethernet; по кабелю шлюз и DNS не выдаются.

**Pi нужен интернет** (apt, обновить что-то из сети) — редко. Включите точку доступа на iPhone и по кабелю:
```
ssh -t bio@192.168.50.2 "sudo ~/BioReactor_AI/raspberry/setup_network.sh online 30"
```
Pi уйдёт на iPhone на 30 минут и сама вернётся к BioReactor-Pi. Раньше: `sudo ~/BioReactor_AI/raspberry/setup_network.sh back`.
Пока Pi на iPhone, ноутбук в BioReactor-Pi её не видит — работайте по кабелю.

**Обновить код на Pi** — без интернета, с ноутбука (по кабелю или по BioReactor-Pi), `git pull` на Pi больше не нужен:
```
powershell -ExecutionPolicy Bypass -File scripts\deploy_to_pi.ps1
```
Скрипт копирует папку `raspberry/` (как она на ноутбуке), кладёт код моста в `/opt/bioreactor-pi`, перезапускает
службу и ждёт `/health` с отметкой «коммит, время». Без пароля он запускает только `/usr/local/sbin/bioreactor-deploy`
(правило `/etc/sudoers.d/bioreactor-deploy`, ставит `install.sh`). Сетевые скрипты он только копирует; применить их —
`sudo ./install.sh && sudo ./setup_network.sh always` на Pi, **с подключённым кабелем**.

Переключить режим Wi-Fi (только с подключённым кабелем, иначе команда откажется):
`sudo ~/BioReactor_AI/raspberry/setup_network.sh always` (по умолчанию) или `... auto` (старый: iPhone рядом → он, нет → своя сеть).

## Вход на Pi: ключ, sudo, если ноутбук потерян

С 18.11.2026 (`raspberry/ssh_keys_only.sh`):
- **SSH — только по ключу** `~/.ssh/id_ed25519_bioreactor` с ноутбука (пароль по SSH не принимается, вход root по SSH запрещён).
  `ssh bioreactor` — по кабелю (192.168.50.2), `ssh bioreactor-wifi` — через BioReactor-Pi (10.42.0.1).
- **sudo без пароля** для `bio` (`/etc/sudoers.d/010-bio-nopasswd`). Значит, ключ ноутбука = полный доступ к Pi:
  берегите ноутбук; копию ключа держите только на своей флешке, не в проекте и не в облаке.
- **С монитора и клавиатуры на самой Pi** вход по-прежнему **с паролем** пользователя `bio` — это запасной путь.

**Если ноутбук потерян (или ключ пропал):**
1. Подключить к Pi монитор (кабель micro-HDMI) и USB-клавиатуру, включить питание.
2. Войти: пользователь `bio` и его пароль.
3. Вариант А — дать доступ новому ноутбуку по ключу. На новом ноутбуке в PowerShell:
   `ssh-keygen -t ed25519 -f $env:USERPROFILE\.ssh\id_ed25519_bioreactor`, файл `id_ed25519_bioreactor.pub`
   перенести на флешке и на Pi выполнить: `cat /media/bio/<флешка>/id_ed25519_bioreactor.pub >> ~/.ssh/authorized_keys`.
4. Вариант Б — временно вернуть вход по паролю: `sudo ~/BioReactor_AI/raspberry/ssh_keys_only.sh undo`
   (SSH снова принимает пароль, sudo снова спрашивает пароль). После настройки ключа — снова
   `sudo ~/BioReactor_AI/raspberry/ssh_keys_only.sh` (5 минут на подтверждение входом по ключу в новой сессии).
5. Если ноутбук украли — удалить его ключ: `nano ~/.ssh/authorized_keys`, строка с `laptop-bioreactor`.

## 1. Первый запуск Pi (один раз, с монитором или по SSH)

1. В Raspberry Pi Imager → «Настройки» включить SSH, задать имя пользователя и пароль.
2. Скопировать папку `raspberry` на Pi, например флешкой: `cp -r /media/$USER/<флешка>/raspberry ~/`.
3. Прошить Arduino скетчем `firmware/bioreactor/bioreactor.ino` (Arduino IDE на ноутбуке) и подключить её к Pi по USB.

## 2. Установка моста + автозапуск

```bash
cd ~/raspberry
chmod +x install.sh setup_network.sh
sudo ./install.sh                # с Arduino
# sudo ./install.sh --simulate   # без железа: виртуальная Arduino (для проверки сети)
```

Скрипт ставит код в `/opt/bioreactor-pi`, конфиг в `/etc/bioreactor-pi/config.json`, журнал в
`/var/lib/bioreactor-pi/`, создаёт пользователя `bioreactor` (группа `dialout` даёт доступ к `/dev/ttyACM*`) и
службу systemd `bioreactor-pi`. Служба стартует при загрузке и перезапускается после сбоя.

Проверка на самом Pi:
```bash
curl http://127.0.0.1:8780/health      # {"ok": true, ... "arduino_ok": true, "port": "/dev/ttyACM0"}
journalctl -u bioreactor-pi -f         # лог службы
ls /dev/ttyACM* /dev/ttyUSB*           # видна ли Arduino (Uno/Mega — ttyACM, клоны на CH340 — ttyUSB)
```

Пороги реактора (Temp Min/Max, Overheat, газ) хранятся в EEPROM Arduino и меняются на странице «Реактор» (блок
«Пороги Arduino», с подтверждением) или в меню Limits на экране Arduino. В `/etc/bioreactor-pi/config.json` — только
порт, таймауты и HTTP: после правки `sudo systemctl restart bioreactor-pi`.
Перед остановкой служба выключает только реле, включённые с ноутбука (ALLOFF не шлёт: автоматика Arduino продолжает работать).

Наша Pi с настоящей Mega (прошивка bioreactor-1.0, CH340 → `/dev/ttyUSB0`), переустановка без симулятора:
`ssh -t bioreactor "cd ~/BioReactor_AI && git pull && cd raspberry && ./run_simulated.sh stop; sudo ./install.sh"`

## 3. Сеть ноутбук ↔ Pi без интернета

### Основной вариант — прямой Ethernet-кабель

На Pi (пароль sudo вводит человек; с ноутбука: `ssh -t bioreactor "sudo ~/BioReactor_AI/raspberry/setup_network.sh cable"`):
```bash
sudo ./setup_network.sh cable
```
- Pi = **192.168.50.2/24** на eth0 и сама раздаёт ноутбуку адрес 192.168.50.x (NetworkManager «shared», свой dnsmasq).
- **Без шлюза и без DNS** (`/etc/NetworkManager/dnsmasq-shared.d/bioreactor-no-gateway.conf`, `ipv4.never-default`,
  IPv6 на кабеле выключен): интернет ноутбука всегда идёт через Wi-Fi, кабель — только для Pi.
- Wi-Fi Pi не трогается. Профиль Debian 13 `netplan-eth0` остаётся, наш `bioreactor-cable` главнее по приоритету.
- Защита от потери связи: если кабель вставлен, через 3 мин изменения откатываются сами, пока кто-то не подтвердит
  по кабелю: `ssh bio@192.168.50.2 "touch /tmp/bioreactor-net-ok"`.
- Отменить: `sudo nmcli con delete bioreactor-cable`.

На ноутбуке (Windows) ничего настраивать не нужно: адаптер Ethernet «получать адрес автоматически» (по умолчанию).

Проверка с ноутбука: `ping 192.168.50.2`, затем `http://192.168.50.2:8780/health`; `route print 0.0.0.0` — маршрут
по умолчанию только через Wi-Fi.

Проверено 18.11.2026: ноутбук получил 192.168.50.142 (DHCP), DNS на Ethernet пустой, маршрут по умолчанию один —
Wi-Fi (172.20.10.1), github.com открывается, ping 0 мс, /health по кабелю отвечает, после 3 мин профиль на месте.

### Без кабеля и без интернета — своя Wi-Fi сеть Pi «BioReactor-Pi»

Установка (пароль Wi-Fi — **только цифры, от 8**, вводите сами; он хранится только в профиле на Pi, не в проекте).
С `test` Pi сразу отпускает iPhone и держит BioReactor-Pi 20 минут — для проверки при подключённом кабеле:
```
ssh -t bio@192.168.50.2 "cd ~/BioReactor_AI && git pull && sudo raspberry/setup_network.sh hotspot test"
```
Сменить только пароль: `sudo raspberry/setup_network.sh hotspot-password`. Тестовый режим ещё раз:
`sudo raspberry/setup_network.sh hotspot-test 20`. Посмотреть, кто подключён: `sudo raspberry/setup_network.sh status`.

Настройки для Windows: WPA2-PSK (без WPA3), шифрование AES-CCMP, PMF выключен, WPS выключен, 2,4 ГГц, канал 6.
Что получается (служба `bioreactor-wifi`, работает без монитора и клавиатуры):

| Ситуация | Что делает Pi |
|---|---|
| рядом iPhone с включённой точкой доступа | подключается к нему (разработка: SSH, интернет для обновлений) |
| iPhone нет 45 с (выключен, далеко) — в том числе сразу после включения Pi | сама поднимает Wi-Fi **BioReactor-Pi**, адрес Pi **10.42.0.1** |
| в BioReactor-Pi никого нет 5 мин | пробует iPhone; если его нет — сразу снова BioReactor-Pi |
| к BioReactor-Pi кто-то подключён | никуда не переключается (демо не прервётся) |

Ноутбук получает адрес 10.42.0.x **без шлюза и DNS** — интернета в этой сети нет, и он не нужен.
Кабель (192.168.50.2) остаётся запасным и не меняется.

Защита от потери связи: первый раз, когда Pi сама поднимет BioReactor-Pi, в течение 3 минут кто-то должен зайти на Pi
**через эту сеть**: `ssh bio@10.42.0.1 "touch /tmp/bioreactor-hotspot-ok"`. Иначе всё само вернётся как было
(профиль удалится, служба уберётся, Pi вернётся к iPhone) — **но только если кабель не подключён**: с кабелем Pi
доступна и так, отката нет. После отката BioReactor-Pi больше не появится, пока не установить её заново. Убрать вручную: `sudo raspberry/setup_network.sh hotspot-remove`.
Журнал: `journalctl -u bioreactor-wifi -f`.

#### Простая инструкция: демо ↔ разработка (режим always)

**Демо:** включить питание Pi → через 1–2 мин на ноутбуке Wi-Fi **BioReactor-Pi** (подключается сам, если других
знакомых сетей рядом нет; иначе выбрать вручную) → `ЗАПУСК_BioReactor.bat` → «Реактор»: «через Wi-Fi Pi».

**Разработка:** ноутбук в школьном Wi-Fi + кабель к Pi. Дашборд найдёт Pi по кабелю («через кабель»), интернет у
ноутбука идёт через Wi-Fi. Windows не переключится на BioReactor-Pi сама, пока подключена к школьной сети.

## 4. Ноутбук: где искать Pi

`data/config/reactor_hardware.json`, `"mode": "auto"` (по умолчанию): дашборд по очереди пробует
`http://10.42.0.1:8780` (Wi-Fi Pi) → `http://192.168.50.2:8780` (кабель) → `http://bioreactor.local:8780` (общая сеть)
и пишет на странице, через что подключён.

Переопределить без правки файла: `set BIOREACTOR_SENSORS=simulator` (без железа, на странице крупно «СИМУЛЯТОР») или
`set BIOREACTOR_PI_URL=http://192.168.50.2:8780` (один фиксированный адрес).

## 5. Если что-то не работает

| Признак | Что проверить |
|---|---|
| «НЕТ СВЯЗИ С RASPBERRY PI» | кабель; `ping 192.168.50.2`; адрес ноутбука 192.168.50.1; `systemctl status bioreactor-pi`; `pi_url` |
| «НЕТ СВЯЗИ С ARDUINO» | USB-кабель (нужен кабель с данными, не только зарядный); `ls /dev/ttyACM*`; в журнале `usb_connect_failed` |
| Реле выключились сами | журнал на странице: `laptop_lost` (ноутбук молчал > 15 с), `watchdog_all_off` (Arduino 10 с без команд), `leak_heat_off` |
| Ложная утечка сразу после включения | MQ греются ~1 мин (`warmup`); порог `GAS_OUT_LEAK` подобрать скетчем `sensor_test` |
| `permission denied /dev/ttyACM0` | пользователь `bioreactor` в группе `dialout` (`install.sh` добавляет), перезапуск службы |
