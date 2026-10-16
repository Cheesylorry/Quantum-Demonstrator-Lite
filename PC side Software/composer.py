"""Board -> SpinDrops JSON composition and validation.

Every column (time step) must independently pass validation before any
JSON is emitted; a single invalid column blocks the whole file so
SpinDrops can never be fed a crashing configuration (e.g. a CNOT and a
Hadamard sharing one time step).

Column rules:
  * unknown UID anywhere            -> invalid
  * any multi_part tag present      -> ALL tags in the column must belong to
                                       the same figure_id, with every role of
                                       its family present exactly once, and
                                       nothing else in the column
  * any measurement tag present     -> only measurement tags allowed, and all
                                       must share the same basis
  * otherwise (single gates only)   -> always valid; E2 fills empty rows
"""

from dataclasses import dataclass, field

from board import NUM_ROWS, NUM_COLS
from database import GateDatabase, TagEntry
from families import FAMILIES

EMPTY_COLUMN = {"gate": {"gates": ["E2"] * NUM_ROWS, "name": "Empty"}}


@dataclass
class ColumnResult:
    json_obj: dict | None          # None when invalid
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass
class BoardResult:
    columns: list[ColumnResult]
    cell_status: dict[tuple[int, int], str]   # (row,col) -> status keyword

    @property
    def valid(self) -> bool:
        return all(c.valid for c in self.columns)

    @property
    def table(self) -> list[dict] | None:
        if not self.valid:
            return None
        return [c.json_obj for c in self.columns]

    def all_errors(self) -> list[str]:
        out = []
        for col, c in enumerate(self.columns):
            out.extend(f"Step {col + 1}: {e}" for e in c.errors)
        return out


def compose_board(cells: dict[tuple[int, int], str],
                  db: GateDatabase) -> BoardResult:
    columns: list[ColumnResult] = []
    cell_status: dict[tuple[int, int], str] = {}

    for col in range(NUM_COLS):
        tags: list[tuple[int, str, TagEntry | None]] = []
        for row in range(NUM_ROWS):
            uid = cells.get((row, col))
            if uid is not None:
                tags.append((row, uid, db.lookup(uid)))
        result = _compose_column(tags)
        columns.append(result)

        for row, uid, entry in tags:
            if entry is None:
                cell_status[(row, col)] = "unknown"
            elif not result.valid:
                cell_status[(row, col)] = "invalid"
            else:
                cell_status[(row, col)] = entry.type

    return BoardResult(columns=columns, cell_status=cell_status)


# --------------------------------------------------------------------------
def _compose_column(tags: list[tuple[int, str, TagEntry | None]]
                    ) -> ColumnResult:
    if not tags:
        return ColumnResult(json_obj=dict(EMPTY_COLUMN))

    errors = [f"unknown tag {uid} on Qubit {row + 1} (not in database)"
              for row, uid, entry in tags if entry is None]
    if errors:
        return ColumnResult(None, errors)

    known: list[tuple[int, TagEntry]] = [(r, e) for r, _u, e in tags]
    types = {e.type for _r, e in known}

    if "multi_part" in types:
        return _compose_multi(known, types)
    if "measurement" in types:
        return _compose_measurement(known, types)
    return _compose_singles(known)


def _compose_multi(known: list[tuple[int, TagEntry]],
                   types: set[str]) -> ColumnResult:
    errors: list[str] = []

    # Rule 1: nothing but parts of ONE figure may share the column.
    intruders = [(r, e) for r, e in known if e.type != "multi_part"]
    for r, e in intruders:
        errors.append(f"'{e.display_name}' (Qubit {r + 1}) cannot share a "
                      f"time step with a multi-qubit gate")

    parts = [(r, e) for r, e in known if e.type == "multi_part"]
    figure_ids = {e.figure_id for _r, e in parts}
    if len(figure_ids) > 1:
        errors.append("parts of different figures in one time step: "
                      + ", ".join(sorted(figure_ids)))
    if errors:
        return ColumnResult(None, errors)

    # Rule 2: completeness -- every role exactly once.
    family_name = parts[0][1].family
    family = FAMILIES[family_name]
    role_rows: dict[str, list[int]] = {}
    for r, e in parts:
        role_rows.setdefault(e.role, []).append(r)

    fid = parts[0][1].figure_id
    for role in family.roles:
        rows = role_rows.get(role, [])
        if not rows:
            errors.append(f"{fid} incomplete: '{role}' tag missing")
        elif len(rows) > 1:
            errors.append(f"{fid}: role '{role}' appears "
                          f"{len(rows)} times")
    for role in role_rows:
        if role not in family.roles:
            errors.append(f"{fid}: unexpected role '{role}'")
    if errors:
        return ColumnResult(None, errors)

    # Compose: role -> 1-based qubit number fills the templates.
    fmt = {role: role_rows[role][0] + 1 for role in family.roles}
    obj = {"gate": {
        "gates": [family.expr_fmt.format(**fmt)],
        "name": family.name_fmt.format(**fmt),
        "ham": True,
        "multi": True,
    }}
    return ColumnResult(obj)


def _compose_measurement(known: list[tuple[int, TagEntry]],
                         types: set[str]) -> ColumnResult:
    errors: list[str] = []
    intruders = [(r, e) for r, e in known if e.type != "measurement"]
    for r, e in intruders:
        errors.append(f"'{e.display_name}' (Qubit {r + 1}) cannot share a "
                      f"time step with a measurement")
    bases = {e.gate_string.lower() for _r, e in known
             if e.type == "measurement"}
    if len(bases) > 1:
        errors.append("mixed measurement bases in one time step: "
                      + ", ".join(sorted(bases)))
    if errors:
        return ColumnResult(None, errors)

    meas: dict = {"basis": bases.pop()}
    rows = sorted(r for r, e in known)
    for r in rows:
        meas[f"qbit{r + 1}"] = True
    return ColumnResult({"measurement": meas})


def _compose_singles(known: list[tuple[int, TagEntry]]) -> ColumnResult:
    gates = ["E2"] * NUM_ROWS
    sqrt = [False] * NUM_ROWS
    inverse = [False] * NUM_ROWS
    name_parts = []
    for r, e in sorted(known):
        gates[r] = e.gate_string
        sqrt[r] = e.sqrt
        inverse[r] = e.inverse
        name_parts.append(f"{e.gate_string}{r + 1}")

    gate: dict = {"gates": gates}
    if any(sqrt):
        gate["sqrt"] = sqrt
    if any(inverse):
        gate["inverse"] = inverse
    gate["name"] = " ".join(name_parts)
    return ColumnResult({"gate": gate})
