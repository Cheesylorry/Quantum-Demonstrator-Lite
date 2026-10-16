"""
Temporary GUI: live 3x7 board view + manual JSON builder.

gui.py was written with assistance of an LLM

Two board sources feed the *identical* compose/validate/write pipeline:
  Hardware -- populated by the serial thread from PLACE/REMOVE events
  Manual   -- populated by clicking cells and picking tags from a menu
              (for testing SpinDrops without hardware present)

The JSON file is only (re)written when the composed table actually changed
and every column passed validation; while anything is invalid the last
valid file on disk stays untouched.


"""

import queue
import tkinter as tk
from tkinter import ttk, messagebox

from board import BoardState, NUM_ROWS, NUM_COLS
from composer import compose_board
from database import GateDatabase, TagEntry, TYPES, normalize_uid
from families import FAMILIES
from serial_link import SerialLink, available_ports
from writer import JsonWriter

DEBOUNCE_MS = 600         # settle time after the last change before writing
POLL_MS = 100

STATUS_COLORS = {
    "empty":       "#eceff1",
    "single":      "#c8e6c9",
    "multi_part":  "#bbdefb",
    "measurement": "#e1bee7",
    "unknown":     "#ffcc80",
    "invalid":     "#ffcdd2",
}


class App(tk.Tk):
    def __init__(self, db_path: str, out_dir: str,
                 port: str | None = None, baud: int = 115200):
        super().__init__()
        self.title("Quanten Demonstrator PC side interface")
        self.resizable(False, False)

        self.db = GateDatabase(db_path)
        self.writer = JsonWriter(out_dir)
        self.baud = baud

        self.hw_board = BoardState()
        self.manual_board = BoardState()
        self.link: SerialLink | None = None
        self.status_q: queue.Queue = queue.Queue(maxsize=200)

        self.source_var = tk.StringVar(value="hardware")
        self.auto_write_var = tk.BooleanVar(value=True)
        self.port_var = tk.StringVar(value=port or "")

        self._last_seen = {"hardware": -1, "manual": -1}
        self._pending_write_at: int | None = None   # ms timestamp via after()
        self._pending_after_id: str | None = None
        self._board_result = None

        self._build_ui()
        self._refresh_ports()
        if port:
            self.port_var.set(port)
            self._connect()
        self._show_db_errors()
        self._recompose(schedule_write=False)
        self.after(POLL_MS, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ================================================================== UI
    def _build_ui(self) -> None:
        pad = {"padx": 4, "pady": 3}

        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew", **pad)

        ttk.Label(top, text="Source:").pack(side="left")
        for label, val in (("Hardware", "hardware"), ("Manual", "manual")):
            ttk.Radiobutton(top, text=label, value=val,
                            variable=self.source_var,
                            command=self._on_source_change).pack(side="left")

        ttk.Separator(top, orient="vertical").pack(side="left", fill="y",
                                                   padx=8)
        ttk.Label(top, text="Port:").pack(side="left")
        self.port_combo = ttk.Combobox(top, textvariable=self.port_var,
                                       width=18)
        self.port_combo.pack(side="left")
        ttk.Button(top, text="⟳", width=3,
                   command=self._refresh_ports).pack(side="left")
        self.connect_btn = ttk.Button(top, text="Connect",
                                      command=self._toggle_connect)
        self.connect_btn.pack(side="left", padx=4)
        self.conn_label = ttk.Label(top, text="not connected",
                                    foreground="#888")
        self.conn_label.pack(side="left", padx=4)

        # ----------------------------------------------------------- grid
        grid = ttk.Frame(self)
        grid.grid(row=1, column=0, **pad)

        self.col_headers: list[tk.Label] = []
        for col in range(NUM_COLS):
            lbl = tk.Label(grid, text=f"Step {col + 1}", width=16,
                           font=("TkDefaultFont", 9, "bold"))
            lbl.grid(row=0, column=col + 1, padx=2, pady=(0, 2))
            self.col_headers.append(lbl)

        self.cells: dict[tuple[int, int], dict] = {}
        for row in range(NUM_ROWS):
            tk.Label(grid, text=f"Qubit {row + 1}",
                     font=("TkDefaultFont", 9, "bold")
                     ).grid(row=row + 1, column=0, padx=(0, 4))
            for col in range(NUM_COLS):
                frame = tk.Frame(grid, width=130, height=52, bd=1,
                                 relief="ridge", bg=STATUS_COLORS["empty"])
                frame.grid(row=row + 1, column=col + 1, padx=2, pady=2)
                frame.grid_propagate(False)
                name = tk.Label(frame, text="", bg=frame["bg"],
                                font=("TkDefaultFont", 9, "bold"))
                name.place(relx=0.5, rely=0.32, anchor="center")
                uid = tk.Label(frame, text="", bg=frame["bg"],
                               font=("TkDefaultFont", 7), fg="#555")
                uid.place(relx=0.5, rely=0.72, anchor="center")
                for w in (frame, name, uid):
                    w.bind("<Button-1>",
                           lambda _e, r=row, c=col: self._on_cell_click(r, c))
                    w.bind("<Button-3>",
                           lambda _e, r=row, c=col: self._on_cell_right(r, c))
                self.cells[(row, col)] = {"frame": frame, "name": name,
                                          "uid": uid}

        self.col_status: list[tk.Label] = []
        tk.Label(grid, text="").grid(row=NUM_ROWS + 1, column=0)
        for col in range(NUM_COLS):
            lbl = tk.Label(grid, text="–", width=16)
            lbl.grid(row=NUM_ROWS + 1, column=col + 1)
            self.col_status.append(lbl)

        # --------------------------------------------------------- errors
        err_frame = ttk.LabelFrame(self, text="Validation / messages")
        err_frame.grid(row=2, column=0, sticky="ew", **pad)
        self.err_text = tk.Text(err_frame, height=5, width=100,
                                state="disabled", wrap="word",
                                font=("TkDefaultFont", 9))
        self.err_text.pack(fill="both", expand=True, padx=2, pady=2)

        # --------------------------------------------------------- bottom
        bottom = ttk.Frame(self)
        bottom.grid(row=3, column=0, sticky="ew", **pad)
        ttk.Checkbutton(bottom, text=f"Auto-write JSON "
                        f"(debounce {DEBOUNCE_MS} ms)",
                        variable=self.auto_write_var).pack(side="left")
        ttk.Button(bottom, text="Write JSON now",
                   command=self._write_now).pack(side="left", padx=4)
        self.clear_btn = ttk.Button(bottom, text="Clear manual board",
                                    command=self._clear_manual)
        self.clear_btn.pack(side="left", padx=4)
        ttk.Button(bottom, text="Reload database",
                   command=self._reload_db).pack(side="left", padx=4)

        info = ttk.Frame(self)
        info.grid(row=4, column=0, sticky="ew", **pad)
        ttk.Label(info, text=f"Output folder: {self.writer.out_dir}",
                  foreground="#555").pack(side="left")
        self.last_file_label = ttk.Label(info, text="   Last written: —",
                                         foreground="#555")
        self.last_file_label.pack(side="left")

        self.statusbar = ttk.Label(self, text="ready", anchor="w",
                                   relief="sunken")
        self.statusbar.grid(row=5, column=0, sticky="ew")

    # =========================================================== serial UI
    def _refresh_ports(self) -> None:
        ports = available_ports()
        self.port_combo["values"] = ports
        if ports and not self.port_var.get():
            self.port_var.set(ports[0])

    def _toggle_connect(self) -> None:
        if self.link:
            self._disconnect()
        else:
            self._connect()

    def _connect(self) -> None:
        port = self.port_var.get().strip()
        if not port:
            messagebox.showwarning("No port", "Select a serial port first.")
            return
        self.link = SerialLink(port, self.baud, self.hw_board, self.status_q)
        self.link.start()
        self.connect_btn.config(text="Disconnect")

    def _disconnect(self) -> None:
        if self.link:
            self.link.stop()
            self.link = None
        self.connect_btn.config(text="Connect")
        self.conn_label.config(text="not connected", foreground="#888")

    # ============================================================ actions
    def _active_board(self) -> BoardState:
        return (self.hw_board if self.source_var.get() == "hardware"
                else self.manual_board)

    def _on_source_change(self) -> None:
        self._cancel_pending_write()
        self._recompose(schedule_write=False)

    def _clear_manual(self) -> None:
        self.manual_board.clear()

    def _reload_db(self) -> None:
        self.db.reload()
        self._show_db_errors()
        self._recompose(schedule_write=False)
        self._set_status("database reloaded "
                         f"({len(self.db.entries)} tags)")

    def _write_now(self) -> None:
        if self._board_result is None or not self._board_result.valid:
            messagebox.showerror(
                "Invalid board",
                "The board has validation errors -- fix them first:\n\n"
                + "\n".join(self._board_result.all_errors()
                            if self._board_result else []))
            return
        path = self.writer.write(self._board_result.table, force=True)
        self._after_write(path)

    # ====================================================== manual builder
    def _on_cell_click(self, row: int, col: int) -> None:
        if self.source_var.get() == "manual":
            self._open_place_menu(row, col)
        else:
            self._maybe_register(row, col)

    def _on_cell_right(self, row: int, col: int) -> None:
        self._maybe_register(row, col)

    def _open_place_menu(self, row: int, col: int) -> None:
        menu = tk.Menu(self, tearoff=0)

        singles = self.db.singles()
        if singles:
            m = tk.Menu(menu, tearoff=0)
            for e in singles:
                m.add_command(label=f"{e.display_name}  [{e.gate_string}]",
                              command=lambda e=e: self._manual_place(
                                  row, col, e))
            menu.add_cascade(label="Single gates", menu=m)

        figures = self.db.figures()
        if figures:
            m = tk.Menu(menu, tearoff=0)
            for fid, parts in figures.items():
                sub = tk.Menu(m, tearoff=0)
                for e in parts:
                    sub.add_command(label=e.role,
                                    command=lambda e=e: self._manual_place(
                                        row, col, e))
                m.add_cascade(label=f"{fid} ({parts[0].family})", menu=sub)
            menu.add_cascade(label="Multi-gate parts", menu=m)

        meas = self.db.measurements()
        if meas:
            m = tk.Menu(menu, tearoff=0)
            for e in meas:
                m.add_command(label=f"{e.display_name}  "
                                    f"[basis {e.gate_string}]",
                              command=lambda e=e: self._manual_place(
                                  row, col, e))
            menu.add_cascade(label="Measurements", menu=m)

        menu.add_separator()
        menu.add_command(label="Clear cell",
                         command=lambda: self.manual_board.remove(row, col))
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    def _manual_place(self, row: int, col: int, entry: TagEntry) -> None:
        self.manual_board.place(row, col, entry.uid)

    # ==================================================== tag registration
    def _maybe_register(self, row: int, col: int) -> None:
        cells, _v = self._active_board().snapshot()
        uid = cells.get((row, col))
        if uid and self.db.lookup(uid) is None:
            RegisterDialog(self, self.db, uid,
                           on_done=lambda: self._recompose(
                               schedule_write=True))

    # ========================================================== poll loop
    def _poll(self) -> None:
        while True:
            try:
                msg = self.status_q.get_nowait()
            except queue.Empty:
                break
            self._set_status(msg)
        if self.link:
            if self.link.connected:
                self.conn_label.config(text=f"connected ({self.link.port})",
                                       foreground="#2e7d32")
            else:
                self.conn_label.config(text="waiting for device...",
                                       foreground="#e65100")

        src = self.source_var.get()
        version = self._active_board().version
        if version != self._last_seen[src]:
            self._last_seen[src] = version
            self._recompose(schedule_write=True)

        self.after(POLL_MS, self._poll)

    # ================================================= compose and render
    def _recompose(self, schedule_write: bool) -> None:
        cells, _v = self._active_board().snapshot()
        result = compose_board(cells, self.db)
        self._board_result = result
        self._render(cells, result)
        if schedule_write and self.auto_write_var.get():
            self._schedule_write()

    def _render(self, cells: dict, result) -> None:
        for (row, col), widgets in self.cells.items():
            uid = cells.get((row, col))
            if uid is None:
                status, name_txt, uid_txt = "empty", "", ""
            else:
                entry = self.db.lookup(uid)
                status = result.cell_status.get((row, col), "unknown")
                name_txt = entry.short_label if entry else "unknown tag"
                uid_txt = uid
            color = STATUS_COLORS.get(status, STATUS_COLORS["empty"])
            widgets["frame"].config(bg=color)
            widgets["name"].config(text=name_txt, bg=color)
            widgets["uid"].config(text=uid_txt, bg=color)

        for col, col_result in enumerate(result.columns):
            if not col_result.valid:
                self.col_status[col].config(text="✗ invalid",
                                            fg="#c62828")
                self.col_headers[col].config(fg="#c62828")
            elif col_result.json_obj.get("gate", {}).get("name") == "Empty":
                self.col_status[col].config(text="–", fg="#888")
                self.col_headers[col].config(fg="black")
            else:
                self.col_status[col].config(text="OK", fg="#2e7d32")
                self.col_headers[col].config(fg="black")

        self._show_errors(result)

    def _show_errors(self, result) -> None:
        lines = list(self.db.load_errors)
        lines += result.all_errors()
        self.err_text.config(state="normal")
        self.err_text.delete("1.0", "end")
        if lines:
            self.err_text.insert("end", "\n".join(lines))
        else:
            self.err_text.insert("end", "all steps valid")
        self.err_text.config(state="disabled")

    def _show_db_errors(self) -> None:
        for e in self.db.load_errors:
            self._set_status(f"database: {e}")

    # ====================================================== write pipeline
    def _schedule_write(self) -> None:
        self._cancel_pending_write()
        self._pending_after_id = self.after(DEBOUNCE_MS, self._fire_write)

    def _cancel_pending_write(self) -> None:
        if self._pending_after_id:
            self.after_cancel(self._pending_after_id)
            self._pending_after_id = None

    def _fire_write(self) -> None:
        self._pending_after_id = None
        if self._board_result is None:
            return
        if not self._board_result.valid:
            self._set_status("board invalid -- JSON not written "
                             "(last valid file kept)")
            return
        table = self._board_result.table
        if not self.writer.table_changed(table):
            return
        path = self.writer.write(table)
        self._after_write(path)

    def _after_write(self, path: str | None) -> None:
        if path:
            self.last_file_label.config(text=f"   Last written: {path}")
            self._set_status(f"wrote {path}")

    # ============================================================== misc
    def _set_status(self, msg: str) -> None:
        self.statusbar.config(text=msg)

    def _on_close(self) -> None:
        self._disconnect()
        self.destroy()


# ==========================================================================
class RegisterDialog(tk.Toplevel):
    """Add an unknown tag UID to the CSV database."""

    def __init__(self, parent: App, db: GateDatabase, uid: str, on_done):
        super().__init__(parent)
        self.title("Register tag")
        self.db = db
        self.on_done = on_done
        self.resizable(False, False)
        self.grab_set()

        self.v_uid = tk.StringVar(value=uid)
        self.v_name = tk.StringVar()
        self.v_type = tk.StringVar(value="single")
        self.v_family = tk.StringVar()
        self.v_role = tk.StringVar()
        self.v_figure = tk.StringVar()
        self.v_gate = tk.StringVar()
        self.v_sqrt = tk.BooleanVar()
        self.v_inverse = tk.BooleanVar()

        rows = [
            ("UID", ttk.Entry(self, textvariable=self.v_uid, width=24)),
            ("Display name", ttk.Entry(self, textvariable=self.v_name,
                                       width=24)),
            ("Type", ttk.Combobox(self, textvariable=self.v_type,
                                  values=list(TYPES), state="readonly",
                                  width=22)),
            ("Family (multi)", ttk.Combobox(self, textvariable=self.v_family,
                                            values=list(FAMILIES),
                                            width=22)),
            ("Role (multi)", ttk.Entry(self, textvariable=self.v_role,
                                       width=24)),
            ("Figure id (multi)", ttk.Entry(self, textvariable=self.v_figure,
                                            width=24)),
            ("Gate string / basis", ttk.Entry(self, textvariable=self.v_gate,
                                              width=24)),
            ("sqrt (single)", ttk.Checkbutton(self, variable=self.v_sqrt)),
            ("inverse (single)", ttk.Checkbutton(self,
                                                 variable=self.v_inverse)),
        ]
        for i, (label, widget) in enumerate(rows):
            ttk.Label(self, text=label).grid(row=i, column=0, sticky="e",
                                             padx=6, pady=2)
            widget.grid(row=i, column=1, sticky="w", padx=6, pady=2)

        btns = ttk.Frame(self)
        btns.grid(row=len(rows), column=0, columnspan=2, pady=6)
        ttk.Button(btns, text="Save", command=self._save).pack(side="left",
                                                               padx=4)
        ttk.Button(btns, text="Cancel",
                   command=self.destroy).pack(side="left", padx=4)

    def _save(self) -> None:
        entry = TagEntry(
            uid=normalize_uid(self.v_uid.get()),
            display_name=self.v_name.get().strip() or self.v_uid.get(),
            type=self.v_type.get(),
            family=self.v_family.get().strip(),
            role=self.v_role.get().strip().lower(),
            figure_id=self.v_figure.get().strip(),
            gate_string=self.v_gate.get().strip(),
            sqrt=self.v_sqrt.get(),
            inverse=self.v_inverse.get(),
        )
        err = self._validate(entry) or self.db.append_entry(entry)
        if err:
            messagebox.showerror("Cannot register", err, parent=self)
            return
        if self.db.load_errors:
            messagebox.showwarning(
                "Registered with warnings",
                "\n".join(self.db.load_errors), parent=self)
        self.on_done()
        self.destroy()

    @staticmethod
    def _validate(e: TagEntry) -> str | None:
        if not e.uid:
            return "UID is required"
        if e.type == "single" and not e.gate_string:
            return "single gates need a gate string"
        if e.type == "measurement" and not e.gate_string:
            return "measurements need a basis (e.g. z)"
        if e.type == "multi_part":
            if e.family not in FAMILIES:
                return "multi_part needs a known family"
            if e.role not in FAMILIES[e.family].roles:
                return (f"role must be one of: "
                        f"{', '.join(FAMILIES[e.family].roles)}")
            if not e.figure_id:
                return "multi_part needs a figure id"
        return None
