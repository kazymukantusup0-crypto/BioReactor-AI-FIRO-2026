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
- `sudo` на Pi спрашивает пароль → `install.sh` и сетевые команды запускает человек.
- Ручная проверка без Arduino и без sudo (когда службы ещё нет): сначала `cd ~/BioReactor_AI && git pull`
  (скрипт появился в коммите c1435c7), затем `~/BioReactor_AI/raspberry/run_simulated.sh start` → на ноутбуке
  `BIOREACTOR_SENSORS=pi BIOREACTOR_PI_URL=http://<адрес Pi>:8780`, страница показывает
  «RASPBERRY PI (<адрес>) → ВИРТУАЛЬНЫЙ ARDUINO» (`docs/reactor/real_pi_virtual_arduino.png`).
- Ручной запуск и служба `bioreactor-pi` делят порт 8780 — одновременно работать не могут.
  Перед установкой службы: `~/BioReactor_AI/raspberry/run_simulated.sh stop` (install.sh теперь делает это сам).
  Установка (пароль sudo вводит человек):
  `ssh -t bioreactor "cd ~/BioReactor_AI && git pull && cd raspberry && ./run_simulated.sh stop; sudo ./install.sh --simulate"`
- 18.11 служба установлена с `--simulate` и работает (`systemctl status bioreactor-pi` → active (running)).
- Trixie: сетевые профили создаёт netplan (`netplan-eth0`, `netplan-wlan0-…`), управляет ими NetworkManager.

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

Изменить пороги или порт: `sudo nano /etc/bioreactor-pi/config.json`, затем `sudo systemctl restart bioreactor-pi`.
Перед остановкой служба выключает все реле (`all_off`).

## 3. Сеть ноутбук ↔ Pi без интернета

### Основной вариант — прямой Ethernet-кабель

На Pi:
```bash
sudo ./setup_network.sh cable          # Pi = 192.168.50.2/24 на eth0, Wi-Fi не трогает
```

На ноутбуке (Windows) задать адаптеру Ethernet статический адрес **192.168.50.1**, маска **255.255.255.0**, шлюз пустой:
«Параметры → Сеть и Интернет → Ethernet → Назначение IP → Изменить → Вручную». Или в командной строке от
администратора (имя адаптера смотреть в `ipconfig`):
```bat
netsh interface ipv4 set address name="Ethernet" static 192.168.50.1 255.255.255.0
```

Проверка с ноутбука: `ping 192.168.50.2`, затем в браузере `http://192.168.50.2:8780/health`.

### Запасной вариант — Wi-Fi точка доступа на Pi

```bash
sudo ./setup_network.sh hotspot МойПароль123   # сеть "BioReactor-Pi", Pi = 10.42.0.1
```
Ноутбук подключается к Wi-Fi «BioReactor-Pi», адрес Pi: `http://10.42.0.1:8780`. Отключить:
`sudo nmcli con down bioreactor-hotspot`.

## 4. Ноутбук: указать адрес Pi

`data/config/reactor_hardware.json`:
```json
{"mode": "pi", "pi_url": "http://192.168.50.2:8780"}
```
(для Wi-Fi — `http://10.42.0.1:8780`). Можно не менять файл, а задать переменные перед запуском:
`set BIOREACTOR_SENSORS=pi` и `set BIOREACTOR_PI_URL=http://192.168.50.2:8780`.

Перезапустить дашборд (`ЗАПУСК_BioReactor.bat`), открыть «Реактор» → **«Проверить связь»**. Вверху должно быть
«RASPBERRY PI → ARDUINO (192.168.50.2:8780)», время ответа и порт Arduino.

`"mode": "simulator"` (по умолчанию) — железо не нужно: внутри дашборда работает тот же код Pi с виртуальной
Arduino, на странице крупно «СИМУЛЯТОР». Это запасной вариант на защите, если железо откажет.

## 5. Если что-то не работает

| Признак | Что проверить |
|---|---|
| «НЕТ СВЯЗИ С RASPBERRY PI» | кабель; `ping 192.168.50.2`; адрес ноутбука 192.168.50.1; `systemctl status bioreactor-pi`; `pi_url` |
| «НЕТ СВЯЗИ С ARDUINO» | USB-кабель (нужен кабель с данными, не только зарядный); `ls /dev/ttyACM*`; в журнале `usb_connect_failed` |
| Реле выключились сами | журнал на странице: `laptop_lost` (ноутбук молчал > 15 с), `watchdog_all_off` (Arduino 10 с без команд), `leak_heat_off` |
| Ложная утечка сразу после включения | MQ греются ~1 мин (`warmup`); порог `GAS_OUT_LEAK` подобрать скетчем `sensor_test` |
| `permission denied /dev/ttyACM0` | пользователь `bioreactor` в группе `dialout` (`install.sh` добавляет), перезапуск службы |
