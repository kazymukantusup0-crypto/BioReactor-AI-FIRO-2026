"""Virtual Arduino: a line-by-line port of firmware/bioreactor/bioreactor.ino (bioreactor-1.0) + simple physics.

Used (1) by the Pi bridge in --simulate mode, (2) by the laptop's «СИМУЛЯТОР» (an in-process Pi with this Arduino),
(3) by tests of the Pi code through VirtualSerial (a fake USB port that can be «unplugged»).

Same as the sketch (function names kept, so the two can be compared side by side):
    loop() every 1 s     readSensors -> evaluateAlarms -> autoControl -> enforceSafety -> sendStatus
    evaluateAlarms       warm-up 60 s; leak (gas outside > limit 2 times in a row) -> latched, AUTO off;
                         overheat with 2 °C hysteresis; no Pi command for 10 s -> relays switched on FROM THE PI off
                         (link_lost); auger longer than 10 min -> off (auger_timeout, in ONE status only)
    autoControl          AUTO: heater below temp_min, cooler above temp_max (0.5 °C hysteresis), pump when gas inside
                         > gas_in_limit (30 hysteresis), nothing during warm-up
    enforceSafety        E-STOP/leak -> all off; heater locked by E-STOP/leak/warm-up/no sensor/overheat; pump off
                         during warm-up; heater+cooler -> heater off
    requestRelay         the same refusal codes; a manual heat/cool/pump command switches AUTO off
    commands             PING GET RELAY AUTO SET ESTOP RESET ALLOFF; errors BAD_ARGS UNKNOWN BAD_KEY OUT_OF_RANGE ...
Not simulated: the screen, the encoder and the local buttons (E-STOP by holding BACK is the same as the ESTOP command).

Physics (every effect goes the right way): the heater warms the barrel, the cooler cools it, it loses heat to the air;
gas inside (MQ raw) grows while gas forms, most near 37 °C, the pump lowers it; gas outside is a low background,
«simulate a leak» raises it above the limit. Values are raw MQ-9 0-1023, not ppm.
"""
from __future__ import annotations

import json
import math
import random
import time
from collections.abc import Callable

from . import protocol

FIRMWARE = "bioreactor-1.0-virtual"
TEMP_HYST = 0.5
OVERHEAT_HYST = 2.0
GAS_IN_HYST = 30
LEAK_CONFIRM = 2
DEFAULT_LIMITS = {"temp_min": 35.0, "temp_max": 38.0, "temp_hard_max": 45.0, "gas_out_limit": 400, "gas_in_limit": 700}


class VirtualArduino:
    def __init__(self, config: dict, seed: int = 7):
        self.sim = dict(config["simulator"])
        self.random = random.Random(seed)
        self.temp_c = self.sim["start_temp_c"]
        self.gas_in = float(self.sim["start_gas_in"])
        self.gas_out = float(self.sim["gas_out_clean"])
        self.cfg = dict(DEFAULT_LIMITS)          # «EEPROM»: survives a reset, like on the real board
        self.leak_on = False                      # «simulate a leak»
        self.temp_sensor_broken = False           # «simulate a broken temperature sensor»
        self.boot()

    # -- setup() ----------------------------------------------------------------------
    def boot(self) -> None:
        """Power-on / reset (a real Mega also resets when the USB port is opened): relays OFF, AUTO on."""
        self.uptime_s = 0.0
        self.relay = {name: False for name in protocol.RELAYS}
        self.remote = {name: False for name in protocol.RELAYS}
        self.auto = True
        self.estop = False
        self.leak = False
        self.overheat = False
        self.warmup = True
        self.link_lost = False
        self.leak_count = 0
        self.last_link_s = 0.0
        self.auger_on_since = 0.0
        self.auger_timed_out = False
        self.outbox: list[bytes] = [self._json({"type": "boot", "fw": FIRMWARE})]
        self._read_sensors()

    @staticmethod
    def _json(message: dict) -> bytes:
        return (json.dumps(message, separators=(",", ":")) + "\n").encode("ascii")

    # -- physics + readSensors() --------------------------------------------------------------
    def gas_factor(self) -> float:
        return max(0.05, 1 - ((self.temp_c - 37.0) / 15.0) ** 2)

    def _physics(self, dt: float) -> None:
        sim = self.sim
        heat = sim["heater_c_per_s"] if self.relay["heat"] else 0.0
        cool = sim["cooler_c_per_s"] if self.relay["cool"] else 0.0
        self.temp_c += (heat - cool - sim["loss_per_s"] * (self.temp_c - sim["ambient_c"])) * dt
        self.gas_in += sim["gas_in_per_s_at_37"] * self.gas_factor() * dt
        if self.relay["pump"]:
            self.gas_in -= sim["pump_gas_in_per_s"] * dt
        self.gas_in = min(1023.0, max(float(sim["gas_in_floor"]), self.gas_in))
        target = sim["gas_out_leak"] if self.leak_on else sim["gas_out_clean"]
        self.gas_out += (target - self.gas_out) * min(1.0, 0.35 * dt)

    def _read_sensors(self) -> None:
        noise = self.random.uniform
        self.mq_in = int(min(1023, max(0, round(self.gas_in + noise(-4, 4)))))
        self.mq_out = int(min(1023, max(0, round(self.gas_out + noise(-4, 4)))))
        self.humidity = round(min(99.0, 84 + 2 * math.sin(self.uptime_s / 90) + noise(-0.5, 0.5)), 1)
        self.ds_valid = not self.temp_sensor_broken
        self.temp_ds = round(self.temp_c + noise(-0.05, 0.05), 1)

    # -- loop() every SENSOR_INTERVAL_MS ---------------------------------------------------------
    def step(self, dt: float = 1.0) -> None:
        self._physics(dt)
        self.uptime_s += dt
        self._read_sensors()
        self._evaluate_alarms()
        self._auto_control()
        self._enforce_safety()
        self.outbox.append(self.status_line())
        self.auger_timed_out = False

    def heat_locked(self) -> bool:
        return self.estop or self.leak or self.warmup or not self.ds_valid or self.overheat

    def _evaluate_alarms(self) -> None:
        self.warmup = self.uptime_s < self.sim["mq_warmup_s"]
        if not self.warmup:
            if self.mq_out > self.cfg["gas_out_limit"]:
                self.leak_count = min(255, self.leak_count + 1)
                if self.leak_count >= LEAK_CONFIRM and not self.leak:
                    self.leak = True
                    self.auto = False
            else:
                self.leak_count = 0
        if self.ds_valid:
            if self.temp_ds >= self.cfg["temp_hard_max"]:
                self.overheat = True
            elif self.temp_ds <= self.cfg["temp_hard_max"] - OVERHEAT_HYST:
                self.overheat = False
        else:
            self.overheat = False
        if any(self.remote.values()) and self.uptime_s - self.last_link_s > self.sim["link_timeout_s"]:
            for name in protocol.RELAYS:
                if self.remote[name]:
                    self.relay[name] = False
                    self.remote[name] = False
            self.link_lost = True
        if self.relay["auger"] and self.uptime_s - self.auger_on_since > self.sim["auger_max_run_s"]:
            self.relay["auger"] = False
            self.remote["auger"] = False
            self.auger_timed_out = True

    def _auto_control(self) -> None:
        if not self.auto:
            return
        if self.ds_valid:
            if self.temp_ds < self.cfg["temp_min"]:
                self.relay["heat"] = True
            elif self.temp_ds >= self.cfg["temp_min"] + TEMP_HYST:
                self.relay["heat"] = False
            if self.temp_ds > self.cfg["temp_max"]:
                self.relay["cool"] = True
            elif self.temp_ds <= self.cfg["temp_max"] - TEMP_HYST:
                self.relay["cool"] = False
        else:
            self.relay["heat"] = self.relay["cool"] = False
        if self.warmup:
            self.relay["pump"] = False
        elif self.mq_in > self.cfg["gas_in_limit"]:
            self.relay["pump"] = True
        elif self.mq_in < self.cfg["gas_in_limit"] - GAS_IN_HYST:
            self.relay["pump"] = False

    def _enforce_safety(self) -> None:
        if self.estop or self.leak:
            self.relay = {name: False for name in protocol.RELAYS}
        if self.heat_locked():
            self.relay["heat"] = False
        if self.warmup:
            self.relay["pump"] = False
        if self.relay["heat"] and self.relay["cool"]:
            self.relay["heat"] = False
        for name in protocol.RELAYS:
            if not self.relay[name]:
                self.remote[name] = False

    def _request_relay(self, name: str, on: bool, remote: bool) -> str | None:
        if on:
            if self.estop:
                return "ESTOP"
            if self.leak:
                return "LEAK"
            if name == "heat":
                if self.warmup:
                    return "WARMUP"
                if not self.ds_valid:
                    return "NO_TEMP"
                if self.overheat:
                    return "OVERHEAT"
                if self.relay["cool"]:
                    return "INTERLOCK"
            if name == "cool" and self.relay["heat"]:
                return "INTERLOCK"
            if name == "pump" and self.warmup:
                return "WARMUP"
        if name != "auger":
            self.auto = False                     # manual control switches AUTO off
        if name == "auger" and on and not self.relay["auger"]:
            self.auger_on_since = self.uptime_s
        self.relay[name] = on
        self.remote[name] = on and remote
        self._enforce_safety()
        return None

    def _set_auto(self, on: bool) -> None:
        self.auto = on
        if on:
            for name in ("heat", "cool", "pump"):
                self.remote[name] = False
            self._auto_control()
        self._enforce_safety()

    def _all_off(self) -> None:
        self.relay = {name: False for name in protocol.RELAYS}
        self.remote = {name: False for name in protocol.RELAYS}
        self.auto = False

    def _reset_alarms(self) -> str | None:
        self.estop = False
        self.link_lost = False
        if self.leak:
            if not self.warmup and self.mq_out < self.cfg["gas_out_limit"]:
                self.leak = False
                self.leak_count = 0
            else:
                return "GAS_STILL_HIGH"
        return None

    def _set_limit(self, key: str, value: float) -> str | None:
        names = {v: k for k, v in protocol.LIMITS.items()}
        if key not in names:
            return "BAD_KEY"
        new = dict(self.cfg)
        new[names[key]] = int(value) if names[key] in protocol.GAS_LIMITS else float(value)
        if math.isnan(float(value)) or protocol.limits_error(new):
            return "OUT_OF_RANGE"
        self.cfg = new
        return None

    # -- sendStatus() / sendAck() -------------------------------------------------------------
    def status_line(self) -> bytes:
        return self._json({
            "type": "status", "fw": FIRMWARE, "uptime_s": int(self.uptime_s), "mq_in": self.mq_in, "mq_out": self.mq_out,
            "humidity": self.humidity, "temp": self.temp_ds if self.ds_valid else None,
            "relays": dict(self.relay), "remote": dict(self.remote), "auto": self.auto,
            "temp_min": round(float(self.cfg["temp_min"]), 1), "temp_max": round(float(self.cfg["temp_max"]), 1),
            "temp_hard_max": round(float(self.cfg["temp_hard_max"]), 1),
            "gas_out_limit": int(self.cfg["gas_out_limit"]), "gas_in_limit": int(self.cfg["gas_in_limit"]),
            "alarms": {"estop": self.estop, "leak": self.leak, "overheat": self.overheat, "warmup": self.warmup,
                       "no_temp": not self.ds_valid, "link_lost": self.link_lost, "auger_timeout": self.auger_timed_out}})

    def _ack(self, cmd: str, error: str | None) -> None:
        message = {"type": "ack", "cmd": cmd, "ok": error is None}
        if error:
            message["error"] = error
        self.outbox.append(self._json(message))

    # -- handleCommand() ---------------------------------------------------------------------
    def handle(self, line: bytes) -> None:
        words = line.decode("ascii", errors="replace").strip().upper().split()
        if not words:
            return
        cmd, args = words[0], words[1:]
        self.last_link_s = self.uptime_s
        self.link_lost = False
        error = None
        if cmd == "PING":
            pass
        elif cmd == "GET":
            self.outbox.append(self.status_line())
            return
        elif cmd == "RELAY":
            try:
                number, state = int(args[0]), int(args[1])
            except (IndexError, ValueError):
                number, state = 0, -1
            if not 1 <= number <= 4 or state not in (0, 1):
                error = "BAD_ARGS"
            else:
                error = self._request_relay(protocol.RELAYS[number - 1], state == 1, remote=True)
        elif cmd == "AUTO":
            if not args or args[0] not in ("0", "1"):
                error = "BAD_ARGS"
            elif args[0] == "1" and (self.estop or self.leak):
                error = "ESTOP" if self.estop else "LEAK"
            else:
                self._set_auto(args[0] == "1")
        elif cmd == "SET":
            if len(args) < 2:
                error = "BAD_ARGS"
            else:
                try:
                    value = float(args[1])
                except ValueError:
                    value = 0.0            # atof() of garbage is 0 on the Arduino too
                error = self._set_limit(args[0], value)
        elif cmd == "ESTOP":
            self.estop = True
            self._all_off()
        elif cmd == "RESET":
            error = self._reset_alarms()
        elif cmd == "ALLOFF":
            self._all_off()
        else:
            error = "UNKNOWN"
        self._ack(cmd, error)
        self._enforce_safety()

    def take_output(self) -> list[bytes]:
        out, self.outbox = self.outbox, []
        return out


class VirtualSerial:
    """A fake USB port with a VirtualArduino behind it: same methods as serial_link.SerialLink.

    unplugged = True   -> the port disappears (open/readline/write raise LinkError), like a pulled USB cable
    silent = True      -> the port exists but the Arduino sends nothing and hears nothing (frozen board)
    Opening the port resets the Arduino (as the DTR line does on a real Mega): boot line, relays OFF, AUTO on.
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
