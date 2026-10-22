"""CSV-backed tag database.

Schema (header row required):

    uid,display_name,type,family,role,figure_id,gate_string,sqrt,inverse

  uid          NFC UID as hex (separators like ':' '-' ' ' are tolerated)
  display_name human readable name shown in the GUI
  type         single | multi_part | measurement
  family       (multi_part only) key into families.FAMILIES, e.g. CNOT
  role         (multi_part only) role within the family, e.g. control
  figure_id    (multi_part only) which physical figure the tag belongs to,
               e.g. CNOT#1 -- all parts of one figure share this id
  gate_string  single:      the gate slot content, e.g. H, X, phase(60)
               measurement: the basis, e.g. z
               multi_part:  unused (composed from the family template)
  sqrt         (single only) true/false, optional
  inverse      (single only) true/false, optional
"""

import csv
import os
from dataclasses import dataclass

from families import FAMILIES

TYPES = ("single", "multi_part", "measurement")
CSV_FIELDS = ["uid", "display_name", "type", "family", "role",
              "figure_id", "gate_string", "sqrt", "inverse"]

_TRUE = {"1", "true", "yes", "y", "x"}


def normalize_uid(raw: str) -> str:
    """Canonical UID form: uppercase hex, no separators."""
    return "".join(c for c in raw.strip().upper() if c not in " :-_")


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in _TRUE


@dataclass(frozen=True)
class TagEntry:
    uid: str
    display_name: str
    type: str
    family: str = ""
    role: str = ""
    figure_id: str = ""
    gate_string: str = ""
    sqrt: bool = False
    inverse: bool = False

    @property
    def short_label(self) -> str:
        if self.type == "multi_part":
            return f"{self.figure_id} {self.role}"
        return self.display_name


class GateDatabase:
    def __init__(self, path: str):
        self.path = path
        self.entries: dict[str, TagEntry] = {}   # uid -> entry
        self.load_errors: list[str] = []
        self.reload()

    # load
    def reload(self) -> None:
        self.entries = {}
        self.load_errors = []
        if not os.path.exists(self.path):
            self.load_errors.append(f"database file not found: {self.path}")
            return
        with open(self.path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames is None:
                self.load_errors.append("database file is empty")
                return
            fields = [fn.strip().lower() for fn in reader.fieldnames]
            missing = [c for c in ("uid", "display_name", "type")
                       if c not in fields]
            if missing:
                self.load_errors.append(
                    f"missing required CSV columns: {', '.join(missing)}")
                return
            for lineno, raw in enumerate(reader, start=2):
                row = {(k or "").strip().lower(): (v or "").strip()
                       for k, v in raw.items()}
                if not any(row.values()):
                    continue  # blank line
                err = self._add_row(row)
                if err:
                    self.load_errors.append(f"line {lineno}: {err}")

    def _add_row(self, row: dict) -> str | None:
        uid = normalize_uid(row.get("uid", ""))
        if not uid:
            return "missing uid"
        if uid in self.entries:
            return f"duplicate uid {uid}"
        typ = row.get("type", "").lower()
        if typ not in TYPES:
            return f"uid {uid}: unknown type '{row.get('type')}'"

        entry = TagEntry(
            uid=uid,
            display_name=row.get("display_name", "") or uid,
            type=typ,
            family=row.get("family", ""),
            role=row.get("role", "").lower(),
            figure_id=row.get("figure_id", ""),
            gate_string=row.get("gate_string", ""),
            sqrt=_parse_bool(row.get("sqrt", "")),
            inverse=_parse_bool(row.get("inverse", "")),
        )

        if typ == "single":
            if not entry.gate_string:
                return f"uid {uid}: single gate needs a gate_string"
        elif typ == "measurement":
            if not entry.gate_string:
                return f"uid {uid}: measurement needs a basis in gate_string"
        elif typ == "multi_part":
            if entry.family not in FAMILIES:
                return (f"uid {uid}: unknown family '{entry.family}' "
                        f"(known: {', '.join(FAMILIES)})")
            if entry.role not in FAMILIES[entry.family].roles:
                return (f"uid {uid}: role '{entry.role}' not valid for "
                        f"{entry.family} (roles: "
                        f"{', '.join(FAMILIES[entry.family].roles)})")
            if not entry.figure_id:
                return f"uid {uid}: multi_part needs a figure_id"

        self.entries[uid] = entry
        return None

    # lookup
    def lookup(self, uid: str) -> TagEntry | None:
        return self.entries.get(normalize_uid(uid))

    # grouped listing
    def singles(self) -> list[TagEntry]:
        return sorted((e for e in self.entries.values() if e.type == "single"),
                      key=lambda e: e.display_name)

    def measurements(self) -> list[TagEntry]:
        return sorted((e for e in self.entries.values()
                       if e.type == "measurement"),
                      key=lambda e: e.display_name)

    def figures(self) -> dict[str, list[TagEntry]]:
        """figure_id -> parts, parts ordered by their family's role order."""
        figs: dict[str, list[TagEntry]] = {}
        for e in self.entries.values():
            if e.type == "multi_part":
                figs.setdefault(e.figure_id, []).append(e)
        for fid, parts in figs.items():
            order = FAMILIES[parts[0].family].roles
            parts.sort(key=lambda e: order.index(e.role)
                       if e.role in order else 99)
        return dict(sorted(figs.items()))

    # upsert
    def upsert_entry(self, entry: TagEntry) -> None:
        """Insert the entry, or overwrite the existing row with the same UID.
        Rewrites the CSV atomically and reloads."""
        target_uid = normalize_uid(entry.uid)
        rows: list[dict] = []
        if os.path.exists(self.path):
            with open(self.path, newline="", encoding="utf-8-sig") as f:
                for raw in csv.DictReader(f):
                    row = {(k or "").strip().lower(): (v or "").strip()
                           for k, v in raw.items()}
                    if any(row.values()):
                        rows.append(row)

        new_row = {
            "uid": target_uid,
            "display_name": entry.display_name,
            "type": entry.type,
            "family": entry.family,
            "role": entry.role,
            "figure_id": entry.figure_id,
            "gate_string": entry.gate_string,
            "sqrt": "true" if entry.sqrt else "false",
            "inverse": "true" if entry.inverse else "false",
        }
        replaced = False
        for i, row in enumerate(rows):
            if normalize_uid(row.get("uid", "")) == target_uid:
                rows[i] = new_row
                replaced = True
                break
        if not replaced:
            rows.append(new_row)

        tmp = self.path + ".tmp"
        with open(tmp, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS,
                                    extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({k: row.get(k, "") for k in CSV_FIELDS})
        os.replace(tmp, self.path)
        self.reload()

    # append
    def append_entry(self, entry: TagEntry) -> str | None:
        """Append a new tag to the CSV and reload. Returns error or None."""
        if self.lookup(entry.uid):
            return f"uid {entry.uid} already in database"
        file_exists = os.path.exists(self.path)
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            if not file_exists or os.path.getsize(self.path) == 0:
                writer.writeheader()
            writer.writerow({
                "uid": normalize_uid(entry.uid),
                "display_name": entry.display_name,
                "type": entry.type,
                "family": entry.family,
                "role": entry.role,
                "figure_id": entry.figure_id,
                "gate_string": entry.gate_string,
                "sqrt": "true" if entry.sqrt else "false",
                "inverse": "true" if entry.inverse else "false",
            })
        self.reload()
        return None
