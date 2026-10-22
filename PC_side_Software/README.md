# Quantum Board Bridge

PC-side interface for the 3x7 NFC gate board (Pico 2 firmware). Reads
PLACE/REMOVE events over USB serial, resolves tag UIDs to quantum gates
through a CSV database, validates every time step, and writes uniquely
named SpinDrops JSON files whenever the board content changes. Tested on Linux, Mac OS and Windows remain untested.

## Requirements

    Python 3.14 or newer
    pip install pyserial

Tkinter ships with the standard Python installer on Windows, on Linux you
may need to use your distros Package manager.

    dnf install python3-tkinter


## Run

    python main.py                          # defaults: gates.csv, ./output
    python main.py --port COM5              # auto-connect on start
    python main.py --db mytags.csv --out /home/[username]/Documents/-

## Coordinates

Row = qubit (row 0 = Qubit 1, the top line of the grid), column = time step
(1 through 7, left to right). The firmware's reader index maps as
`row = pos // 7`, `col = pos % 7`. Rows and columns are kept separate
everywhere in the code, the GUI, and all messages.

## The tag database (gates.csv)

One row per physical NFC tag:

    uid,display_name,type,family,role,figure_id,gate_string,sqrt,inverse

| type        | uses                                                        |
|-------------|-------------------------------------------------------------|
| single      | `gate_string` = slot content (`H`, `X`, `phase(60)`), optional `sqrt`/`inverse` flags |
| multi_part  | `family` (CNOT / CZ / Toffoli), `role` within it, `figure_id` shared by all tags of one physical figure (e.g. `CNOT#1`) |
| measurement | `gate_string` = basis (`z`, `x`, ...)                        |

Multi-qubit gates are *composed from placement*: the rows the parts land
on fill the expression, so control on Qubit 2 + target on Qubit 3 yields
`-2/pi*logm(CNOT23)/i`; flip the figure and you get `CNOT32`. Non-adjacent
spans (e.g. CZ 1->3 across an empty Qubit 2) work automatically. Each
physical figure needs its own set of UIDs / its own `figure_id`, otherwise
the software cannot pair the parts.

Unknown tags appear orange in the GUI; click them (right-click in manual
mode) to register them into the CSV without leaving the program.

To add a new gate family (e.g. SWAP), add one entry to `FAMILIES` in
`families.py` and the matching tag rows to the CSV.

## Validation (QBeads crash guard)

A JSON file is only written when **every** step passes:

- a step containing any multi-qubit part contains only the UUIDs belongingto the Multi gate figure (no CNOT + Hadamard, no two figures, no control without its target, no meassurements)
-  measurement steps contain only measurements with the same basis (WIP)
- no unknown UIDs on the board.

While any step is invalid, the last valid file on disk stays untouched;
the GUI shows the step and the reason in red.

## Output files

Only triggered by a change to the arreangement currently on the board with a 600 ms debounce (placing a two-tag figure does not create an intermediate file), deduplicated (identical board content is not rewritten). Each file gets a unique name like
`Qu_20260720_154212.json`; the internal `name` field matches this. (Reason for this is QBeads refusing to open files with the same `Name` entry). Empty positions render as the `Empty` / `["E2","E2","E2"]`,a partially filled board is always a valid 7-step file.

## GUI

- **Source toggle** Hardware / Manual -- both feed the identical pipeline.
- **Hardware**: pick the COM port, Connect. On every (re)connect the state
  is cleared and a resync (`R`) is requested, so it always mirrors the
  physical board; the link auto-retries if the device is unplugged.
- **Manual builder**: click any cell to place a gate, a figure part, or a
  measurement from the database menu, or clear the cell -- for testing
  SpinDrops without hardware.
- **Write JSON now** forces a file (still validated); the auto-write
  checkbox controls the change-driven writing.
- **Enroll gate**: used to introduce new Hardare gates, writing the UUIDs into the CSV.  (WIP)


## Enrolling new Gates (WIP)

By running the enroll.py prgram pointed to the Port at which the board is located. Most likely `/dev/ttyACM0`on Linux and \com0 on windows. 

    python enroll.py --port /dev/ttyACM0 

and follow the instructions. The Names are only Important if you want to designate your own gates, otherwise you can name your gate anything, this has no effect on the results.
## Files

    main.py         CLI
    gui.py          Tkinter GUI, write scheduling, tag registration
    serial_link.py  serial thread (PLACE/REMOVE parsing, auto-reconnect)
    board.py        thread-safe (row, col) board state
    composer.py     validation + column -> JSON composition
    families.py     multi-qubit gate templates
    database.py     CSV load/lookup/append
    writer.py       debounced-safe unique-name atomic writer
    gates.csv       example database (replace UIDs with your real tags)
    selftest.py     hardware-free regression test
    enroll.py       Enters new gates into the CSV (WIP)
