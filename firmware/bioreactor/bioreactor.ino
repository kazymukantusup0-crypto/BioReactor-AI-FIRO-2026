/*
  BioReactor AI — Arduino firmware (MAIN protection layer).
  Chain: sensors + 3 relays -> THIS ARDUINO -> USB Serial -> Raspberry Pi -> network -> laptop.

  Protocol (docs/hardware_protocol.md), one JSON object per line, 115200 baud:
    Arduino -> Pi  every 1 s:
      {"type":"state","seq":12,"uptime_ms":24000,"temp_c":36.8,"rh_pct":88.0,"gas_in":512,"gas_out":95,"p_kpa":1.42,
       "relays":{"heat":1,"cool":0,"pump":0},"alarms":{"leak":0,"overheat":0,"watchdog":0,"temp_sensor":0,"warmup":0}}
    Pi -> Arduino:
      {"cmd":"relay","name":"heat","state":1,"id":17}   {"cmd":"ping","id":18}   {"cmd":"all_off","id":19}   {"cmd":"reset","id":20}
    Arduino -> Pi  answer to every command:
      {"type":"ack","id":17,"ok":1,"relays":{...}}   or   {"type":"ack","id":17,"ok":0,"reason":"interlock","relays":{...}}

  PROTECTION HERE (works even if the Pi and the laptop are dead):
    * at start every relay is OFF (pins are set before anything else);
    * gas outside >= GAS_OUT_LEAK -> heater OFF and LOCKED until {"cmd":"reset"} (refused while it still leaks);
    * temperature >= OVERHEAT_C -> heater OFF, refused until it is below OVERHEAT_RELEASE_C;
    * temperature sensor gives no value -> heater OFF and refused (fail-safe: never heat blind);
    * MQ sensors warm up after power-on (MQ_WARMUP_MS): heater refused meanwhile, leak check starts after;
    * heater and cooler never ON together (the second command is refused: "interlock");
    * no command / ping for WATCHDOG_MS -> ALL relays OFF;
    * pressure <= PUMP_STOP_KPA -> pump OFF (no vacuum in the barrel).
  The virtual Arduino (raspberry/bioreactor_pi/virtual_arduino.py) implements the same rules for tests.

  Libraries (Arduino IDE -> Library Manager): ArduinoJson (v7) by Benoit Blanchon;
  if USE_DS18B20 = 1: OneWire + DallasTemperature;  if USE_DHT = 1: "DHT sensor library" by Adafruit.
*/

#include <ArduinoJson.h>

// ======================= SETTINGS — PLACEHOLDERS, CHECK BEFORE CONNECTING THE REAL REACTOR =======================
// ---- Pins (Arduino Uno / Nano) ----
const uint8_t PIN_RELAY_HEAT = 7;     // relay 1: heater
const uint8_t PIN_RELAY_COOL = 8;     // relay 2: cooling (fan / water pump of the cooler)
const uint8_t PIN_RELAY_PUMP = 9;     // relay 3: gas pump (pumping the gas out of the barrel)
const bool RELAY_ACTIVE_LOW = true;   // most cheap relay modules switch ON with LOW. false = ON with HIGH.

const uint8_t PIN_TEMP_ONEWIRE = 2;   // temperature inside: DS18B20 waterproof probe (placeholder model)
const uint8_t PIN_DHT = 3;            // humidity: DHT22 (placeholder model)
const uint8_t PIN_MQ_IN = A0;         // gas inside the barrel: MQ-4 analog output (placeholder model)
const uint8_t PIN_MQ_OUT = A1;        // gas outside (leak sensor): MQ-4 / MQ-2 analog output (placeholder model)
const uint8_t PIN_PRESSURE = A2;      // gas pressure: analog sensor, e.g. MPX5010DP 0..10 kPa (placeholder model)

#define USE_DS18B20 1                 // 0 = no temperature sensor yet: temp_c = null, heater is always refused
#define USE_DHT 1                     // 0 = no humidity sensor yet: rh_pct = null

// ---- Thresholds (the same numbers as raspberry/bioreactor_pi/default_config.json) ----
const float OVERHEAT_C = 45.0;        // heater OFF at or above
const float OVERHEAT_RELEASE_C = 43.0; // heater allowed again below
const int GAS_OUT_LEAK = 400;         // raw ADC of the outside MQ sensor: leak (calibrate with the sensor test sketch!)
const float PUMP_STOP_KPA = 0.1;      // pump OFF when the barrel is empty of gas

// ---- Timings ----
const unsigned long STATE_EVERY_MS = 1000;   // state line every second
const unsigned long WATCHDOG_MS = 10000;     // no command / ping for 10 s -> all relays OFF
const unsigned long MQ_WARMUP_MS = 60000;    // MQ heaters need ~1 min after power-on (datasheet: longer for accuracy)

// ---- Pressure sensor conversion (MPX5010DP: Vout = Vs * (0.09 * P + 0.04), P in kPa) — placeholder ----
const float PRESSURE_OFFSET = 0.04;
const float PRESSURE_SLOPE = 0.09;
// ==================================================================================================================

#if USE_DS18B20
#include <OneWire.h>
#include <DallasTemperature.h>
OneWire oneWire(PIN_TEMP_ONEWIRE);
DallasTemperature tempSensor(&oneWire);
#endif
#if USE_DHT
#include <DHT.h>
DHT dht(PIN_DHT, DHT22);
#endif

const char *RELAY_NAMES[3] = {"heat", "cool", "pump"};
const uint8_t RELAY_PINS[3] = {PIN_RELAY_HEAT, PIN_RELAY_COOL, PIN_RELAY_PUMP};
enum { HEAT = 0, COOL = 1, PUMP = 2 };

bool relayOn[3] = {false, false, false};
bool alarmLeak = false, alarmOverheat = false, alarmWatchdog = false, alarmTempSensor = false, alarmWarmup = true;
float tempC = NAN, rhPct = NAN, pKpa = NAN;
int gasIn = 0, gasOut = 0;
unsigned long lastCommandMs = 0, lastStateMs = 0;
unsigned long seq = 0;
char lineBuf[160];
uint8_t lineLen = 0;

void writeRelay(uint8_t index, bool on) {
  relayOn[index] = on;
  digitalWrite(RELAY_PINS[index], (on ^ RELAY_ACTIVE_LOW) ? HIGH : LOW);
}

void allOff() {
  for (uint8_t i = 0; i < 3; i++) writeRelay(i, false);
}

void sendEvent(const char *code) {
  JsonDocument doc;
  doc["type"] = "event";
  doc["code"] = code;
  serializeJson(doc, Serial);
  Serial.println();
}

void heatOff(const char *code) {
  if (relayOn[HEAT]) {
    writeRelay(HEAT, false);
    sendEvent(code);
  }
}

void addRelays(JsonDocument &doc) {
  JsonObject relays = doc["relays"].to<JsonObject>();
  for (uint8_t i = 0; i < 3; i++) relays[RELAY_NAMES[i]] = relayOn[i] ? 1 : 0;
}

void sendAck(long id, bool ok, const char *reason) {
  JsonDocument doc;
  doc["type"] = "ack";
  doc["id"] = id;
  doc["ok"] = ok ? 1 : 0;
  if (!ok) doc["reason"] = reason;
  addRelays(doc);
  serializeJson(doc, Serial);
  Serial.println();
}

// ------------------------------------------------ sensors ------------------------------------------------
void readSensors() {
#if USE_DS18B20
  float t = tempSensor.getTempCByIndex(0);   // result of the request started one second ago
  tempC = (t == DEVICE_DISCONNECTED_C || t < -40 || t > 125) ? NAN : t;
  tempSensor.requestTemperatures();          // non-blocking (setWaitForConversion(false)), ready next second
#else
  tempC = NAN;
#endif
#if USE_DHT
  rhPct = dht.readHumidity();
#else
  rhPct = NAN;
#endif
  gasIn = analogRead(PIN_MQ_IN);    // raw 0..1023: an INDICATOR of gas, NOT % methane
  gasOut = analogRead(PIN_MQ_OUT);
  float ratio = analogRead(PIN_PRESSURE) / 1023.0;
  float p = (ratio - PRESSURE_OFFSET) / PRESSURE_SLOPE;
  pKpa = p < 0 ? 0 : p;
}

// ------------------------------------------------ protection ------------------------------------------------
void protect() {
  unsigned long now = millis();
  if (alarmWarmup && now >= MQ_WARMUP_MS) alarmWarmup = false;
  if (!alarmWarmup && gasOut >= GAS_OUT_LEAK && !alarmLeak) {
    alarmLeak = true;
    sendEvent("leak");
  }
  if (alarmLeak) heatOff("leak_heat_off");
  alarmTempSensor = isnan(tempC);
  if (alarmTempSensor) {
    heatOff("temp_sensor_heat_off");
  } else if (tempC >= OVERHEAT_C) {
    alarmOverheat = true;
  } else if (tempC < OVERHEAT_RELEASE_C) {
    alarmOverheat = false;
  }
  if (alarmOverheat) heatOff("overheat_heat_off");
  if (now - lastCommandMs >= WATCHDOG_MS && !alarmWatchdog) {
    alarmWatchdog = true;
    if (relayOn[HEAT] || relayOn[COOL] || relayOn[PUMP]) {
      allOff();
      sendEvent("watchdog_all_off");
    }
  }
  if (relayOn[PUMP] && !isnan(pKpa) && pKpa <= PUMP_STOP_KPA) {
    writeRelay(PUMP, false);
    sendEvent("pump_empty_off");
  }
}

void sendState() {
  JsonDocument doc;
  doc["type"] = "state";
  doc["seq"] = ++seq;
  doc["uptime_ms"] = millis();
  if (isnan(tempC)) doc["temp_c"] = nullptr; else doc["temp_c"] = round(tempC * 100) / 100.0;
  if (isnan(rhPct)) doc["rh_pct"] = nullptr; else doc["rh_pct"] = round(rhPct * 10) / 10.0;
  doc["gas_in"] = gasIn;
  doc["gas_out"] = gasOut;
  if (isnan(pKpa)) doc["p_kpa"] = nullptr; else doc["p_kpa"] = round(pKpa * 1000) / 1000.0;
  addRelays(doc);
  JsonObject alarms = doc["alarms"].to<JsonObject>();
  alarms["leak"] = alarmLeak ? 1 : 0;
  alarms["overheat"] = alarmOverheat ? 1 : 0;
  alarms["watchdog"] = alarmWatchdog ? 1 : 0;
  alarms["temp_sensor"] = alarmTempSensor ? 1 : 0;
  alarms["warmup"] = alarmWarmup ? 1 : 0;
  serializeJson(doc, Serial);
  Serial.println();
}

// ------------------------------------------------ commands ------------------------------------------------
int relayIndex(const char *name) {
  for (uint8_t i = 0; i < 3; i++) if (strcmp(name, RELAY_NAMES[i]) == 0) return i;
  return -1;
}

void handleLine(const char *line) {
  JsonDocument doc;
  if (deserializeJson(doc, line)) return;   // not JSON: ignored (no ack: there is no id to answer)
  const char *cmd = doc["cmd"] | "";
  long id = doc["id"] | 0L;
  lastCommandMs = millis();                 // any valid command feeds the watchdog
  alarmWatchdog = false;
  if (strcmp(cmd, "ping") == 0) {
    sendAck(id, true, nullptr);
  } else if (strcmp(cmd, "all_off") == 0) {
    allOff();
    sendAck(id, true, nullptr);
  } else if (strcmp(cmd, "reset") == 0) {
    if (gasOut >= GAS_OUT_LEAK) {
      sendAck(id, false, "still_leaking");
    } else {
      alarmLeak = false;
      sendAck(id, true, nullptr);
    }
  } else if (strcmp(cmd, "relay") == 0) {
    int index = relayIndex(doc["name"] | "");
    bool on = (doc["state"] | 0) == 1;
    if (index < 0) { sendAck(id, false, "unknown_relay"); return; }
    if (on && index == HEAT) {
      if (alarmLeak) { sendAck(id, false, "leak_lock"); return; }
      if (alarmTempSensor) { sendAck(id, false, "temp_sensor"); return; }
      if (alarmOverheat) { sendAck(id, false, "overheat"); return; }
      if (alarmWarmup) { sendAck(id, false, "warmup"); return; }
    }
    if (on && ((index == HEAT && relayOn[COOL]) || (index == COOL && relayOn[HEAT]))) {
      sendAck(id, false, "interlock");
      return;
    }
    writeRelay(index, on);
    sendAck(id, true, nullptr);
  } else {
    sendAck(id, false, "bad_cmd");
  }
}

void readSerial() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (lineLen > 0) {
        lineBuf[lineLen] = '\0';
        handleLine(lineBuf);
        lineLen = 0;
      }
    } else if (lineLen < sizeof(lineBuf) - 1) {
      lineBuf[lineLen++] = c;
    } else {
      lineLen = 0;   // too long: dropped
    }
  }
}

void setup() {
  // FIRST: every relay OFF (before the serial port, before the sensors).
  for (uint8_t i = 0; i < 3; i++) {
    digitalWrite(RELAY_PINS[i], RELAY_ACTIVE_LOW ? HIGH : LOW);
    pinMode(RELAY_PINS[i], OUTPUT);
  }
  allOff();
  Serial.begin(115200);
#if USE_DS18B20
  tempSensor.begin();
  tempSensor.setWaitForConversion(false);
  tempSensor.requestTemperatures();
#endif
#if USE_DHT
  dht.begin();
#endif
  lastCommandMs = millis();
  Serial.println(F("{\"type\":\"boot\",\"fw\":\"0.1\",\"proto\":1}"));
}

void loop() {
  readSerial();
  unsigned long now = millis();
  if (now - lastStateMs >= STATE_EVERY_MS) {
    lastStateMs = now;
    readSensors();
    protect();
    sendState();
  } else {
    protect();   // watchdog and locks are checked all the time, not only once per second
  }
}
