// ============================================================
//  BioReactor AI — прошивка Arduino Mega 2560, версия 1.0
//  Основа: исходная прошивка проекта (экран, энкодер, меню, EEPROM).
//
//  Что добавлено:
//   * пороги в EEPROM: Temp Min / Temp Max / Overheat / Gas out alarm / Gas in pump
//   * защита на самой Arduino (работает и без Raspberry Pi):
//       - нет датчика температуры        -> подогрев выключен и заблокирован
//       - перегрев (>= Overheat)          -> подогрев выключен
//       - утечка газа снаружи (> порога)  -> ВСЕ реле выключены, тревога до сброса
//       - подогрев и охлаждение одновременно включить нельзя
//       - прогрев датчиков MQ 60 с после включения: подогрев и откачка заблокированы
//       - нет связи с Pi 10 с             -> выключаются реле, включённые с Pi
//   * аварийная остановка (E-STOP):
//       - удерживать кнопку BACK 2 с, или команда ESTOP с Pi
//       - все реле выключены, автоматика выключена, держится до сброса
//   * сброс тревог: удерживать кнопку энкодера 3 с, или команда RESET
//   * автоматическая откачка: газ внутри > Gas in pump -> реле 3 (в режиме AUTO)
//   * обмен с Raspberry Pi по USB Serial (115200), протокол описан ниже
//
//  Реле:  R1 (пин 27) подогрев, R2 (26) охлаждение, R3 (24) откачка, R4 (25) шнек (мотор)
//  Шнек: только вручную, автоотключение через AUGER_MAX_RUN_MS непрерывной работы
//
//  ПРОТОКОЛ (одна строка = одно сообщение, конец строки \n)
//  Arduino -> Pi:
//    при старте:     {"type":"boot","fw":"bioreactor-1.0"}
//    раз в секунду:  {"type":"status", ...все показания, реле, пороги, тревоги...}
//    ответ на команду: {"type":"ack","cmd":"RELAY","ok":true}
//                      {"type":"ack","cmd":"RELAY","ok":false,"error":"INTERLOCK"}
//  Pi -> Arduino (регистр не важен):
//    PING                    - «я на связи» (слать каждые 2 с)
//    GET                     - прислать статус сразу
//    RELAY <1-4> <0|1>       - включить/выключить реле
//    AUTO <0|1>              - автоматика вкл/выкл
//    SET TMIN|TMAX|THARD <°C>  - пороги температуры
//    SET GOUT|GIN <0-1023>     - пороги газа (сырое значение MQ-9)
//    ESTOP / RESET / ALLOFF  - авария / сброс тревог / всё выключить (и AUTO выкл)
//  Коды ошибок: BAD_ARGS, UNKNOWN, BAD_KEY, OUT_OF_RANGE, LOCAL_EDIT, INTERLOCK,
//               NO_TEMP, OVERHEAT, WARMUP, ESTOP, LEAK, GAS_STILL_HIGH
// ============================================================

#include <Adafruit_GFX.h>
#include <MCUFRIEND_kbv.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <DHT.h>
#include <EEPROM.h>
#include <avr/wdt.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>

#define FW_VERSION "bioreactor-1.0"

// --- ПИНЫ ---
#define ENC_CLK  A8
#define ENC_DT   A9
#define ENC_SW   A10
#define BTN_BACK 22

#define PIN_MQ9_IN  A12   // газ внутри реактора
#define PIN_MQ9_OUT A11   // газ снаружи (датчик утечки)
#define PIN_DHT     23
#define PIN_DS18    28

#define PIN_RELAY_1 27    // R1 подогрев
#define PIN_RELAY_2 26    // R2 охлаждение
#define PIN_RELAY_3 24    // R3 откачка газа
#define PIN_RELAY_4 25    // R4 шнек (мотор), только вручную

#define RELAY_ON  LOW
#define RELAY_OFF HIGH

#define R_HEAT 0
#define R_COOL 1
#define R_PUMP 2
#define R_AUGER 3

// --- НАСТРОЙКИ БЕЗОПАСНОСТИ ---
#define SERIAL_BAUD 115200
const unsigned long SENSOR_INTERVAL_MS = 1000;
const unsigned long MQ_WARMUP_MS       = 60000;  // прогрев датчиков MQ
const unsigned long LINK_TIMEOUT_MS    = 10000;  // нет связи с Pi
const unsigned long ESTOP_HOLD_MS      = 2000;   // удержание BACK = авария
const unsigned long RESET_HOLD_MS      = 3000;   // удержание кнопки энкодера = сброс
const float TEMP_HYST     = 0.5;
const float OVERHEAT_HYST = 2.0;
const int   GAS_IN_HYST   = 30;
const byte  LEAK_CONFIRM  = 2;   // столько измерений подряд выше порога = утечка
const unsigned long AUGER_MAX_RUN_MS = 600000;  // шнек: макс. 10 мин непрерывно

// Сторожевой таймер AVR. Выключен: на старых клонах Mega загрузчик
// может уйти в бесконечную перезагрузку. Включайте, только если уверены в загрузчике.
#define USE_AVR_WDT 0

// --- ОБЪЕКТЫ ---
MCUFRIEND_kbv tft;
#define DHTTYPE DHT11
DHT dht(PIN_DHT, DHTTYPE);
OneWire oneWire(PIN_DS18);
DallasTemperature sensors(&oneWire);

// --- ЦВЕТА ---
#define BLACK    0x0000
#define WHITE    0xFFFF
#define CYAN     0x07FF
#define YELLOW   0xFFE0
#define GREEN    0x07E0
#define RED      0xF800
#define ORANGE   0xFD20
#define DARKGREY 0x39E7

// --- НАСТРОЙКИ В EEPROM ---
struct Settings {
  float tempMin;      // ниже — включить подогрев (R1)
  float tempMax;      // выше — включить охлаждение (R2)
  float tempHardMax;  // аварийный перегрев — подогрев выключается всегда
  int   gasOutLimit;  // утечка снаружи (сырое значение MQ-9)
  int   gasInLimit;   // газ внутри выше — включить откачку (R3)
};

const byte EEPROM_MAGIC = 0xB2;   // новая версия раскладки EEPROM
Settings cfg;

// --- ДАННЫЕ ДАТЧИКОВ ---
int mqIn = 0;
int mqOut = 0;
float humidity = 0.0;
bool humOk = false;
byte humFail = 0;
float tempDS = 0.0;
bool dsValid = false;
bool dsSeen = false;

int prevMqIn = -1;
int prevMqOut = -1;
float prevHumidity = -999.0;
bool prevHumOk = false;
float prevTempDS = -999.0;
bool prevDsValid = false;

// --- РЕЛЕ И РЕЖИМЫ ---
bool relayState[4]  = {false, false, false, false};
bool remoteOwned[4] = {false, false, false, false};  // включено командой с Pi
const int relayPins[4] = {PIN_RELAY_1, PIN_RELAY_2, PIN_RELAY_3, PIN_RELAY_4};
const char* relayNames[4] = {"Heat (R1)", "Cool (R2)", "Pump (R3)", "Auger(R4)"};
bool autoMode = true;

// --- ТРЕВОГИ ---
bool estopLatched = false;
bool leakLatched = false;
bool overheat = false;
bool warmup = true;
bool linkLost = false;
byte leakCount = 0;
unsigned long bootMs = 0;
unsigned long lastLinkMs = 0;
unsigned long augerOnSince = 0;
bool augerTimedOut = false;

// --- ИНТЕРФЕЙС ---
enum ScreenState { SCREEN_MAIN, SCREEN_FULLSCREEN, SCREEN_RELAYS, SCREEN_LIMITS };
ScreenState currentScreen = SCREEN_MAIN;

const int MAIN_ITEMS = 6;
const char* mainMenuNames[MAIN_ITEMS] = {
  "Gas inside", "Gas outside", "Humidity", "Temp DS18", "Relays", "Limits"
};
const int LIMIT_ITEMS = 5;
const char* limitNames[LIMIT_ITEMS] = {
  "Temp Min", "Temp Max", "Overheat", "Gas out alarm", "Gas in pump"
};

int mainIndex = 0, prevMainIndex = 0;
int scrollOffset = 0, prevScrollOffset = 0;
const int VISIBLE_ROWS = 4;
int subIndex = 0, prevSubIndex = 0;
bool isEditingLimit = false;
bool needFullRedraw = true;

int lastClkState;
unsigned long lastEncTime = 0;
unsigned long lastSensorRead = 0;

// кнопки: нажатие / долгое удержание
bool encPrev = HIGH, backPrev = HIGH;
unsigned long encDownAt = 0, backDownAt = 0;
bool encLongDone = false, backLongDone = false;

// нижняя строка подсказок / сообщений
char footerMsg[40] = "";
unsigned long footerMsgUntil = 0;
int lastStatusCode = -1;

// приём команд
char rxBuf[64];
byte rxLen = 0;


// ==========================================
// EEPROM
// ==========================================

void setDefaults() {
  cfg.tempMin = 35.0;       // мезофильный режим
  cfg.tempMax = 38.0;
  cfg.tempHardMax = 45.0;
  cfg.gasOutLimit = 400;    // подобрать по калибровке в чистом воздухе!
  cfg.gasInLimit = 700;
}

bool validSettings(const Settings& s) {
  if (isnan(s.tempMin) || isnan(s.tempMax) || isnan(s.tempHardMax)) return false;
  if (s.tempMin < 0 || s.tempMax > 68) return false;
  if (s.tempMin > s.tempMax - 0.5) return false;
  if (s.tempHardMax < s.tempMax + 2.0 || s.tempHardMax > 70) return false;
  if (s.gasOutLimit < 50 || s.gasOutLimit > 1000) return false;
  if (s.gasInLimit < 50 || s.gasInLimit > 1000) return false;
  return true;
}

void saveSettings() {
  EEPROM.write(0, EEPROM_MAGIC);
  EEPROM.put(1, cfg);
}

void loadSettings() {
  if (EEPROM.read(0) == EEPROM_MAGIC) {
    EEPROM.get(1, cfg);
    if (!validSettings(cfg)) {
      setDefaults();
      saveSettings();
    }
  } else {
    setDefaults();
    saveSettings();
  }
}


// ==========================================
// SETUP
// ==========================================

void setup() {
  MCUSR = 0;
  wdt_disable();

  // Реле — сразу выключить, до всего остального
  for (int i = 0; i < 4; i++) {
    pinMode(relayPins[i], OUTPUT);
    digitalWrite(relayPins[i], RELAY_OFF);
  }

  Serial.begin(SERIAL_BAUD);

  pinMode(ENC_CLK, INPUT_PULLUP);
  pinMode(ENC_DT, INPUT_PULLUP);
  pinMode(ENC_SW, INPUT_PULLUP);
  pinMode(BTN_BACK, INPUT_PULLUP);

  loadSettings();
  lastClkState = digitalRead(ENC_CLK);

  dht.begin();
  sensors.begin();
  sensors.setWaitForConversion(false);
  sensors.requestTemperatures();

  uint16_t ID = tft.readID();
  if (ID == 0xD3D3 || ID == 0xFFFF || ID == 0x0000) ID = 0x9488;
  tft.begin(ID);
  tft.setRotation(1);
  tft.fillScreen(BLACK);

  bootMs = millis();
  lastLinkMs = millis();

  Serial.println(F("{\"type\":\"boot\",\"fw\":\"" FW_VERSION "\"}"));

  readSensors();

#if USE_AVR_WDT
  wdt_enable(WDTO_8S);
#endif
}


// ==========================================
// LOOP
// ==========================================

void loop() {
#if USE_AVR_WDT
  wdt_reset();
#endif

  readSerialCommands();
  handleEncoder();
  handleButtons();

  if (needFullRedraw) {
    drawInterface();
    needFullRedraw = false;
  }

  if (millis() - lastSensorRead >= SENSOR_INTERVAL_MS) {
    lastSensorRead = millis();

    bool prevRelay[4];
    for (int i = 0; i < 4; i++) prevRelay[i] = relayState[i];
    bool prevAuto = autoMode;
    bool prevHeatLock = heatLocked();

    readSensors();
    evaluateAlarms();
    autoControl();
    enforceSafety();
    applyRelayStates();

    updateValuesOnly();
    refreshRelayRows(prevRelay, prevAuto, prevHeatLock);
    drawStatus(false);

    if (augerTimedOut && currentScreen == SCREEN_RELAYS) {
      setFooterMsg("Auger auto-off (time limit)");
    }

    if (footerMsgUntil != 0 && (long)(millis() - footerMsgUntil) >= 0) {
      footerMsgUntil = 0;
      drawFooter();
    }

    sendStatus();
    augerTimedOut = false;
  }
}


// ==========================================
// ДАТЧИКИ
// ==========================================

void readSensors() {
  mqIn = analogRead(PIN_MQ9_IN);
  mqOut = analogRead(PIN_MQ9_OUT);

  float h = dht.readHumidity();
  if (!isnan(h)) {
    humidity = h;
    humFail = 0;
    humOk = true;
  } else if (humFail < 255) {
    humFail++;
    if (humFail >= 5) humOk = false;   // одиночные сбои DHT11 не считаем ошибкой
  }

  float t = sensors.getTempCByIndex(0);
  bool plausible = (t != DEVICE_DISCONNECTED_C && t > -55.0 && t < 125.0);
  if (plausible && t == 85.0 && !dsSeen) plausible = false;  // 85 °C — значение после включения
  if (plausible) {
    tempDS = t;
    dsValid = true;
    dsSeen = true;
  } else {
    dsValid = false;
  }
  sensors.requestTemperatures();
}


// ==========================================
// ТРЕВОГИ И БЕЗОПАСНОСТЬ
// ==========================================

bool heatLocked() {
  return estopLatched || leakLatched || warmup || !dsValid || overheat;
}

void evaluateAlarms() {
  warmup = (millis() - bootMs) < MQ_WARMUP_MS;

  if (!warmup) {
    if (mqOut > cfg.gasOutLimit) {
      if (leakCount < 255) leakCount++;
      if (leakCount >= LEAK_CONFIRM && !leakLatched) {
        leakLatched = true;
        autoMode = false;
        needFullRedraw = true;
      }
    } else {
      leakCount = 0;
    }
  }

  if (dsValid) {
    if (tempDS >= cfg.tempHardMax) overheat = true;
    else if (tempDS <= cfg.tempHardMax - OVERHEAT_HYST) overheat = false;
  } else {
    overheat = false;   // без датчика подогрев и так заблокирован
  }

  // связь с Pi: выключаем то, что Pi включила, если она пропала
  bool anyRemote = false;
  for (int i = 0; i < 4; i++) if (remoteOwned[i]) anyRemote = true;
  if (anyRemote && millis() - lastLinkMs > LINK_TIMEOUT_MS) {
    for (int i = 0; i < 4; i++) {
      if (remoteOwned[i]) {
        relayState[i] = false;
        remoteOwned[i] = false;
      }
    }
    linkLost = true;
  }

  // шнек: автоотключение после долгой непрерывной работы
  if (relayState[R_AUGER] && millis() - augerOnSince > AUGER_MAX_RUN_MS) {
    relayState[R_AUGER] = false;
    remoteOwned[R_AUGER] = false;
    augerTimedOut = true;
  }
}

void autoControl() {
  if (!autoMode) return;

  if (dsValid) {
    if (tempDS < cfg.tempMin) relayState[R_HEAT] = true;
    else if (tempDS >= cfg.tempMin + TEMP_HYST) relayState[R_HEAT] = false;

    if (tempDS > cfg.tempMax) relayState[R_COOL] = true;
    else if (tempDS <= cfg.tempMax - TEMP_HYST) relayState[R_COOL] = false;
  } else {
    relayState[R_HEAT] = false;
    relayState[R_COOL] = false;
  }

  if (warmup) {
    relayState[R_PUMP] = false;
  } else if (mqIn > cfg.gasInLimit) {
    relayState[R_PUMP] = true;
  } else if (mqIn < cfg.gasInLimit - GAS_IN_HYST) {
    relayState[R_PUMP] = false;
  }
}

// Последнее слово всегда за этой функцией: она вызывается перед каждой записью в реле
void enforceSafety() {
  if (estopLatched || leakLatched) {
    for (int i = 0; i < 4; i++) relayState[i] = false;
  }
  if (heatLocked()) relayState[R_HEAT] = false;
  if (warmup) relayState[R_PUMP] = false;
  if (relayState[R_HEAT] && relayState[R_COOL]) relayState[R_HEAT] = false;
  for (int i = 0; i < 4; i++) {
    if (!relayState[i]) remoteOwned[i] = false;
  }
}

void applyRelayStates() {
  for (int i = 0; i < 4; i++) {
    digitalWrite(relayPins[i], relayState[i] ? RELAY_ON : RELAY_OFF);
  }
}

// Запрос на переключение реле (с экрана или с Pi). NULL = успешно, иначе код отказа.
const char* requestRelay(byte i, bool on, bool remote) {
  if (i > 3) return "BAD_ARGS";
  if (on) {
    if (estopLatched) return "ESTOP";
    if (leakLatched) return "LEAK";
    if (i == R_HEAT) {
      if (warmup) return "WARMUP";
      if (!dsValid) return "NO_TEMP";
      if (overheat) return "OVERHEAT";
      if (relayState[R_COOL]) return "INTERLOCK";
    }
    if (i == R_COOL && relayState[R_HEAT]) return "INTERLOCK";
    if (i == R_PUMP && warmup) return "WARMUP";
  }
  if (i <= R_PUMP) autoMode = false;   // ручное управление отключает автоматику
  if (i == R_AUGER && on && !relayState[R_AUGER]) augerOnSince = millis();
  relayState[i] = on;
  remoteOwned[i] = on && remote;
  enforceSafety();
  applyRelayStates();
  return NULL;
}

void setAuto(bool on) {
  autoMode = on;
  if (on) {
    for (int i = 0; i <= R_PUMP; i++) remoteOwned[i] = false;
    autoControl();
  }
  enforceSafety();
  applyRelayStates();
}

void allOff() {
  for (int i = 0; i < 4; i++) {
    relayState[i] = false;
    remoteOwned[i] = false;
  }
  autoMode = false;
  applyRelayStates();
}

void triggerEstop() {
  estopLatched = true;
  allOff();
}

const char* resetAlarms() {
  estopLatched = false;
  linkLost = false;
  if (leakLatched) {
    if (!warmup && mqOut < cfg.gasOutLimit) {
      leakLatched = false;
      leakCount = 0;
    } else {
      return "GAS_STILL_HIGH";
    }
  }
  return NULL;
}

const char* setLimit(const char* key, float v) {
  if (isEditingLimit) return "LOCAL_EDIT";
  Settings s = cfg;
  if (!strcmp(key, "TMIN")) s.tempMin = v;
  else if (!strcmp(key, "TMAX")) s.tempMax = v;
  else if (!strcmp(key, "THARD")) s.tempHardMax = v;
  else if (!strcmp(key, "GOUT")) s.gasOutLimit = (int)v;
  else if (!strcmp(key, "GIN")) s.gasInLimit = (int)v;
  else return "BAD_KEY";
  if (!validSettings(s)) return "OUT_OF_RANGE";
  cfg = s;
  saveSettings();
  return NULL;
}


// ==========================================
// ОБМЕН С RASPBERRY PI
// ==========================================

void printFloatField(const char* key, float v, bool ok) {
  Serial.print(F(",\""));
  Serial.print(key);
  Serial.print(F("\":"));
  if (ok) {
    char b[12];
    dtostrf(v, 0, 1, b);
    Serial.print(b);
  } else {
    Serial.print(F("null"));
  }
}

void printBoolField(const char* key, bool v, bool first) {
  if (!first) Serial.print(',');
  Serial.print('"');
  Serial.print(key);
  Serial.print(F("\":"));
  Serial.print(v ? F("true") : F("false"));
}

void sendStatus() {
  Serial.print(F("{\"type\":\"status\",\"fw\":\"" FW_VERSION "\",\"uptime_s\":"));
  Serial.print(millis() / 1000);
  Serial.print(F(",\"mq_in\":"));
  Serial.print(mqIn);
  Serial.print(F(",\"mq_out\":"));
  Serial.print(mqOut);
  printFloatField("humidity", humidity, humOk);
  printFloatField("temp", tempDS, dsValid);

  Serial.print(F(",\"relays\":{"));
  printBoolField("heat", relayState[R_HEAT], true);
  printBoolField("cool", relayState[R_COOL], false);
  printBoolField("pump", relayState[R_PUMP], false);
  printBoolField("auger", relayState[R_AUGER], false);
  Serial.print(F("},\"remote\":{"));
  printBoolField("heat", remoteOwned[R_HEAT], true);
  printBoolField("cool", remoteOwned[R_COOL], false);
  printBoolField("pump", remoteOwned[R_PUMP], false);
  printBoolField("auger", remoteOwned[R_AUGER], false);
  Serial.print('}');

  Serial.print(F(",\"auto\":"));
  Serial.print(autoMode ? F("true") : F("false"));

  printFloatField("temp_min", cfg.tempMin, true);
  printFloatField("temp_max", cfg.tempMax, true);
  printFloatField("temp_hard_max", cfg.tempHardMax, true);
  Serial.print(F(",\"gas_out_limit\":"));
  Serial.print(cfg.gasOutLimit);
  Serial.print(F(",\"gas_in_limit\":"));
  Serial.print(cfg.gasInLimit);

  Serial.print(F(",\"alarms\":{"));
  printBoolField("estop", estopLatched, true);
  printBoolField("leak", leakLatched, false);
  printBoolField("overheat", overheat, false);
  printBoolField("warmup", warmup, false);
  printBoolField("no_temp", !dsValid, false);
  printBoolField("link_lost", linkLost, false);
  printBoolField("auger_timeout", augerTimedOut, false);
  Serial.println(F("}}"));
}

void sendAck(const char* cmd, const char* err) {
  Serial.print(F("{\"type\":\"ack\",\"cmd\":\""));
  Serial.print(cmd);
  Serial.print(F("\",\"ok\":"));
  if (err) {
    Serial.print(F("false,\"error\":\""));
    Serial.print(err);
    Serial.println(F("\"}"));
  } else {
    Serial.println(F("true}"));
  }
}

void handleCommand(char* line) {
  for (char* p = line; *p; ++p) *p = toupper(*p);
  char* cmd = strtok(line, " ");
  if (!cmd) return;

  lastLinkMs = millis();
  linkLost = false;

  const char* err = NULL;
  bool changed = false;

  if (!strcmp(cmd, "PING")) {
    // только отметка связи
  } else if (!strcmp(cmd, "GET")) {
    sendStatus();
    return;
  } else if (!strcmp(cmd, "RELAY")) {
    char* a = strtok(NULL, " ");
    char* b = strtok(NULL, " ");
    if (!a || !b) {
      err = "BAD_ARGS";
    } else {
      int n = atoi(a);
      int s = atoi(b);
      if (n < 1 || n > 4 || (s != 0 && s != 1)) err = "BAD_ARGS";
      else {
        err = requestRelay(n - 1, s == 1, true);
        changed = (err == NULL);
      }
    }
  } else if (!strcmp(cmd, "AUTO")) {
    char* a = strtok(NULL, " ");
    if (!a || (strcmp(a, "0") && strcmp(a, "1"))) err = "BAD_ARGS";
    else {
      if (a[0] == '1' && (estopLatched || leakLatched)) err = estopLatched ? "ESTOP" : "LEAK";
      else {
        setAuto(a[0] == '1');
        changed = true;
      }
    }
  } else if (!strcmp(cmd, "SET")) {
    char* key = strtok(NULL, " ");
    char* val = strtok(NULL, " ");
    if (!key || !val) err = "BAD_ARGS";
    else {
      err = setLimit(key, atof(val));
      changed = (err == NULL);
    }
  } else if (!strcmp(cmd, "ESTOP")) {
    triggerEstop();
    changed = true;
  } else if (!strcmp(cmd, "RESET")) {
    err = resetAlarms();
    changed = true;
  } else if (!strcmp(cmd, "ALLOFF")) {
    allOff();
    changed = true;
  } else {
    err = "UNKNOWN";
  }

  sendAck(cmd, err);

  if (changed) {
    enforceSafety();
    applyRelayStates();
    if (currentScreen == SCREEN_RELAYS || (currentScreen == SCREEN_LIMITS && !isEditingLimit)) {
      needFullRedraw = true;
    }
    drawStatus(true);
  }
}

void readSerialCommands() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      rxBuf[rxLen] = 0;
      if (rxLen > 0) handleCommand(rxBuf);
      rxLen = 0;
    } else if (rxLen < sizeof(rxBuf) - 1) {
      rxBuf[rxLen++] = c;
    } else {
      rxLen = 0;   // слишком длинная строка — отбрасываем
    }
  }
}


// ==========================================
// ТЕКСТЫ ДЛЯ ЭКРАНА
// ==========================================

int currentStatus() {
  if (estopLatched) return 6;
  if (leakLatched) return 5;
  if (overheat) return 4;
  if (warmup) return 1;
  if (!dsValid) return 2;
  if (linkLost) return 3;
  return 0;
}

const char* statusText(int c) {
  switch (c) {
    case 1: return "WARM-UP";
    case 2: return "NO TEMP";
    case 3: return "LINK LOST";
    case 4: return "OVERHEAT";
    case 5: return "GAS LEAK!";
    case 6: return "E-STOP";
    default: return "OK";
  }
}

uint16_t statusColor(int c) {
  if (c >= 4) return RED;
  if (c >= 1) return ORANGE;
  return GREEN;
}

const char* reasonText(const char* e) {
  if (!e) return "";
  if (!strcmp(e, "INTERLOCK")) return "Heat+Cool not allowed";
  if (!strcmp(e, "NO_TEMP")) return "No temp sensor: heat off";
  if (!strcmp(e, "WARMUP")) return "Gas sensors warming up";
  if (!strcmp(e, "OVERHEAT")) return "Overheat: heat blocked";
  if (!strcmp(e, "ESTOP")) return "E-STOP: hold OK 3s";
  if (!strcmp(e, "LEAK")) return "Gas leak alarm active";
  if (!strcmp(e, "GAS_STILL_HIGH")) return "Gas still high!";
  return e;
}

void padTo(char* s, byte width, size_t cap) {
  size_t l = strlen(s);
  while (l < width && l < cap - 1) s[l++] = ' ';
  s[l] = 0;
}

void formatMainValue(int idx, char* out, size_t cap) {
  char num[12];
  switch (idx) {
    case 0:
      snprintf(out, cap, "%d raw", mqIn);
      break;
    case 1:
      snprintf(out, cap, "%d raw", mqOut);
      break;
    case 2:
      if (humOk) {
        dtostrf(humidity, 0, 1, num);
        snprintf(out, cap, "%s %%", num);
      } else {
        strncpy(out, "ERR", cap);
      }
      break;
    case 3:
      if (dsValid) {
        dtostrf(tempDS, 0, 1, num);
        snprintf(out, cap, "%s C", num);
      } else {
        strncpy(out, "NO SENS", cap);
      }
      break;
    case 4:
    case 5:
      strncpy(out, ">", cap);
      out[cap - 1] = 0;
      return;
    default:
      out[0] = 0;
      return;
  }
  out[cap - 1] = 0;
  padTo(out, 9, cap);
}

void formatLimitValue(int idx, char* out, size_t cap, bool editing) {
  char num[12];
  if (idx <= 2) {
    float v = (idx == 0) ? cfg.tempMin : (idx == 1) ? cfg.tempMax : cfg.tempHardMax;
    dtostrf(v, 0, 1, num);
    if (editing) snprintf(out, cap, "<%s>", num);
    else snprintf(out, cap, "%s C", num);
  } else {
    int v = (idx == 3) ? cfg.gasOutLimit : cfg.gasInLimit;
    if (editing) snprintf(out, cap, "<%d>", v);
    else snprintf(out, cap, "%d", v);
  }
  out[cap - 1] = 0;
  padTo(out, 8, cap);
}


// ==========================================
// ОТРИСОВКА
// ==========================================

void drawHeader(const char* title) {
  tft.setTextSize(3);
  tft.setTextColor(CYAN, BLACK);
  tft.setCursor(20, 15);
  tft.print(title);
  tft.drawFastHLine(0, 50, 480, WHITE);
}

void drawStatus(bool force) {
  int c = currentStatus();
  if (!force && c == lastStatusCode) return;
  lastStatusCode = c;

  int x, y, w;
  if (currentScreen == SCREEN_FULLSCREEN) { x = 270; y = 282; w = 196; }
  else { x = 300; y = 20; w = 176; }

  tft.fillRect(x - 4, y - 4, w, 22, BLACK);
  tft.setTextSize(2);
  tft.setTextColor(statusColor(c), BLACK);
  tft.setCursor(x, y);
  tft.print(statusText(c));
}

void setFooterMsg(const char* m) {
  strncpy(footerMsg, m, sizeof(footerMsg));
  footerMsg[sizeof(footerMsg) - 1] = 0;
  footerMsgUntil = millis() + 2500;
  if (footerMsgUntil == 0) footerMsgUntil = 1;
  drawFooter();
}

void drawFooter() {
  if (currentScreen != SCREEN_RELAYS && currentScreen != SCREEN_LIMITS) return;
  char buf[40];
  if (footerMsgUntil != 0) {
    strncpy(buf, footerMsg, sizeof(buf));
  } else if (currentScreen == SCREEN_RELAYS) {
    strncpy(buf, "Click:Toggle Back:Menu Hold:Stop", sizeof(buf));
  } else if (isEditingLimit) {
    strncpy(buf, "Rotate:+/- Click:Save Back:Cancel", sizeof(buf));
  } else {
    strncpy(buf, "Click:Edit  Back:Menu", sizeof(buf));
  }
  buf[sizeof(buf) - 1] = 0;
  padTo(buf, 37, sizeof(buf));
  tft.setTextSize(2);
  tft.setTextColor(footerMsgUntil != 0 ? ORANGE : YELLOW, BLACK);
  tft.setCursor(12, 292);
  tft.print(buf);
}

void drawMainRow(int row, int itemIdx, bool isSelected) {
  int y = 70 + row * 60;
  uint16_t bg = isSelected ? CYAN : BLACK;
  uint16_t fg = isSelected ? BLACK : WHITE;

  if (isSelected) {
    tft.fillRoundRect(10, y - 8, 460, 50, 8, CYAN);
  } else {
    tft.fillRoundRect(10, y - 8, 460, 50, 8, BLACK);
    tft.drawRoundRect(10, y - 8, 460, 50, 8, DARKGREY);
  }

  tft.setTextSize(3);
  tft.setTextColor(fg, bg);
  tft.setCursor(25, y + 5);
  tft.print(mainMenuNames[itemIdx]);

  char val[16];
  formatMainValue(itemIdx, val, sizeof(val));
  int valX = (itemIdx >= 4) ? 430 : 275;
  tft.setCursor(valX, y + 5);
  tft.print(val);
}

void drawRelayRow(int i, bool isSelected) {
  int y = 60 + i * 45;
  uint16_t bg = isSelected ? CYAN : BLACK;

  if (isSelected) {
    tft.fillRoundRect(10, y - 5, 460, 40, 8, CYAN);
  } else {
    tft.fillRoundRect(10, y - 5, 460, 40, 8, BLACK);
    tft.drawRoundRect(10, y - 5, 460, 40, 8, DARKGREY);
  }

  tft.setTextSize(3);
  tft.setTextColor(isSelected ? BLACK : WHITE, bg);
  tft.setCursor(25, y + 3);

  if (i < 4) {
    tft.print(relayNames[i]);
    tft.setCursor(365, y + 3);
    bool locked = (i == R_HEAT && !relayState[i] && heatLocked());
    if (!isSelected) {
      uint16_t c = relayState[i] ? GREEN : (locked ? ORANGE : RED);
      tft.setTextColor(c, bg);
    }
    if (relayState[i]) tft.print(F("ON "));
    else if (locked) tft.print(F("LCK"));
    else tft.print(F("OFF"));
  } else {
    tft.print(F("Auto mode"));
    tft.setCursor(345, y + 3);
    if (!isSelected) tft.setTextColor(autoMode ? GREEN : YELLOW, bg);
    tft.print(autoMode ? F("AUTO") : F("MAN "));
  }
}

void redrawRelayRows() {
  for (int i = 0; i < 5; i++) drawRelayRow(i, i == subIndex);
}

void refreshRelayRows(const bool prevRelay[4], bool prevAuto, bool prevHeatLock) {
  if (currentScreen != SCREEN_RELAYS) return;
  bool lockNow = heatLocked();
  for (int i = 0; i < 4; i++) {
    bool changed = (prevRelay[i] != relayState[i]) || (i == R_HEAT && prevHeatLock != lockNow);
    if (changed) drawRelayRow(i, subIndex == i);
  }
  if (prevAuto != autoMode) drawRelayRow(4, subIndex == 4);
}

void drawLimitRow(int i, bool isSelected) {
  int y = 62 + i * 44;
  uint16_t bg = BLACK;

  if (isSelected) {
    bg = isEditingLimit ? YELLOW : CYAN;
    tft.fillRoundRect(10, y - 6, 460, 40, 8, bg);
  } else {
    tft.fillRoundRect(10, y - 6, 460, 40, 8, BLACK);
    tft.drawRoundRect(10, y - 6, 460, 40, 8, DARKGREY);
  }

  tft.setTextSize(3);
  tft.setTextColor(isSelected ? BLACK : WHITE, bg);
  tft.setCursor(22, y + 4);
  tft.print(limitNames[i]);

  char val[16];
  formatLimitValue(i, val, sizeof(val), isSelected && isEditingLimit);
  tft.setCursor(300, y + 4);
  tft.print(val);
}

void drawInterface() {
  tft.fillScreen(BLACK);

  prevMqIn = mqIn;
  prevMqOut = mqOut;
  prevHumidity = humidity;
  prevHumOk = humOk;
  prevTempDS = tempDS;
  prevDsValid = dsValid;

  if (currentScreen == SCREEN_FULLSCREEN) {
    tft.drawRect(5, 5, 470, 310, CYAN);
    tft.setTextSize(4);
    tft.setTextColor(CYAN, BLACK);
    tft.setCursor(30, 30);
    tft.print(mainMenuNames[mainIndex]);
    tft.drawFastHLine(20, 80, 440, DARKGREY);

    char val[16];
    formatMainValue(mainIndex, val, sizeof(val));
    tft.setTextSize(7);
    tft.setTextColor(WHITE, BLACK);
    tft.setCursor(30, 140);
    tft.print(val);

    tft.setTextSize(2);
    tft.setTextColor(YELLOW, BLACK);
    tft.setCursor(30, 280);
    tft.print(F("Back button to exit"));

  } else if (currentScreen == SCREEN_MAIN) {
    drawHeader("SENSOR MONITOR");
    for (int row = 0; row < VISIBLE_ROWS; row++) {
      int itemIdx = scrollOffset + row;
      if (itemIdx >= MAIN_ITEMS) break;
      drawMainRow(row, itemIdx, itemIdx == mainIndex);
    }

  } else if (currentScreen == SCREEN_RELAYS) {
    drawHeader("RELAY CONTROL");
    redrawRelayRows();
    drawFooter();

  } else if (currentScreen == SCREEN_LIMITS) {
    drawHeader("LIMITS");
    for (int i = 0; i < LIMIT_ITEMS; i++) drawLimitRow(i, i == subIndex);
    drawFooter();
  }

  drawStatus(true);
}

void updateValuesOnly() {
  bool changed[4];
  changed[0] = (mqIn != prevMqIn);
  changed[1] = (mqOut != prevMqOut);
  changed[2] = (fabs(humidity - prevHumidity) >= 0.1) || (humOk != prevHumOk);
  changed[3] = (fabs(tempDS - prevTempDS) >= 0.1) || (dsValid != prevDsValid);

  prevMqIn = mqIn;
  prevMqOut = mqOut;
  prevHumidity = humidity;
  prevHumOk = humOk;
  prevTempDS = tempDS;
  prevDsValid = dsValid;

  char val[16];

  if (currentScreen == SCREEN_FULLSCREEN) {
    if (mainIndex < 4 && changed[mainIndex]) {
      formatMainValue(mainIndex, val, sizeof(val));
      tft.setTextSize(7);
      tft.setTextColor(WHITE, BLACK);
      tft.setCursor(30, 140);
      tft.print(val);
    }
  } else if (currentScreen == SCREEN_MAIN) {
    for (int row = 0; row < VISIBLE_ROWS; row++) {
      int itemIdx = scrollOffset + row;
      if (itemIdx >= 4) continue;
      if (!changed[itemIdx]) continue;
      int y = 70 + row * 60;
      bool isSelected = (itemIdx == mainIndex);
      formatMainValue(itemIdx, val, sizeof(val));
      tft.setTextSize(3);
      tft.setTextColor(isSelected ? BLACK : WHITE, isSelected ? CYAN : BLACK);
      tft.setCursor(275, y + 5);
      tft.print(val);
    }
  }
}


// ==========================================
// ЭНКОДЕР
// ==========================================

void adjustLimit(int idx, int dir) {
  switch (idx) {
    case 0:
      cfg.tempMin += dir * 0.5;
      if (cfg.tempMin < 0) cfg.tempMin = 0;
      if (cfg.tempMin > cfg.tempMax - 0.5) cfg.tempMin = cfg.tempMax - 0.5;
      break;
    case 1:
      cfg.tempMax += dir * 0.5;
      if (cfg.tempMax < cfg.tempMin + 0.5) cfg.tempMax = cfg.tempMin + 0.5;
      if (cfg.tempMax > cfg.tempHardMax - 2.0) cfg.tempMax = cfg.tempHardMax - 2.0;
      break;
    case 2:
      cfg.tempHardMax += dir * 0.5;
      if (cfg.tempHardMax < cfg.tempMax + 2.0) cfg.tempHardMax = cfg.tempMax + 2.0;
      if (cfg.tempHardMax > 70) cfg.tempHardMax = 70;
      break;
    case 3:
      cfg.gasOutLimit += dir * 10;
      if (cfg.gasOutLimit < 50) cfg.gasOutLimit = 50;
      if (cfg.gasOutLimit > 1000) cfg.gasOutLimit = 1000;
      break;
    case 4:
      cfg.gasInLimit += dir * 10;
      if (cfg.gasInLimit < 50) cfg.gasInLimit = 50;
      if (cfg.gasInLimit > 1000) cfg.gasInLimit = 1000;
      break;
  }
}

void handleEncoder() {
  if (currentScreen == SCREEN_FULLSCREEN) return;

  int currentClkState = digitalRead(ENC_CLK);

  if (lastClkState == HIGH && currentClkState == LOW && millis() - lastEncTime > 50) {
    lastEncTime = millis();
    int dir = (digitalRead(ENC_DT) == HIGH) ? 1 : -1;

    if (currentScreen == SCREEN_MAIN) {
      prevMainIndex = mainIndex;
      prevScrollOffset = scrollOffset;
      mainIndex += dir;
      if (mainIndex >= MAIN_ITEMS) mainIndex = 0;
      if (mainIndex < 0) mainIndex = MAIN_ITEMS - 1;

      if (mainIndex < scrollOffset) scrollOffset = mainIndex;
      else if (mainIndex >= scrollOffset + VISIBLE_ROWS) scrollOffset = mainIndex - VISIBLE_ROWS + 1;

      if (scrollOffset == prevScrollOffset) {
        drawMainRow(prevMainIndex - scrollOffset, prevMainIndex, false);
        drawMainRow(mainIndex - scrollOffset, mainIndex, true);
      } else {
        for (int row = 0; row < VISIBLE_ROWS; row++) {
          int idx = scrollOffset + row;
          drawMainRow(row, idx, idx == mainIndex);
        }
      }

    } else if (currentScreen == SCREEN_RELAYS) {
      prevSubIndex = subIndex;
      subIndex += dir;
      if (subIndex >= 5) subIndex = 0;
      if (subIndex < 0) subIndex = 4;
      drawRelayRow(prevSubIndex, false);
      drawRelayRow(subIndex, true);

    } else if (currentScreen == SCREEN_LIMITS) {
      if (isEditingLimit) {
        adjustLimit(subIndex, dir);
        drawLimitRow(subIndex, true);
      } else {
        prevSubIndex = subIndex;
        subIndex += dir;
        if (subIndex >= LIMIT_ITEMS) subIndex = 0;
        if (subIndex < 0) subIndex = LIMIT_ITEMS - 1;
        drawLimitRow(prevSubIndex, false);
        drawLimitRow(subIndex, true);
      }
    }
  }

  lastClkState = currentClkState;
}


// ==========================================
// КНОПКИ: короткое нажатие и долгое удержание
// ==========================================

void onEncClick() {
  if (currentScreen == SCREEN_MAIN) {
    if (mainIndex < 4) {
      currentScreen = SCREEN_FULLSCREEN;
    } else if (mainIndex == 4) {
      subIndex = 0;
      currentScreen = SCREEN_RELAYS;
    } else {
      subIndex = 0;
      isEditingLimit = false;
      currentScreen = SCREEN_LIMITS;
    }
    needFullRedraw = true;

  } else if (currentScreen == SCREEN_RELAYS) {
    if (subIndex < 4) {
      const char* e = requestRelay(subIndex, !relayState[subIndex], false);
      if (e) setFooterMsg(reasonText(e));
      redrawRelayRows();
    } else {
      if (!autoMode && (estopLatched || leakLatched)) {
        setFooterMsg(reasonText(estopLatched ? "ESTOP" : "LEAK"));
      } else {
        setAuto(!autoMode);
        redrawRelayRows();
      }
    }

  } else if (currentScreen == SCREEN_LIMITS) {
    if (isEditingLimit) {
      saveSettings();
      isEditingLimit = false;
      if (!estopLatched && !leakLatched) setAuto(true);
    } else {
      isEditingLimit = true;
    }
    drawLimitRow(subIndex, true);
    drawFooter();
  }
}

void onBackClick() {
  if (currentScreen != SCREEN_MAIN) {
    if (isEditingLimit) loadSettings();   // отмена правки
    isEditingLimit = false;
    currentScreen = SCREEN_MAIN;
    needFullRedraw = true;
  }
}

void handleButtons() {
  unsigned long now = millis();
  bool enc = digitalRead(ENC_SW);
  bool back = digitalRead(BTN_BACK);

  // --- кнопка энкодера: клик / удержание 3 с = сброс тревог ---
  if (enc == LOW && encPrev == HIGH) {
    encDownAt = now;
    encLongDone = false;
  }
  if (enc == LOW && !encLongDone && now - encDownAt >= RESET_HOLD_MS) {
    encLongDone = true;
    const char* e = resetAlarms();
    if (e) setFooterMsg(reasonText(e));
    else setFooterMsg("Alarms reset");
    needFullRedraw = true;
  }
  if (enc == HIGH && encPrev == LOW) {
    unsigned long held = now - encDownAt;
    if (!encLongDone && held > 30) onEncClick();
  }
  encPrev = enc;

  // --- BACK: клик / удержание 2 с = АВАРИЙНАЯ ОСТАНОВКА ---
  if (back == LOW && backPrev == HIGH) {
    backDownAt = now;
    backLongDone = false;
  }
  if (back == LOW && !backLongDone && now - backDownAt >= ESTOP_HOLD_MS) {
    backLongDone = true;
    triggerEstop();
    enforceSafety();
    applyRelayStates();
    needFullRedraw = true;
  }
  if (back == HIGH && backPrev == LOW) {
    unsigned long held = now - backDownAt;
    if (!backLongDone && held > 30) onBackClick();
  }
  backPrev = back;
}
