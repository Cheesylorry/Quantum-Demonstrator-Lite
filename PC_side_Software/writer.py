"""QuBeads JSON output.

Files are written atomically (temp file + os.replacement) so a user that polls the folder 
can never read a half-written file, and only when the composed table actually 
differs from the last written one, so transient re-reads on the hardware never spam identical files.

every file name is the same 'QD_output.json' and the 'name' field differs but includes the timestamp
"""

import json
import os
import time

DEFAULT_PREFIX = "QD_in"


class JsonWriter:
    def __init__(self, out_dir: str, prefix: str = DEFAULT_PREFIX):
        self.out_dir = out_dir
        self.prefix = prefix
        self.last_written_table: str | None = None   # serialized dedupe key
        self.last_path: str | None = None

    def table_changed(self, table: list[dict]) -> bool:
        return self._key(table) != self.last_written_table

    @staticmethod
    def _key(table: list[dict]) -> str:
        return json.dumps(table, sort_keys=True)

    def _unique_stem(self) -> str:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        stem = f"{self.prefix}_{stamp}"     #to keep all
        alt_stem = f"{self.prefix}"          #to overwrite
        candidate, n = stem, 1
        while os.path.exists(os.path.join(self.out_dir, candidate + ".json")):
            candidate = f"{stem}_{n:02d}"
            n += 1
        return candidate
    
    def _not_so_unique_stem(self) -> str:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        stem = f"{self.prefix}_{stamp}"     #to keep all
        alt_stem = f"{self.prefix}"          #to overwrite
        candidate, n = alt_stem, 1
        while os.path.exists(os.path.join(self.out_dir, candidate + ".json")):
            candidate = f"{alt_stem}_{n:02d}"
            n += 1
        return candidate

    def write(self, table: list[dict], force: bool = False) -> str | None:
        """Write a new uniquely named file. Returns the path, or None if the
        content is unchanged and force is False."""
        if not force and not self.table_changed(table):
            return None
        os.makedirs(self.out_dir, exist_ok=True)
        stem = self._unique_stem()
        alt_stem = self._not_so_unique_stem()
        doc = {
            "Spin System": "Homonuclear",
            "desc": "Inputfile from DevBoard",
            "groups": [],
            "menu_path": [],
            "name": stem,
            "table": table,
        }
        #path = os.path.join(self.out_dir, alt_stem + ".json")
        path = os.path.join(self.out_dir, "QD_output" + ".json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
        self.last_written_table = self._key(table)
        self.last_path = path
        return path
