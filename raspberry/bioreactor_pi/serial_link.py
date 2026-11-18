"""USB Serial link to the Arduino (pyserial): port auto-detection, clear errors, reopen after a pulled cable.

    open()        finds the port ("auto": /dev/ttyACM*, /dev/ttyUSB*, or a USB COM port on Windows) and opens it
    readline()    one line or None after a short wait; raises LinkError when the port disappears
    write(data)
    close()
The bridge calls open() again every 3 s while the link is down (reconnect).
"""
from __future__ import annotations

import glob
import sys

# USB-serial chips of Arduino-like boards: Arduino, CH340, CP210x, FTDI.
KNOWN_USB_VIDS = {0x2341, 0x2A03, 0x1A86, 0x10C4, 0x0403}


class LinkError(OSError):
    """The Arduino cannot be reached (no port, cable pulled out, port busy)."""


def find_port(ports=None, linux_globs=None) -> str | None:
    """Linux (the Pi): first /dev/ttyACM* then /dev/ttyUSB*. Elsewhere: the first known USB-serial chip."""
    if linux_globs is None and sys.platform.startswith("linux"):
        linux_globs = sorted(glob.glob("/dev/ttyACM*")) + sorted(glob.glob("/dev/ttyUSB*"))
    if linux_globs:
        return linux_globs[0]
    if ports is None:
        try:
            from serial.tools import list_ports
        except ImportError:
            return None
        ports = list_ports.comports()
    usb = [p for p in ports if getattr(p, "vid", None) is not None]
    for p in usb:
        if p.vid in KNOWN_USB_VIDS:
            return p.device
    return usb[0].device if usb else None


class SerialLink:
    def __init__(self, port: str = "auto", baud: int = 115200):
        self.setting = port
        self.baud = baud
        self.port: str | None = None if port == "auto" else port
        self._serial = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None

    def open(self) -> None:
        try:
            import serial
        except ImportError as error:
            raise LinkError("pyserial is not installed (pip install pyserial)") from error
        port = find_port() if self.setting == "auto" else self.setting
        if not port:
            raise LinkError("no Arduino found (/dev/ttyACM*, /dev/ttyUSB*)")
        self.port = port
        try:
            self._serial = serial.serial_for_url(port, baudrate=self.baud, timeout=0.2, write_timeout=1)
        except (serial.SerialException, ValueError, OSError) as error:
            raise LinkError(str(error)) from error

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    def readline(self, wait_s: float = 0.2) -> bytes | None:
        import serial
        if self._serial is None:
            raise LinkError("port closed")
        try:
            return self._serial.readline() or None
        except (serial.SerialException, OSError) as error:
            self.close()
            raise LinkError(str(error)) from error

    def write(self, data: bytes) -> None:
        import serial
        if self._serial is None:
            raise LinkError("port closed")
        try:
            self._serial.write(data)
        except (serial.SerialException, OSError) as error:
            self.close()
            raise LinkError(str(error)) from error
