"""The Pi's wall clock. A Raspberry Pi has no battery clock: after a power-on without internet it starts from the time
of its last shutdown (systemd keeps it in /var/lib/systemd/timesync/clock), so journal and chart times can be hours
or days off. The laptop's dashboard compares the times when it connects and, if they differ by more than
TIME_SYNC_MIN_OFFSET_S, sends its own time (POST /time); Bridge.set_time() applies it through one of these clocks.

    SystemClock    the real clock of the Pi: time.clock_settime(CLOCK_REALTIME). Needs CAP_SYS_TIME — the systemd unit
                   gives the service user exactly that one capability (AmbientCapabilities=CAP_SYS_TIME), nothing else.
    VirtualClock   a clock with an offset, for the laptop's in-process simulator and the tests: it never touches the
                   computer's own clock. VirtualClock(offset_s=-3600) is a Pi that is one hour behind.

Safety does NOT depend on the wall clock: watchdogs and relay timers use time.monotonic (Bridge.clock), so setting
the time can never trip the «laptop silent» watchdog or switch a relay.
"""
from __future__ import annotations

import sys
import time

TIME_SYNC_MIN_OFFSET_S = 5.0
# A laptop time outside this range is a broken laptop clock, not a reason to move the Pi's clock.
EPOCH_MIN = 1704067200.0   # 2024-01-01 UTC
EPOCH_MAX = 4102444800.0   # 2100-01-01 UTC


class SystemClock:
    kind = "system"

    def now(self) -> float:
        return time.time()

    def set(self, epoch: float) -> None:
        if not hasattr(time, "clock_settime"):
            raise NotImplementedError("this system cannot set the clock from Python")
        time.clock_settime(time.CLOCK_REALTIME, epoch)  # PermissionError without CAP_SYS_TIME


class VirtualClock:
    kind = "virtual"

    def __init__(self, offset_s: float = 0.0, base=time.time):
        self.offset_s = float(offset_s)
        self._base = base

    def now(self) -> float:
        return self._base() + self.offset_s

    def set(self, epoch: float) -> None:
        self.offset_s = float(epoch) - self._base()


def default_clock(simulated_host: bool) -> SystemClock | VirtualClock:
    """The real clock only on Linux (the Pi); on any other computer (a developer's Windows laptop) a virtual one."""
    if simulated_host or not sys.platform.startswith("linux"):
        return VirtualClock()
    return SystemClock()
