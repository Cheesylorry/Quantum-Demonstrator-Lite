"""
Copyright (C) 2026  Henry Hill, Max Planck Institute of Quantum Optics

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.


Quantum demonstrator PC-side -- PC-side interface for the 3x7 NFC reader board.

Usage:
    python main.py [--db gates.csv] [--out output] [--port COM5] [--baud 115200]

Reads PLACE/REMOVE events from the Pico firmware, resolves tag UIDs to
quantum gates through the CSV database, validates every time step, and
writes uniquely named SpinDrops JSON files whenever the board changes.
"""

import argparse
import os

from gui import App


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=os.path.join(here, "gates.csv"),
                        help="path to the tag database CSV")
    parser.add_argument("--out", default=os.path.join(here, "output"),
                        help="folder for generated JSON files")
    parser.add_argument("--port", default=None,
                        help="serial port to auto-connect on start "
                             "(e.g. COM5 or /dev/ttyACM0)")
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    app = App(db_path=args.db, out_dir=args.out,
              port=args.port, baud=args.baud)
    app.mainloop()


if __name__ == "__main__":
    main()
