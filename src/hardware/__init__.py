"""Laptop side of the reactor hardware (docs/hardware_protocol.md, docs/raspberry_setup.md).

    sensors + relays -> Arduino (main protection) -> USB -> Raspberry Pi (raspberry/bioreactor_pi, second protection)
    -> network -> this server -> «Реактор» page and the AI agent (read-only)

    config.py   data/config/reactor_hardware.json: mode simulator|pi, the Pi's address
    client.py   polls the Pi (GET /state every second), forwards a person's commands; in «simulator» mode it starts
                the same Pi bridge code with a virtual Arduino inside this server
    api.py      /api/reactor/* routes for the page
    live.py     read-only copy of the status for the AI agent (it never switches relays)

Rule: automatic protection only switches relays OFF. Switching ON is done only by a person (button + confirmation).
"""
