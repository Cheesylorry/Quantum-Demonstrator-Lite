"""
Coordinates are kept as separate (row, col) pairs everywhere:
  row = qubit index 0..2   (row 0 = Qubit 1, top line of the grid)
  col = time step  0..6    (left to right)

The firmware's reader position 0..20 maps as:
  row = pos // 7,  col = pos % 7
(line 1 of the grid = CS0..CS6 = Qubit 1, etc.)
"""

import threading

NUM_ROWS = 3   # qubits
NUM_COLS = 7   # time steps


def pos_to_rc(pos: int) -> tuple[int, int] | None:
    if 0 <= pos < NUM_ROWS * NUM_COLS:
        return pos // NUM_COLS, pos % NUM_COLS
    return None


class BoardState:
    """Mapping of (row, col) -> uid with a change counter.

    Written by the serial thread (hardware board) or the GUI (manual board);
    read by the GUI poll loop. All access goes through the lock.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._cells: dict[tuple[int, int], str] = {}
        self._version = 0

    def place(self, row: int, col: int, uid: str) -> None:
        with self._lock:
            if self._cells.get((row, col)) != uid:
                self._cells[(row, col)] = uid
                self._version += 1

    def place_pos(self, pos: int, uid: str) -> None:
        rc = pos_to_rc(pos)
        if rc:
            self.place(rc[0], rc[1], uid)

    def remove(self, row: int, col: int) -> None:
        with self._lock:
            if (row, col) in self._cells:
                del self._cells[(row, col)]
                self._version += 1

    def remove_pos(self, pos: int) -> None:
        rc = pos_to_rc(pos)
        if rc:
            self.remove(rc[0], rc[1])

    def clear(self) -> None:
        with self._lock:
            if self._cells:
                self._cells = {}
            self._version += 1

    def snapshot(self) -> tuple[dict[tuple[int, int], str], int]:
        with self._lock:
            return dict(self._cells), self._version

    @property
    def version(self) -> int:
        with self._lock:
            return self._version
