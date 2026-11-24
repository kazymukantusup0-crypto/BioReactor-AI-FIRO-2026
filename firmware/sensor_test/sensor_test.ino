/*
  BioReactor AI — SENSOR TEST sketch (for wiring and calibration, NOT for the reactor in operation).
  Prints the raw values of every sensor twice a second in the Serial Monitor (115200 baud). Relays stay OFF.

  How to use:
    1. Upload, open Tools -> Serial Monitor, 115200.
    2. Wait 1-2 minutes: MQ sensors heat up, their numbers fall and settle — note the value in clean air.
    3. Leak threshold (GAS_OUT_LEAK in bioreactor.ino): a lighter's gas (NOT lit) near the outside sensor raises the
       number; choose a threshold between clean air and that value. Write both numbers into docs/hardware_protocol.md.
    4. Pressure: with the barrel open the reading must be ~0 kPa; correct PRESSURE_OFFSET if it is not.
  Pins and models are the same placeholders as in bioreactor.ino — keep them equal.
*/

#define USE_DS18B20 1
#define USE_DHT 1

const uint8_t PIN_RELAY_HEAT = 7, PIN_RELAY_COOL = 8, PIN_RELAY_PUMP = 9;
const bool RELAY_ACTIVE_LOW = true;
const uint8_t PIN_TEMP_ONEWIRE = 2;
const uint8_t PIN_DHT = 3;
const uint8_t PIN_MQ_IN = A0;
const uint8_t PIN_MQ_OUT = A1;
const uint8_t PIN_PRESSURE = A2;
const float PRESSURE_OFFSET = 0.04;
const float PRESSURE_SLOPE = 0.09;

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

void setup() {
  const uint8_t relays[3] = {PIN_RELAY_HEAT, PIN_RELAY_COOL, PIN_RELAY_PUMP};
  for (uint8_t i = 0; i < 3; i++) {            // relays OFF and stay OFF in this sketch
    digitalWrite(relays[i], RELAY_ACTIVE_LOW ? HIGH : LOW);
    pinMode(relays[i], OUTPUT);
  }
  Serial.begin(115200);
#if USE_DS18B20
  tempSensor.begin();
  Serial.print(F("DS18B20 found: "));
  Serial.println(tempSensor.getDeviceCount());
#endif
#if USE_DHT
  dht.begin();
#endif
  Serial.println(F("time_s | temp_C | DHT_temp_C | rh_% | MQ_in_raw | MQ_out_raw | p_raw | p_volt | p_kPa"));
}

void loop() {
  float temp = NAN;
#if USE_DS18B20
  tempSensor.requestTemperatures();
  temp = tempSensor.getTempCByIndex(0);
#endif
  float dhtTemp = NAN, rh = NAN;
#if USE_DHT
  dhtTemp = dht.readTemperature();
  rh = dht.readHumidity();
#endif
  int mqIn = analogRead(PIN_MQ_IN);
  int mqOut = analogRead(PIN_MQ_OUT);
  int pRaw = analogRead(PIN_PRESSURE);
  float pVolt = pRaw * 5.0 / 1023.0;
  float pKpa = (pRaw / 1023.0 - PRESSURE_OFFSET) / PRESSURE_SLOPE;

  Serial.print(millis() / 1000.0, 1); Serial.print(F(" | "));
  Serial.print(temp, 2); Serial.print(F(" | "));
  Serial.print(dhtTemp, 1); Serial.print(F(" | "));
  Serial.print(rh, 1); Serial.print(F(" | "));
  Serial.print(mqIn); Serial.print(F(" | "));
  Serial.print(mqOut); Serial.print(F(" | "));
  Serial.print(pRaw); Serial.print(F(" | "));
  Serial.print(pVolt, 3); Serial.print(F(" | "));
  Serial.println(pKpa, 3);
  delay(500);
}
