"""Tag enrollment wizard -- populate gates.csv using the hardware itself.

    python enroll.py --port /dev/ttyACM0      # or COM5
    python enroll.py --manual                 # no hardware: type UIDs by hand

You choose what kind of gate you want to enroll, the wizard asks for its
properties, and then tells you to place the physical tag on any pad of
COLUMN 1 (time step 1 -- readers 0, 7, 14; rows = Qubit 1..3). The UID
that appears there is captured and written to the CSV. Tags placed on any
other column, and tags already captured in the same figure, are ignored.

For multi-part figures the wizard walks through the roles one by one
("place the CONTROL tag", "place the TARGET tag", ...), so each physical
end of the figure is unambiguously bound to its role.

Re-enrolling a known UID offers to overwrite its existing row. Ctrl+C at
any prompt aborts the current item and returns to the menu.
"""

import argparse
import queue
import sys
import time

from board import BoardState
from database import GateDatabase, TagEntry, normalize_uid
from families import FAMILIES
from serial_link import SerialLink, available_ports

ENROLL_COL = 0      # column 1 on the physical board
POLL_S = 0.05


class Abort(Exception):
    """User aborted the current enrollment item (Ctrl+C)."""


# ------------------------------------------------------------- input helpers
def ask(prompt: str, default: str | None = None,
        required: bool = True) -> str:
    suffix = f" [{default}]" if default is not None else ""
    while True:
        try:
            val = input(f"  {prompt}{suffix}: ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            raise Abort()
        if not val and default is not None:
            return default
        if val or not required:
            return val
        print("    (required)")


def ask_yesno(prompt: str, default: bool = False) -> bool:
    val = ask(prompt + (" (y/N)" if not default else " (Y/n)"),
              default="n" if not default else "y")
    return val.strip().lower() in ("y", "yes")


def ask_choice(prompt: str, choices: list[str]) -> str:
    for i, c in enumerate(choices, 1):
        print(f"    [{i}] {c}")
    while True:
        val = ask(prompt)
        if val in choices:
            return val
        try:
            idx = int(val)
            if 1 <= idx <= len(choices):
                return choices[idx - 1]
        except ValueError:
            pass
        print("    pick a number from the list")


# --------------------------------------------------------------- tag capture
class TagSource:
    """Yields UIDs either from column 1 of the hardware or typed by hand."""

    def __init__(self, board: BoardState | None,
                 status_q: queue.Queue | None, manual: bool):
        self.board = board
        self.status_q = status_q
        self.manual = manual
        self._prev: dict[int, str] = {}

    def _drain_status(self) -> None:
        if not self.status_q:
            return
        while True:
            try:
                print(f"    [serial] {self.status_q.get_nowait()}")
            except queue.Empty:
                return

    def _col_cells(self) -> dict[int, str]:
        cells, _v = self.board.snapshot()
        return {row: uid for (row, col), uid in cells.items()
                if col == ENROLL_COL}

    def capture(self, what: str, exclude: set[str]) -> str:
        """Block until a tag not in `exclude` is (newly) placed on column 1.
        Returns its UID. In manual mode, prompts for it instead."""
        if self.manual:
            while True:
                uid = normalize_uid(ask(f"type the UID for {what}"))
                if not uid:
                    continue
                if uid in exclude:
                    print("    that UID was already captured for this "
                          "figure -- use a different tag")
                    continue
                return uid

        print(f"  >> Place the tag for {what} on any pad of COLUMN 1 "
              "(Ctrl+C to abort)")
        self._prev = self._col_cells()
        # A tag already sitting alone on column 1 counts immediately -- this
        # lets you place the tag first and answer the questions afterwards.
        if len(self._prev) == 1:
            uid = next(iter(self._prev.values()))
            if uid not in exclude:
                row = next(iter(self._prev))
                print(f"     captured {uid} (already on Qubit {row + 1})")
                return uid
        warned: set[str] = set()
        try:
            while True:
                self._drain_status()
                cells = self._col_cells()
                for row, uid in cells.items():
                    if self._prev.get(row) == uid:
                        continue                      # nothing new here
                    if uid in exclude:
                        if uid not in warned:
                            print("     that tag was already captured for "
                                  "this figure -- place a different one")
                            warned.add(uid)
                        continue
                    print(f"     captured {uid} on Qubit {row + 1}")
                    return uid
                self._prev = {r: u for r, u in cells.items()}
                time.sleep(POLL_S)
        except KeyboardInterrupt:
            print()
            raise Abort()


# enrollment
def resolve_conflict(db: GateDatabase, uid: str) -> bool:
    """Returns True if we may (over)write this UID, False to pick another."""
    existing = db.lookup(uid)
    if existing is None:
        return True
    print(f"     {uid} is already in the database as: "
          f"{existing.display_name} ({existing.type}"
          + (f", {existing.figure_id} {existing.role}"
             if existing.type == "multi_part" else "") + ")")
    return ask_yesno("overwrite this entry?")


def capture_unique(source: TagSource, db: GateDatabase, what: str,
                   exclude: set[str]) -> str:
    """Capture a UID, handling already-known tags via overwrite/skip."""
    while True:
        uid = source.capture(what, exclude)
        if resolve_conflict(db, uid):
            return uid
        exclude = exclude | {uid}
        print("     ok -- waiting for a different tag")


def enroll_single(db: GateDatabase, source: TagSource) -> None:
    print("\n-- Single-qubit gate --")
    name = ask("display name (e.g. Hadamard C)")
    gate = ask("gate string (e.g. H, X, phase(60))")
    sqrt = ask_yesno("sqrt flag?")
    inverse = ask_yesno("inverse flag?")
    uid = capture_unique(source, db, f"'{name}'", set())
    db.upsert_entry(TagEntry(uid=uid, display_name=name, type="single",
                             gate_string=gate, sqrt=sqrt, inverse=inverse))
    print(f"  saved: {uid} -> {name} [{gate}]"
          + (" sqrt" if sqrt else "") + (" inverse" if inverse else ""))


def enroll_measurement(db: GateDatabase, source: TagSource) -> None:
    print("\n-- Measurement --")
    basis = ask("basis", default="z").lower()
    name = ask("display name", default=f"Measure {basis.upper()}")
    uid = capture_unique(source, db, f"'{name}'", set())
    db.upsert_entry(TagEntry(uid=uid, display_name=name, type="measurement",
                             gate_string=basis))
    print(f"  saved: {uid} -> {name} [basis {basis}]")


def suggest_figure_id(db: GateDatabase, family: str) -> str:
    taken = {parts[0].figure_id for parts in db.figures().values()
             if parts and parts[0].family == family}
    n = 1
    while f"{family}#{n}" in taken:
        n += 1
    return f"{family}#{n}"


def enroll_figure(db: GateDatabase, source: TagSource) -> None:
    print("\n-- Multi-qubit figure --")
    family_name = ask_choice("family", list(FAMILIES))
    family = FAMILIES[family_name]
    fid = ask("figure id", default=suggest_figure_id(db, family_name))

    clash = [e for e in db.entries.values()
             if e.type == "multi_part" and e.figure_id == fid]
    if clash:
        print(f"     figure id '{fid}' already has {len(clash)} tag(s) "
              "in the database; enrolling will overwrite captured UIDs "
              "but leave the old tags' rows in place if their UIDs differ.")
        if not ask_yesno("continue with this figure id?"):
            return

    captured: list[tuple[str, str]] = []      # (role, uid)
    exclude: set[str] = set()
    for role in family.roles:
        uid = capture_unique(source, db,
                             f"the {role.upper()} of {fid}", exclude)
        captured.append((role, uid))
        exclude.add(uid)

    print(f"  {fid} ({family_name}):")
    for role, uid in captured:
        print(f"    {role:10s} {uid}")
    if not ask_yesno("save these entries?", default=True):
        print("  discarded")
        return
    for role, uid in captured:
        db.upsert_entry(TagEntry(uid=uid, display_name=f"{fid} {role}",
                                 type="multi_part", family=family_name,
                                 role=role, figure_id=fid))
    print(f"  saved {len(captured)} tags for {fid}")


def list_db(db: GateDatabase) -> None:
    print(f"\n-- {len(db.entries)} tags in {db.path} --")
    for e in sorted(db.entries.values(),
                    key=lambda e: (e.type, e.figure_id, e.display_name)):
        extra = (f"{e.figure_id} {e.role}" if e.type == "multi_part"
                 else e.gate_string)
        print(f"  {e.uid:16s} {e.type:12s} {e.display_name:24s} {extra}")


# main
def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="gates.csv")
    parser.add_argument("--port", default=None)
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--manual", action="store_true",
                        help="no hardware: type UIDs by hand")
    args = parser.parse_args()

    db = GateDatabase(args.db)
    for e in db.load_errors:
        print(f"database warning: {e}")

    link = None
    if args.manual:
        source = TagSource(None, None, manual=True)
    else:
        port = args.port
        if not port:
            ports = available_ports()
            if len(ports) == 1:
                port = ports[0]
                print(f"using the only serial port found: {port}")
            else:
                print("available ports: " + (", ".join(ports) or "none"))
                print("re-run with --port <port>, or --manual to type UIDs")
                sys.exit(1)
        board = BoardState()
        status_q: queue.Queue = queue.Queue(maxsize=200)
        link = SerialLink(port, args.baud, board, status_q)
        link.start()
        source = TagSource(board, status_q, manual=False)

    print("\nTag enrollment -- tags are read from COLUMN 1 of the board")
    try:
        while True:
            print("\n[1] single gate  [2] measurement  [3] multi-qubit "
                  "figure  [4] list database  [q] quit")
            try:
                choice = input("> ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                break
            try:
                if choice == "1":
                    enroll_single(db, source)
                elif choice == "2":
                    enroll_measurement(db, source)
                elif choice == "3":
                    enroll_figure(db, source)
                elif choice == "4":
                    list_db(db)
                elif choice == "q":
                    break
            except Abort:
                print("  aborted -- back to menu")
    finally:
        if link:
            link.stop()
    print(f"done -- database now holds {len(db.entries)} tags")


if __name__ == "__main__":
    main()
