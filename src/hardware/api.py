"""/api/reactor/* — the «Реактор» page. The laptop server forwards to the Raspberry Pi (or the simulated Pi).

    GET  /api/reactor/status              readings + levels, relays, alarms, source, links
    GET  /api/reactor/history?window=600  chart points (600 = 10 min, 3600 = 1 hour)
    GET  /api/reactor/journal?limit=50    commands and alarms (the Pi's SQLite journal)
    POST /api/reactor/check               «Проверить связь»: one request to the Pi, with its time
    POST /api/reactor/relay               {"relay":"heat"|"cool"|"pump"|"auger","on":true,"confirm":true} — a PERSON's button
    POST /api/reactor/auto                {"on":true,"confirm":true} — the Arduino's automatic regime
    POST /api/reactor/limit               {"name":"temp_min","value":35.5,"confirm":true} — one EEPROM threshold
    POST /api/reactor/estop               {} — EMERGENCY STOP, no confirmation
    POST /api/reactor/alarm/reset         {"confirm":true} — a person clears E-STOP / leak / link lost (leak only when the
                                          gas outside is below the limit)
    POST /api/reactor/simulator           {"what":"leak"|"usb"|"arduino_silent"|"temp_sensor"|"network","on":true}

Commands need "confirm": true (the page asks first). The AI agent has no route here (it reads src/hardware/live.py).
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


class RelayCommand(BaseModel):
    relay: Literal["heat", "cool", "pump", "auger"]
    on: bool
    confirm: bool = False


class AutoCommand(BaseModel):
    on: bool
    confirm: bool = False


class LimitCommand(BaseModel):
    name: Literal["temp_min", "temp_max", "temp_hard_max", "gas_out_limit", "gas_in_limit"]
    value: float
    confirm: bool = False


class Confirm(BaseModel):
    confirm: bool = False


class SimulatorCommand(BaseModel):
    what: Literal["leak", "usb", "arduino_silent", "temp_sensor", "network"]
    on: bool


def create_router(client) -> APIRouter:
    router = APIRouter(prefix="/api/reactor", tags=["Reactor hardware"])

    @router.get("/status")
    def status() -> dict:
        return client.status()

    @router.get("/history")
    def history(window: int = 600) -> dict:
        if window not in (600, 3600):
            raise HTTPException(422, "window must be 600 or 3600")
        return client.history(window)

    @router.get("/journal")
    def journal(limit: int = 50) -> dict:
        return client.journal(max(1, min(limit, 500)))

    @router.post("/check")
    def check() -> dict:
        return client.check_connection()

    @router.post("/relay")
    def relay(body: RelayCommand) -> dict:
        if not body.confirm:
            raise HTTPException(428, "confirmation required")
        return client.command(body.relay, body.on, who="operator")

    @router.post("/auto")
    def auto(body: AutoCommand) -> dict:
        if not body.confirm:
            raise HTTPException(428, "confirmation required")
        return client.set_auto(body.on, who="operator")

    @router.post("/limit")
    def limit(body: LimitCommand) -> dict:
        if not body.confirm:
            raise HTTPException(428, "confirmation required")
        return client.set_limit(body.name, body.value, who="operator")

    @router.post("/estop")
    def estop() -> dict:
        return client.estop(who="operator")

    @router.post("/alarm/reset")
    def reset(body: Confirm) -> dict:
        if not body.confirm:
            raise HTTPException(428, "confirmation required")
        return client.reset_alarms(who="operator")

    @router.post("/simulator")
    def simulator(body: SimulatorCommand) -> dict:
        result = client.simulate(body.what, body.on, who="operator")
        if result.get("reason") == "not_simulator":
            raise HTTPException(409, "a real Raspberry Pi is configured; simulator buttons are off")
        return result

    return router


def build_client(config: dict | None = None, journal_path=None):
    from src.hardware.client import ReactorClient
    from src.hardware.config import load_config
    return ReactorClient(config or load_config(), journal_path=journal_path)
