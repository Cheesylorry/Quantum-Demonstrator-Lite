"""Serial link to the Pico 2 board firmware.

Protocol (newline-terminated ASCII, device -> host):
    PLACE,<pos>,<uid_hex>
    REMOVE,<pos>
Host -> device:
    R        request full resync (device replays PLACE for every occupied pad)

The link runs in a background thread, keeps retrying on connection loss,
and pushes human-readable status messages into a queue the GUI drains.
On every (re)connect the hardware board state is cleared and a resync is
requested, so stale positions can never survive a reconnect.
"""

import queue
import threading
import time

import serial
from serial.tools import list_ports

from board import BoardState

RETRY_INTERVAL_S = 2.0


def available_ports() -> list[str]:
    return [p.device for p in list_ports.comports()]


class SerialLink(threading.Thread):
    def __init__(self, port: str, baud: int, board: BoardState,
                 status_queue: queue.Queue):
        super().__init__(daemon=True, name="serial-link")
        self.port = port
        self.baud = baud
        self.board = board
        self.status = status_queue
        self._stop = threading.Event()
        self.connected = False

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------------------------ run
    def run(self) -> None:
        while not self._stop.is_set():
            try:
                with serial.Serial(self.port, self.baud, timeout=0.2) as ser:
                    self.connected = True
                    self._report(f"connected to {self.port}")
                    self.board.clear()
                    ser.reset_input_buffer()
                    ser.write(b"R\n")           # full-state resync
                    self._read_loop(ser)
            except (serial.SerialException, OSError) as exc:
                self._report(f"serial error: {exc}")
            finally:
                if self.connected:
                    self.connected = False
                    self._report(f"disconnected from {self.port}")
            if self._stop.is_set():
                break
            self._report(f"retrying {self.port} in {RETRY_INTERVAL_S:.0f} s")
            self._stop.wait(RETRY_INTERVAL_S)

    def _read_loop(self, ser: serial.Serial) -> None:
        buf = b""
        while not self._stop.is_set():
            chunk = ser.readline()          # returns b"" on timeout
            if not chunk:
                continue
            buf += chunk
            if not buf.endswith(b"\n"):
                continue                    # partial line, keep buffering
            line = buf.decode("ascii", errors="replace").strip()
            buf = b""
            if line:
                self._handle_line(line)

    # ---------------------------------------------------------------- parse
    def _handle_line(self, line: str) -> None:
        parts = [p.strip() for p in line.split(",")]
        cmd = parts[0].upper()
        try:
            if cmd == "PLACE" and len(parts) >= 3:
                self.board.place_pos(int(parts[1]), parts[2].upper())
            elif cmd == "REMOVE" and len(parts) >= 2:
                self.board.remove_pos(int(parts[1]))
            else:
                self._report(f"device: {line}")   # boot msgs etc., informative
        except ValueError:
            self._report(f"unparsable line: {line!r}")

    def _report(self, msg: str) -> None:
        try:
            self.status.put_nowait(msg)
        except queue.Full:
            pass
