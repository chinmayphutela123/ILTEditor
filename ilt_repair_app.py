"""
ILT Repair Tool - desktop UI.

Repairs Dyndrite-exported Aconity .ilt files that fail to import into
Aconity Studio with "PART META INVALID". Scan data is never modified.
"""

import os
import queue
import threading
import traceback
import webbrowser
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import ilt_core as core

# ---------------------------------------------------------------- palette
PURPLE = "#6400FF"
GREEN = "#00B989"
BLACK = "#000000"
WHITE = "#FFFFFF"
GREY = "#6B6B6B"      # secondary text only
HAIRLINE = "#E2E2E2"  # 1px separators only

FONT = "Segoe UI"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ILT Repair Tool  -  Dyndrite to Aconity")
        self.geometry("1180x760")
        self.minsize(1000, 640)
        self.configure(bg=WHITE)

        self.reports = {}          # path -> Report
        self.queue = queue.Queue()
        self.busy = False

        self.spot = tk.StringVar(value="%.3f" % core.DEFAULT_SPOT_DIAMETER)
        self.shift_z = tk.BooleanVar(value=False)
        self.out_dir = tk.StringVar(value="")

        self._style()
        self._build()
        self.after(80, self._drain)

    # ------------------------------------------------------------ styling
    def _style(self):
        s = ttk.Style(self)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass

        s.configure(".", background=WHITE, foreground=BLACK,
                    fieldbackground=WHITE, font=(FONT, 10))
        s.configure("TFrame", background=WHITE)
        s.configure("TLabel", background=WHITE, foreground=BLACK)
        s.configure("Dim.TLabel", foreground=GREY)
        s.configure("H1.TLabel", font=(FONT, 19, "bold"), foreground=BLACK)
        s.configure("Sub.TLabel", font=(FONT, 10), foreground=GREY)
        s.configure("Sec.TLabel", font=(FONT, 10, "bold"), foreground=BLACK)

        s.configure("TCheckbutton", background=WHITE, foreground=BLACK)
        s.map("TCheckbutton", background=[("active", WHITE)])
        s.configure("TEntry", bordercolor=HAIRLINE, lightcolor=HAIRLINE,
                    darkcolor=HAIRLINE, insertcolor=BLACK)

        # Primary (purple) button
        s.configure("P.TButton", background=PURPLE, foreground=WHITE,
                    font=(FONT, 10, "bold"), borderwidth=0, focusthickness=0,
                    padding=(16, 9))
        s.map("P.TButton",
              background=[("disabled", "#CFCFCF"), ("pressed", "#5200D6"),
                          ("active", "#7526FF")],
              foreground=[("disabled", "#8A8A8A")])

        # Success (green) button
        s.configure("G.TButton", background=GREEN, foreground=WHITE,
                    font=(FONT, 10, "bold"), borderwidth=0, focusthickness=0,
                    padding=(16, 9))
        s.map("G.TButton",
              background=[("disabled", "#CFCFCF"), ("pressed", "#009C74"),
                          ("active", "#17C79A")],
              foreground=[("disabled", "#8A8A8A")])

        # Secondary (outlined) button
        s.configure("S.TButton", background=WHITE, foreground=BLACK,
                    font=(FONT, 10), borderwidth=1, relief="solid",
                    bordercolor=HAIRLINE, focusthickness=0, padding=(14, 8))
        s.map("S.TButton",
              background=[("active", "#F6F2FF"), ("disabled", WHITE)],
              foreground=[("active", PURPLE), ("disabled", "#B0B0B0")])

        s.configure("Treeview", background=WHITE, fieldbackground=WHITE,
                    foreground=BLACK, rowheight=30, borderwidth=0,
                    font=(FONT, 10))
        s.configure("Treeview.Heading", background=WHITE, foreground=GREY,
                    font=(FONT, 9, "bold"), borderwidth=0, relief="flat",
                    padding=(8, 8))
        s.map("Treeview.Heading", background=[("active", WHITE)])
        s.map("Treeview", background=[("selected", "#F1E9FF")],
              foreground=[("selected", BLACK)])

        s.configure("P.Horizontal.TProgressbar", background=PURPLE,
                    troughcolor="#F0F0F0", borderwidth=0, thickness=5)

    def _rule(self, parent):
        tk.Frame(parent, bg=HAIRLINE, height=1).pack(fill="x")

    # -------------------------------------------------------------- build
    def _build(self):
        # ---- header
        head = ttk.Frame(self, padding=(26, 20, 26, 16))
        head.pack(fill="x")
        tk.Frame(head, bg=PURPLE, width=5, height=44).pack(side="left",
                                                           padx=(0, 14))
        box = ttk.Frame(head)
        box.pack(side="left", anchor="w")
        ttk.Label(box, text="ILT Repair Tool", style="H1.TLabel").pack(anchor="w")
        ttk.Label(box, text="Makes Dyndrite .ilt exports importable by Aconity "
                            "Studio.  Vectors and scan order are never modified.",
                  style="Sub.TLabel").pack(anchor="w", pady=(2, 0))
        ttk.Label(head, text="v" + core.__version__,
                  style="Sub.TLabel").pack(side="right", anchor="n")
        self._rule(self)

        # ---- toolbar
        bar = ttk.Frame(self, padding=(26, 14, 26, 14))
        bar.pack(fill="x")
        ttk.Button(bar, text="Add ILT files", style="P.TButton",
                   command=self.add_files).pack(side="left")
        ttk.Button(bar, text="Remove", style="S.TButton",
                   command=self.remove_sel).pack(side="left", padx=(8, 0))
        ttk.Button(bar, text="Clear all", style="S.TButton",
                   command=self.clear).pack(side="left", padx=(8, 0))

        self.btn_repair = ttk.Button(bar, text="Repair all", style="G.TButton",
                                     command=self.repair_all, state="disabled")
        self.btn_repair.pack(side="right")
        self.btn_folder = ttk.Button(bar, text="Open output folder",
                                     style="S.TButton",
                                     command=self.open_folder, state="disabled")
        self.btn_folder.pack(side="right", padx=(0, 8))
        self.btn_report = ttk.Button(bar, text="Save report", style="S.TButton",
                                     command=self.save_report, state="disabled")
        self.btn_report.pack(side="right", padx=(0, 8))

        # ---- options
        opt = ttk.Frame(self, padding=(26, 0, 26, 14))
        opt.pack(fill="x")
        ttk.Label(opt, text="Spot diameter", style="Dim.TLabel").pack(side="left")
        e = ttk.Entry(opt, textvariable=self.spot, width=7, justify="center")
        e.pack(side="left", padx=(8, 2))
        ttk.Label(opt, text="mm", style="Dim.TLabel").pack(side="left")
        ttk.Checkbutton(opt, text="Shift all layers up by one thickness "
                                  "(only if Studio shows the part one layer low)",
                        variable=self.shift_z,
                        command=self.reanalyse).pack(side="left", padx=(22, 0))
        ttk.Label(opt, textvariable=self.out_dir,
                  style="Dim.TLabel").pack(side="right")
        ttk.Button(opt, text="Output folder...", style="S.TButton",
                   command=self.pick_out).pack(side="right", padx=(10, 8))
        self.out_dir.set('Saving to an "ACONITY ready" subfolder, original name kept')
        self._rule(self)

        # ---- split: file list / detail
        body = ttk.Frame(self, padding=(26, 14, 26, 8))
        body.pack(fill="both", expand=True)
        pane = ttk.PanedWindow(body, orient="horizontal")
        pane.pack(fill="both", expand=True)

        left = ttk.Frame(pane)
        pane.add(left, weight=3)
        cols = ("status", "sections", "layers", "issues")
        self.tree = ttk.Treeview(left, columns=cols, show="tree headings",
                                 selectmode="extended")
        self.tree.heading("#0", text="FILE", anchor="w")
        self.tree.column("#0", width=330, anchor="w")
        for c, t, w in (("status", "STATUS", 120), ("sections", "SECTIONS", 82),
                        ("layers", "LAYERS", 82), ("issues", "FINDINGS", 86)):
            self.tree.heading(c, text=t, anchor="w")
            self.tree.column(c, width=w, anchor="w", stretch=(c == "issues"))
        self.tree.tag_configure("ok", foreground=GREEN)
        self.tree.tag_configure("fix", foreground=PURPLE)
        self.tree.tag_configure("err", foreground=BLACK)
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.show_detail)

        right = ttk.Frame(pane, padding=(16, 0, 0, 0))
        pane.add(right, weight=4)
        ttk.Label(right, text="ASSESSMENT", style="Sec.TLabel").pack(anchor="w")
        wrap = tk.Frame(right, bg=HAIRLINE, bd=0)
        wrap.pack(fill="both", expand=True, pady=(8, 0))
        self.detail = tk.Text(wrap, wrap="word", bg=WHITE, fg=BLACK, bd=0,
                              padx=16, pady=14, font=(FONT, 10),
                              spacing1=1, spacing3=4, cursor="arrow")
        ds = ttk.Scrollbar(wrap, orient="vertical", command=self.detail.yview)
        self.detail.configure(yscrollcommand=ds.set)
        self.detail.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        ds.pack(side="right", fill="y")

        t = self.detail
        t.tag_configure("h", font=(FONT, 13, "bold"), foreground=BLACK,
                        spacing3=8)
        t.tag_configure("sec", font=(FONT, 9, "bold"), foreground=GREY,
                        spacing1=14, spacing3=6)
        t.tag_configure("title", font=(FONT, 10, "bold"), foreground=BLACK)
        t.tag_configure("purple", font=(FONT, 10, "bold"), foreground=PURPLE)
        t.tag_configure("green", font=(FONT, 10, "bold"), foreground=GREEN)
        t.tag_configure("body", foreground=GREY, lmargin1=18, lmargin2=18,
                        spacing3=6)
        t.tag_configure("mono", font=("Consolas", 9), foreground=BLACK,
                        lmargin1=18, lmargin2=18)
        t.tag_configure("dim", foreground=GREY)
        t.configure(state="disabled")

        # ---- footer
        self._rule(self)
        foot = ttk.Frame(self, padding=(26, 10, 26, 14))
        foot.pack(fill="x")
        self.status = ttk.Label(foot, text="Add one or more .ilt files to begin.",
                                style="Dim.TLabel")
        self.status.pack(side="left")
        self.pbar = ttk.Progressbar(foot, style="P.Horizontal.TProgressbar",
                                    mode="determinate", length=260)
        self.pbar.pack(side="right")
        self.pbar.pack_forget()

        self._placeholder()

    def _placeholder(self):
        self._render(("Nothing loaded\n", "h"),
                ("Click “Add ILT files” to load one or more Dyndrite "
                 "exports. Each file is inspected and every proposed change is "
                 "listed here for you to check before anything is written.\n",
                 "body"),
                ("\nWhat this tool never changes\n", "sec"),
                ("Vector coordinates, record order, polyline direction flags, "
                 "layer order and layer Z heights are copied through untouched. "
                 "After each repair the output is re-read and compared against "
                 "the source; if the scan data differs in any way the output is "
                 "discarded.\n", "body"))

    def _render(self, *chunks):
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        for text, tag in chunks:
            self.detail.insert("end", text, tag)
        self.detail.configure(state="disabled")

    # ------------------------------------------------------------- actions
    def _spot(self):
        try:
            v = float(self.spot.get())
            if not 0 < v < 2:
                raise ValueError
            return v
        except ValueError:
            messagebox.showwarning(
                "Spot diameter",
                "Enter a spot diameter in mm between 0 and 2.\n"
                "Using the default %.3f mm." % core.DEFAULT_SPOT_DIAMETER)
            self.spot.set("%.3f" % core.DEFAULT_SPOT_DIAMETER)
            return core.DEFAULT_SPOT_DIAMETER

    def add_files(self):
        if self.busy:
            return
        paths = filedialog.askopenfilenames(
            title="Select ILT file(s)",
            filetypes=[("Aconity ILT", "*.ilt"), ("All files", "*.*")])
        new = [p for p in paths if p not in self.reports]
        if new:
            self._run_analysis(new)

    def reanalyse(self):
        if self.reports and not self.busy:
            self._run_analysis(list(self.reports))

    def _run_analysis(self, paths):
        self._set_busy(True, "Analysing %d file(s)..." % len(paths))
        spot, shift = self._spot(), self.shift_z.get()

        def work():
            for i, p in enumerate(paths):
                try:
                    r = core.analyse(p, spot, shift)
                except Exception:
                    r = core.Report(p)
                    r.error = traceback.format_exc(limit=2)
                self.queue.put(("report", r))
                self.queue.put(("prog", (i + 1, len(paths))))
            self.queue.put(("done_analyse", None))

        threading.Thread(target=work, daemon=True).start()

    def repair_all(self):
        if self.busy:
            return
        todo = [r for r in self.reports.values()
                if r.needs_repair and not r.error and not r.output_path]
        if not todo:
            messagebox.showinfo("Nothing to repair",
                                "No loaded file needs repair.")
            return
        out = None if self.out_dir.get().startswith("Saving to an") \
            else self.out_dir.get()
        if out:
            for r in todo:
                if os.path.abspath(os.path.dirname(r.path)) == os.path.abspath(out):
                    pass
        spot, shift = self._spot(), self.shift_z.get()
        stamp = datetime.now().timetuple()[:6]
        self._set_busy(True, "Repairing...")

        def work():
            for i, r in enumerate(todo):
                dst = core.default_output_path(r.path, out)
                try:
                    self.queue.put(("msg", "Repairing %s" % r.name))
                    core.repair(r, dst, spot, shift, stamp)
                except Exception as e:
                    r.error = str(e)
                self.queue.put(("update", r))
                self.queue.put(("prog", (i + 1, len(todo))))
            self.queue.put(("done_repair", None))

        threading.Thread(target=work, daemon=True).start()

    def remove_sel(self):
        if self.busy:
            return
        for iid in self.tree.selection():
            self.reports.pop(iid, None)
            self.tree.delete(iid)
        self._refresh_buttons()
        self._placeholder()

    def clear(self):
        if self.busy:
            return
        self.reports.clear()
        self.tree.delete(*self.tree.get_children())
        self._refresh_buttons()
        self._placeholder()
        self.status.configure(text="Add one or more .ilt files to begin.")

    def pick_out(self):
        d = filedialog.askdirectory(title="Choose an output folder")
        self.out_dir.set(d if d else 'Saving to an "ACONITY ready" subfolder, original name kept')

    def open_folder(self):
        done = [r for r in self.reports.values() if r.output_path]
        if done:
            webbrowser.open(os.path.dirname(done[-1].output_path))

    def save_report(self):
        if not self.reports:
            return
        p = filedialog.asksaveasfilename(
            title="Save verification report", defaultextension=".txt",
            initialfile="ILT repair report %s.txt"
                        % datetime.now().strftime("%Y-%m-%d %H%M"),
            filetypes=[("Text file", "*.txt")])
        if not p:
            return
        with open(p, "w", encoding="utf-8") as f:
            f.write("ILT REPAIR REPORT\n")
            f.write("Generated   : %s\n" % datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            f.write("Tool version: %s\n" % core.__version__)
            f.write("Spot diameter: %.3f mm   Shift Z: %s\n"
                    % (self._spot(), "yes" if self.shift_z.get() else "no"))
            for r in self.reports.values():
                f.write("\n" + "=" * 72 + "\n%s\n  status : %s\n  source : %s\n"
                        % (r.name, r.status, r.path))
                if r.output_path:
                    f.write("  output : %s\n" % r.output_path)
                if r.verify_detail:
                    f.write("  verify : %s\n" % r.verify_detail)
                if r.error:
                    f.write("  ERROR  : %s\n" % r.error)
                if r.stats:
                    f.write("  stats  : %s\n" % r.stats)
                for fi in r.findings:
                    f.write("   [%s] %s\n      %s\n      %s  ->  %s\n"
                            % (fi.severity, fi.title, fi.detail,
                               fi.before or "-", fi.after or "-"))
        messagebox.showinfo("Report saved", p)

    # -------------------------------------------------------------- queue
    def _drain(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "report":
                    self.reports[payload.path] = payload
                    self._put_row(payload)
                elif kind == "update":
                    self._put_row(payload)
                    if self.tree.selection() and \
                            self.tree.selection()[0] == payload.path:
                        self.show_detail()
                elif kind == "prog":
                    done, total = payload
                    self.pbar.configure(maximum=total, value=done)
                elif kind == "msg":
                    self.status.configure(text=payload)
                elif kind == "done_analyse":
                    self._set_busy(False)
                    self._summarise()
                    kids = self.tree.get_children()
                    if kids and not self.tree.selection():
                        self.tree.selection_set(kids[0])
                elif kind == "done_repair":
                    self._set_busy(False)
                    self._summarise()
        except queue.Empty:
            pass
        self.after(80, self._drain)

    def _put_row(self, r):
        tag = "ok" if r.status in ("REPAIRED", "ALREADY OK") else \
              ("fix" if r.status == "NEEDS REPAIR" else "err")
        vals = (r.status,
                r.stats.get("sections", "-"),
                r.stats.get("layers", "-"),
                len(r.findings) if r.findings else ("-" if not r.error else "!"))
        if self.tree.exists(r.path):
            self.tree.item(r.path, text="  " + r.name, values=vals, tags=(tag,))
        else:
            self.tree.insert("", "end", iid=r.path, text="  " + r.name,
                             values=vals, tags=(tag,))
        self._refresh_buttons()

    def _refresh_buttons(self):
        pend = any(r.needs_repair and not r.error and not r.output_path
                   for r in self.reports.values())
        done = any(r.output_path for r in self.reports.values())
        self.btn_repair.configure(state="normal" if pend and not self.busy
                                  else "disabled")
        self.btn_folder.configure(state="normal" if done else "disabled")
        self.btn_report.configure(state="normal" if self.reports else "disabled")

    def _summarise(self):
        n = len(self.reports)
        rep = sum(1 for r in self.reports.values() if r.output_path)
        pend = sum(1 for r in self.reports.values()
                   if r.needs_repair and not r.error and not r.output_path)
        ok = sum(1 for r in self.reports.values()
                 if not r.needs_repair and not r.error)
        err = sum(1 for r in self.reports.values() if r.error)
        bits = ["%d file(s) loaded" % n]
        if pend:
            bits.append("%d need repair" % pend)
        if rep:
            bits.append("%d repaired and verified" % rep)
        if ok:
            bits.append("%d already valid" % ok)
        if err:
            bits.append("%d could not be read" % err)
        self.status.configure(text="   ·   ".join(bits))

    def _set_busy(self, busy, msg=None):
        self.busy = busy
        if busy:
            self.pbar.pack(side="right")
            self.pbar.configure(value=0)
            if msg:
                self.status.configure(text=msg)
        else:
            self.pbar.pack_forget()
        self._refresh_buttons()

    # ------------------------------------------------------------- detail
    def show_detail(self, _evt=None):
        sel = self.tree.selection()
        if not sel:
            return
        r = self.reports.get(sel[0])
        if not r:
            return
        out = [(r.name + "\n", "h")]

        if r.error:
            out += [("COULD NOT BE PROCESSED\n", "sec"),
                    (r.error + "\n", "body"),
                    ("\nThe source file was not modified.\n", "body")]
            self._render(*out)
            return

        if r.output_path:
            out += [("REPAIRED AND VERIFIED\n", "sec"),
                    ("✓  " + r.verify_detail + "\n", "green"),
                    ("Saved to\n", "body"), (r.output_path + "\n", "mono")]
        elif not r.needs_repair:
            out += [("ALREADY VALID\n", "sec"),
                    ("✓  This file already matches the Aconity dialect. "
                     "No changes are needed.\n", "green")]
        else:
            out += [("READY TO REPAIR\n", "sec"),
                    ("%d change(s) proposed. Nothing is written until you press "
                     "“Repair all”.\n" % (len(r.blockers) + len(r.dialect)),
                     "body")]

        st = r.stats
        out += [("FILE CONTENTS\n", "sec"),
                ("%s toolpath file(s)   %s modelsection(s)   %s layer record(s)\n"
                 % (st.get("cli_files", "?"), st.get("sections", "?"),
                    st.get("layers", "?")), "mono")]

        groups = [("CAUSE OF THE IMPORT ERROR", r.blockers, "purple"),
                  ("DIALECT DIFFERENCES REPAIRED", r.dialect, "purple"),
                  ("FLAGGED FOR YOUR REVIEW", r.reviews, "purple")]
        for head, items, tag in groups:
            if not items:
                continue
            out.append((head + "\n", "sec"))
            for f in items:
                out.append(("  " + f.title + "\n", tag))
                out.append((f.detail + "\n", "body"))
                if f.before or f.after:
                    out.append(("%s:  %s  →  %s\n"
                                % (f.action or "change", f.before or "-",
                                   f.after or "-"), "mono"))

        out += [("SCAN DATA GUARANTEE\n", "sec"),
                ("Vector coordinates, record order, polyline direction flags, "
                 "layer order and layer Z heights are never altered. Only the "
                 "part-id field, the file header and the parameter file are "
                 "rewritten. Every repair is verified against the source before "
                 "the output is kept.\n", "body")]
        self._render(*out)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
