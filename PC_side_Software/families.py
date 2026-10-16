"""Multi-qubit gate families.

A "family" describes a physical multi-tag figure (CNOT, CZ, Toffoli, ...).
Each tag of the figure carries a *role*; the qubit (row) each tag lands on
fills the name/expression templates.

Templates use the role names as format fields, which receive the 1-based
qubit number of the tag holding that role, e.g. control on qubit 2 and
target on qubit 3 ->  "CNOT23"  /  "-2/pi*logm(CNOT23)/i".

To add a new family, add one entry here and matching rows to the CSV
database (one row per tag/role).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Family:
    roles: tuple          # required roles, each exactly once per figure
    name_fmt: str         # JSON "name" field template
    expr_fmt: str         # Hamiltonian expression template ("gates" entry)


FAMILIES = {
    "CNOT": Family(
        roles=("control", "target"),
        name_fmt="CNOT{control}{target}",
        expr_fmt="-2/pi*logm(CNOT{control}{target})/i",
    ),
    "CZ": Family(
        roles=("control", "target"),
        name_fmt="CZ{control}{target}",
        expr_fmt="-2/pi*logm(CZ{control}{target})/i",
    ),
    "Toffoli": Family(
        roles=("control1", "control2", "target"),
        name_fmt="Toffoli",
        expr_fmt="-2/pi*logm(Toffoli({control1},{control2},{target}))/i",
    ),
}
