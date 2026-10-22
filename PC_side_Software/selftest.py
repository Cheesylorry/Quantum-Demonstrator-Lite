"""Selftest without hardware or GUI: python selftest.py

1. Rebuilds the Teleportation circuit purely from simulated tag placements
   and compares the composed table against the known-good structure.
2. Verifies the SpinDrops crash guard (multi and single in one step, mixed
   figures, incomplete figures, mixed measurement bases, unknown UIDs).
3. Tests the writer (unique names, dedupe, atomic write).
"""

import json
import os
import tempfile

from board import BoardState
from composer import compose_board
from database import GateDatabase
from writer import JsonWriter

HERE = os.path.dirname(os.path.abspath(__file__))
db = GateDatabase(os.path.join(HERE, "gates.csv"))
assert not db.load_errors, db.load_errors

FAILURES = []


def check(label: str, cond: bool, extra: str = "") -> None:
    print(("PASS  " if cond else "FAIL  ") + label + (f"  ({extra})"
                                                      if extra else ""))
    if not cond:
        FAILURES.append(label)

# test 1
# 04xxxxxx UUIDs Do not exist as hardware UUIDs, these are only for testing purposes

# Teleportation:  Had2 | CNOT23 | CNOT12 | Had1 | Meas z(1,2) | CNOT23 | CZ13
b = BoardState()
b.place(1, 0, "04000001")            # H on qubit 2, position 1
b.place(1, 1, "04000010")            # CNOT#1 control on qubit 2, position 2
b.place(2, 1, "04000011")            # CNOT#1 target  on qubit 3, position 2
b.place(0, 2, "04000012")            # CNOT#2 control on qubit 1, position 3
b.place(1, 2, "04000013")            # CNOT#2 target  on qubit 2, position 3
b.place(0, 3, "04000002")            # H on qubit 1, position 4
b.place(0, 4, "04000040")            # measure z qubit 1, position 5
b.place(1, 4, "04000041")            # measure z qubit 2, position 5
b.place(1, 5, "04000010")            # CNOT#1 again, position 6
b.place(2, 5, "04000011")
b.place(0, 6, "04000020")            # CZ#1 control qubit 1, position 7
b.place(2, 6, "04000021")            # CZ#1 target  qubit 3, position 7  (skips qbit2)

cells, _ = b.snapshot()
res = compose_board(cells, db)
check("teleportation board valid", res.valid, "; ".join(res.all_errors()))

expected = [
    {"gate": {"gates": ["E2", "H", "E2"], "name": "H2"}},
    {"gate": {"gates": ["-2/pi*logm(CNOT23)/i"], "name": "CNOT23",
              "ham": True, "multi": True}},
    {"gate": {"gates": ["-2/pi*logm(CNOT12)/i"], "name": "CNOT12",
              "ham": True, "multi": True}},
    {"gate": {"gates": ["H", "E2", "E2"], "name": "H1"}},
    {"measurement": {"basis": "z", "qbit1": True, "qbit2": True}},
    {"gate": {"gates": ["-2/pi*logm(CNOT23)/i"], "name": "CNOT23",
              "ham": True, "multi": True}},
    {"gate": {"gates": ["-2/pi*logm(CZ13)/i"], "name": "CZ13",
              "ham": True, "multi": True}},
]
for i, (got, want) in enumerate(zip(res.table, expected)):
    check(f"step {i + 1} matches teleportation reference", got == want,
          f"got {json.dumps(got)}")

# Cross-check the expression strings against the real reference file if it sits next to this script (optional).
ref_path = os.path.join(HERE, "Teleportation.json")
if os.path.exists(ref_path):
    with open(ref_path, encoding="utf-8") as f:
        ref = json.load(f)
    for i, (got, want) in enumerate(zip(res.table, ref["table"])):
        g = got.get("gate", got.get("measurement"))
        w = want.get("gate", want.get("measurement"))
        same = (got.get("measurement") == want.get("measurement")
                if "measurement" in want
                else g["gates"] == w["gates"]
                and g.get("ham") == w.get("ham")
                and g.get("multi") == w.get("multi"))
        check(f"step {i + 1} matches Teleportation.json", same)

# test 2
# Crash guard: CNOT(1->2) + Hadamard on qubit 3 in the same step.
b2 = BoardState()
b2.place(0, 0, "04000010")
b2.place(1, 0, "04000011")
b2.place(2, 0, "04000001")           # the QuBeads-crashing combination
cells, _ = b2.snapshot()
res2 = compose_board(cells, db)
check("multi + single in one step rejected", not res2.valid,
      "; ".join(res2.all_errors()))
check("no table emitted when invalid", res2.table is None)


# Incomplete figure (control without target).
b3 = BoardState()
b3.place(0, 0, "04000010")
res3 = compose_board(b3.snapshot()[0], db)
check("incomplete CNOT rejected", not res3.valid,
      "; ".join(res3.all_errors()))

# Two different figures in one step.
b4 = BoardState()
b4.place(0, 0, "04000010")
b4.place(1, 0, "04000013")
res4 = compose_board(b4.snapshot()[0], db)
check("mixed figures rejected", not res4.valid,
      "; ".join(res4.all_errors()))


# Mixed measurement bases.
b5 = BoardState()
b5.place(0, 0, "04000040")           # z
b5.place(1, 0, "04000050")           # x
res5 = compose_board(b5.snapshot()[0], db)
check("mixed measurement bases rejected", not res5.valid,
      "; ".join(res5.all_errors()))

# Unknown UID.
b6 = BoardState()
b6.place(0, 0, "DEADBEEF")
res6 = compose_board(b6.snapshot()[0], db)
check("unknown uid rejected", not res6.valid,
      "; ".join(res6.all_errors()))

# Sqrt flag on a single gate.
b7 = BoardState()
b7.place(0, 0, "04000004")
res7 = compose_board(b7.snapshot()[0], db)
g = res7.table[0]["gate"]
check("sqrt array emitted",
      g["gates"] == ["X", "E2", "E2"] and g["sqrt"] == [True, False, False],
      json.dumps(g))



# Empty board equals the empty table.
res8 = compose_board({}, db)
empty_cols = all(c.json_obj == {"gate": {"gates": ["E2", "E2", "E2"],
                                         "name": "Empty"}}
                 for c in res8.columns)
check("empty board -> 7 Empty columns", res8.valid and empty_cols)

#test 3
with tempfile.TemporaryDirectory() as tmp:
    w = JsonWriter(tmp)
    p1 = w.write(res.table)
    check("writer produced a file", p1 is not None and os.path.exists(p1))
    p2 = w.write(res.table)
    check("identical table deduplicated", p2 is None)
    p3 = w.write(res.table, force=True)
    check("forced write gets a unique name",
          p3 is not None and p3 != p1)
    with open(p1, encoding="utf-8") as f:
        doc = json.load(f)
    check("document name matches filename stem",
          doc["name"] == os.path.splitext(os.path.basename(p1))[0])
    check("document skeleton matches template",
          doc["Spin System"] == "Homonuclear" and doc["groups"] == []
          and doc["menu_path"] == [] and len(doc["table"]) == 7)


print()
print("ALL TESTS PASSED :3" if not FAILURES
      else f"{len(FAILURES)} FAILURES: {FAILURES}")
raise SystemExit(1 if FAILURES else 0)
