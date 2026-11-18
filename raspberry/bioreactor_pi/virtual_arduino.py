"""Virtual Arduino: the same rules as firmware/bioreactor/bioreactor.ino + realistic readings. No hardware needed.

Used (1) by the Pi bridge in --simulate mode, (2) by the laptop's «СИМУЛЯТОР» (an in-process Pi with this Arduino),
(3) by tests of the Pi code through VirtualSerial (a fake USB port that can be «unplugged»).

Physics (simple, but every effect goes the right way):
    temperature  heater raises it slowly, cooler lowers it, the barrel loses heat to the air
    pressure     gas is produced all the time (most near 37 °C) -> grows; the pump lowers it
    gas inside   MQ raw index grows with the accumulated gas (an indicator, NOT % methane)
    gas outside  low background; «simulate a leak» raises it above the leak threshold
    humidity     high, slowly changing

Arduino protections (exactly as in the sketch):
    boot        all relays OFF
    leak        gas outside >= leak -> heater OFF, locked until {"cmd":"reset"} (refused while still leaking)
    overheat    temp >= overheat_c -> heater OFF, refused until below overheat_release_c
    temp sensor no temperature (sensor broken) -> heater OFF and refused (fail-safe)
    warm-up     MQ sensors need to heat up after power-on: heater refused for mq_warmup_s
    interlock   heater and cooler never ON together (the second command is refused)
    watchdog    no command/ping for arduino_watchdog_s -> ALL relays OFF
    pump stop   pressure <= pump_stop -> pump OFF (no vacuum in the barrel)
"""
from __future__ import annotations

import json
import math
import random
import time
from collections.abc import Callable

from . import protocol

FIRMWARE = "virtual-0.1"


class VirtualArduino:
    def __init__(self, config: dict, seed: int = 7):
        self.sim = dict(config["simulator"])
        th = config["thresholds"]
        self.overheat_c = th["overheat_c"]
        self.overheat_release_c = th["overheat_release_c"]
        self.leak_raw = th["gas_out_raw"]["leak"]
        self.pump_stop = th["pressure_kpa"]["pump_stop"]
        self.watchdog_s = config["arduino_watchdog_s"]
        self.random = random.Random(seed)
        self.temp_c = self.sim["start_temp_c"]
        self.p_kpa = self.sim["start_pressure_kpa"]
        self.gas_out = 80.0
        self.leak_on = False            # «simulate a leak»
        self.temp_sensor_broken = False  # «simulate a broken temperature sensor»
        self.boot()

    def boot(self) -> None:
        """Power-on / reset (a real Arduino also resets when the USB port is opened)."""
        self.uptime_s = 0.0
        self.seq = 0
        self.silence_s = 0.0
        self.relay = {name: False for name in protocol.RELAYS}
        self.alarm = {name: False for name in protocol.ALARMS}
        self.alarm["warmup"] = self.sim.get("mq_warmup_s", 0) > 0
        self.outbox: list[bytes] = [protocol.encode({"type": "boot", "fw": FIRMWARE, "proto": protocol.PROTOCOL_VERSION})]

    # -- physics ------------------------------------------------------------------
    def gas_factor(self) -> float:
        return max(0.05, 1 - ((self.temp_c - 37.0) / 15.0) ** 2)

    def step(self, dt: float = 1.0) -> None:
        sim = self.sim
        heat = sim["heater_c_per_s"] if self.relay["heat"] else 0.0
        cool = sim["cooler_c_per_s"] if self.relay["cool"] else 0.0
        self.temp_c += (heat - cool - sim["loss_per_s"] * (self.temp_c - sim["ambient_c"])) * dt
        self.p_kpa += sim["gas_kpa_per_s_at_37"] * self.gas_factor() * dt
        if self.relay["pump"]:
            self.p_kpa -= sim["pump_kpa_per_s"] * dt
        self.p_kpa = max(0.0, self.p_kpa)
        target = 620.0 if self.leak_on else 80.0
        self.gas_out += (target - self.gas_out) * min(1.0, 0.35 * dt)
        self.uptime_s += dt
        self.silence_s += dt
        self.protect()
        self.outbox.append(self.state_line())

    def _event(self, code: str) -> None:
        self.outbox.append(protocol.encode({"type": "event", "code": code}))

    def _heat_off(self, code: str) -> None:
        if self.relay["heat"]:
            self.relay["heat"] = False
            self._event(code)

    def protect(self) -> None:
        if self.alarm["warmup"] and self.uptime_s >= self.sim.get("mq_warmup_s", 0):
            self.alarm["warmup"] = False
        if not self.alarm["warmup"] and self.gas_out >= self.leak_raw and not self.alarm["leak"]:
            self.alarm["leak"] = True
            self._event("leak")
        if self.alarm["leak"]:
            self._heat_off("leak_heat_off")
        self.alarm["temp_sensor"] = self.temp_sensor_broken
        if self.temp_sensor_broken:
            self._heat_off("temp_sensor_heat_off")
        elif self.temp_c >= self.overheat_c:
            self.alarm["overheat"] = True
        elif self.temp_c < self.overheat_release_c:
            self.alarm["overheat"] = False
        if self.alarm["overheat"]:
            self._heat_off("overheat_heat_off")
        if self.silence_s >= self.watchdog_s and not self.alarm["watchdog"]:
            self.alarm["watchdog"] = True
            if any(self.relay.values()):
                self.relay = {name: False for name in self.relay}
                self._event("watchdog_all_off")
        if self.relay["pump"] and self.p_kpa <= self.pump_stop:
            self.relay["pump"] = False
            self._event("pump_empty_off")

    # -- readings ------------------------------------------------------------------
    def readings(self) -> dict:
        noise = self.random.uniform
        return {
            "temp_c": None if self.temp_sensor_broken else round(self.temp_c + noise(-0.05, 0.05), 2),
            "rh_pct": round(min(100.0, 86 + 2 * math.sin(self.uptime_s / 90) + 0.1 * (self.temp_c - 30) + noise(-0.3, 0.3)), 1),
            "gas_in": round(260 + 110 * min(self.p_kpa, 3.5) + 40 * self.gas_factor() + noise(-6, 6)),
            "gas_out": round(self.gas_out + noise(-4, 4)),
            "p_kpa": round(max(0.0, self.p_kpa + noise(-0.01, 0.01)), 3),
        }

    def state_line(self) -> bytes:
        self.seq += 1
        return protocol.encode({"type": "state", "seq": self.seq, "uptime_ms": int(self.uptime_s * 1000),
                                **self.readings(), "relays": {k: int(v) for k, v in self.relay.items()},
                                "alarms": {k: int(v) for k, v in self.alarm.items()}})

    # -- commands --------------------------------------------------------------------
    def _ack(self, identifier: int, ok: bool, reason: str | None = None) -> None:
        message = {"type": "ack", "id": identifier, "ok": int(ok), "relays": {k: int(v) for k, v in self.relay.items()}}
        if reason:
            message["reason"] = reason
        self.outbox.append(protocol.encode(message))

    def handle(self, line: bytes) -> None:
        try:
            message = json.loads(line.decode("utf-8"))
            cmd, identifier = message["cmd"], message.get("id", 0)
        except (ValueError, KeyError, TypeError, AttributeError):
            return
        if not isinstance(identifier, int):
            identifier = 0
        self.silence_s = 0.0
        self.alarm["watchdog"] = False
        if cmd == "ping":
            self._ack(identifier, True)
        elif cmd == "all_off":
            self.relay = {name: False for name in self.relay}
            self._ack(identifier, True)
        elif cmd == "reset":
            if self.gas_out >= self.leak_raw:
                self._ack(identifier, False, "still_leaking")
            else:
                self.alarm["leak"] = False
                self._ack(identifier, True)
        elif cmd == "relay":
            name, on = message.get("name"), message.get("state") in (1, True)
            if name not in self.relay:
                self._ack(identifier, False, "unknown_relay")
                return
            reason = None
            if on and name == "heat":
                reason = ("leak_lock" if self.alarm["leak"] else "temp_sensor" if self.alarm["temp_sensor"]
                          else "overheat" if self.alarm["overheat"] else "warmup" if self.alarm["warmup"] else None)
            if on and reason is None and ((name == "heat" and self.relay["cool"]) or (name == "cool" and self.relay["heat"])):
                reason = "interlock"
            if reason:
                self._ack(identifier, False, reason)
            else:
                self.relay[name] = on
                self._ack(identifier, True)
        else:
            self._ack(identifier, False, "bad_cmd")

    def take_output(self) -> list[bytes]:
        out, self.outbox = self.outbox, []
        return out


class VirtualSerial:
    """A fake USB port with a VirtualArduino behind it: same methods as serial_link.SerialLink.

    unplugged = True   -> the port disappears (open/readline/write raise LinkError), like a pulled USB cable
    silent = True      -> the port exists but the Arduino sends nothing and hears nothing (frozen board)
    Opening the port resets the Arduino (as the DTR line does on a real one): all relays OFF.
    """

    def __init__(self, config: dict, clock: Callable[[], float] = time.monotonic, seed: int = 7, tick_s: float = 1.0):
        self.arduino = VirtualArduino(config, seed=seed)
        self.clock = clock
        self.tick_s = tick_s
        self.port = "virtual"
        self.unplugged = False
        self.silent = False
        self.is_open = False
        self._last = clock()
        self._queue: list[bytes] = []

    def open(self) -> None:
        from .serial_link import LinkError
        if self.unplugged:
            raise LinkError("virtual port unplugged")
        self.arduino.boot()
        self._queue = []
        self._last = self.clock()
        self.is_open = True

    def close(self) -> None:
        self.is_open = False

    def _advance(self) -> None:
        now = self.clock()
        while now - self._last >= self.tick_s:
            self.arduino.step(self.tick_s)
            self._last += self.tick_s
        output = self.arduino.take_output()
        if not self.silent:
            self._queue += output

    def readline(self, wait_s: float = 0.2) -> bytes | None:
        from .serial_link import LinkError
        if self.unplugged or not self.is_open:
            self.is_open = False
            raise LinkError("virtual port unplugged")
        if not self._queue:
            self._advance()
        if self._queue:
            return self._queue.pop(0)
        if wait_s:
            time.sleep(min(wait_s, 0.05))
        return None

    def write(self, data: bytes) -> None:
        from .serial_link import LinkError
        if self.unplugged or not self.is_open:
            self.is_open = False
            raise LinkError("virtual port unplugged")
        self._advance()
        if not self.silent:
            self.arduino.handle(data)
            self._queue += self.arduino.take_output()
