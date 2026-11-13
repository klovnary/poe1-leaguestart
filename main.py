"""League Start Tracker - a LiveSplit-style timer for a Path of Exile league start.

Right-click the window for the menu. Click the highlighted voidstone (or press
Space) when you get it.
Not affiliated with or endorsed by Grinding Gear Games.
"""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

import updater
from tracker import Tracker

# LiveSplit's default colours
BG = "#0f0f0f"
CURRENT = "#1c3f8a"      # highlighted split
TEXT = "#ffffff"
GRAY = "#acacac"
AHEAD = "#00cc36"
BEHIND = "#cc1200"
GOLD = "#d8af1f"
FONT = "Segoe UI"


def fmt(seconds, sign=False):
    if seconds is None:
        return "-"
    prefix = ""
    if sign:
        prefix = "-" if seconds < 0 else "+"
        seconds = abs(seconds)
    seconds = int(seconds)
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{prefix}{h}:{m:02d}:{s:02d}" if h else f"{prefix}{m}:{s:02d}"


class App:
    def __init__(self, root):
        self.root = root
        self.tracker = Tracker()
        root.title("League Start")
        root.configure(bg=BG)
        root.geometry("300x470")
        root.attributes("-topmost", True)
        self.on_top = tk.BooleanVar(value=True)

        self.title = tk.Label(root, text="", bg=BG, fg=TEXT, font=(FONT, 11, "bold"))
        self.title.pack(fill="x", pady=(8, 0))
        self.subtitle = tk.Label(root, text="", bg=BG, fg=GRAY, font=(FONT, 9))
        self.subtitle.pack(fill="x", pady=(0, 6))

        # 10 rows is enough for either list (10 acts / 4 voidstones)
        self.rows = []
        for i in range(10):
            row = tk.Frame(root, bg=BG)
            row.pack(fill="x")
            name = tk.Label(row, bg=BG, fg=TEXT, font=(FONT, 10), anchor="w")
            name.pack(side="left", padx=8)
            time = tk.Label(row, bg=BG, fg=TEXT, font=(FONT, 10), width=8, anchor="e")
            time.pack(side="right", padx=8)
            delta = tk.Label(row, bg=BG, fg=TEXT, font=(FONT, 10), width=7, anchor="e")
            delta.pack(side="right")
            for widget in (row, name, delta, time):
                widget.bind("<Button-1>", lambda e, i=i: self.row_clicked(i))
            self.rows.append((row, name, delta, time))

        self.timer = tk.Label(root, text="0:00", bg=BG, fg=GRAY, font=(FONT, 30, "bold"), anchor="e")
        self.timer.pack(fill="x", padx=8, pady=(10, 0))
        self.segment = tk.Label(root, text="", bg=BG, fg=GRAY, font=(FONT, 10), anchor="e")
        self.segment.pack(fill="x", padx=8)

        self.info = []
        for _ in range(3):
            row = tk.Frame(root, bg=BG)
            row.pack(fill="x", padx=8)
            left = tk.Label(row, bg=BG, fg=TEXT, font=(FONT, 9), anchor="w")
            left.pack(side="left")
            right = tk.Label(row, bg=BG, fg=TEXT, font=(FONT, 9), anchor="e")
            right.pack(side="right")
            self.info.append((left, right))

        # Tiny bottom bar: version on the left, update status on the right
        tk.Label(root, text="Not affiliated with Grinding Gear Games", bg=BG, fg="#555",
                 font=(FONT, 7)).pack(side="bottom", pady=(0, 3))
        bar = tk.Frame(root, bg=BG)
        bar.pack(side="bottom", fill="x", padx=8)
        tk.Label(bar, text=updater.version_text(), bg=BG, fg="#555", font=(FONT, 7)).pack(side="left")
        self.update_label = tk.Label(bar, text="", bg=BG, fg="#555", font=(FONT, 7))
        self.update_label.pack(side="right")
        self.update_label.bind("<Button-1>", lambda e: self.restart_for_update())
        self.updater = updater.Updater()
        self.updater.check_in_background()

        self.menu = tk.Menu(root, tearoff=0)
        self.menu.add_command(label="Split voidstone (Space)", command=self.split)
        self.menu.add_command(label="Undo voidstone", command=self.undo)
        self.menu.add_separator()
        self.menu.add_command(label="New league...", command=self.new_league)
        self.menu.add_command(label="Find Client.txt...", command=self.choose_log)
        self.menu.add_checkbutton(label="Always on top", variable=self.on_top,
                                  command=lambda: root.attributes("-topmost", self.on_top.get()))
        root.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        root.bind("<space>", lambda e: self.split())
        root.protocol("WM_DELETE_WINDOW", self.close)

        if not self.tracker.log_path:
            root.after(300, self.choose_log)
        elif not self.tracker.run["league"]:
            root.after(300, self.new_league)

        self.read_log()
        self.draw()

    # ---------- actions ----------

    def split(self):
        self.tracker.split_voidstone()

    def undo(self):
        self.tracker.undo_voidstone()

    def row_clicked(self, i):
        if self.tracker.phase() == "atlas" and i == len(self.tracker.run["atlas_splits"]):
            self.split()

    def new_league(self):
        if self.tracker.run["league"] and not messagebox.askyesno(
                "New league", "Reset and start a new league? Your PB and golds are kept."):
            return
        name = simpledialog.askstring("New league", "League name:", parent=self.root)
        if name:
            self.tracker.new_league(name.strip())

    def choose_log(self):
        path = filedialog.askopenfilename(title="Find Client.txt (in Path of Exile's logs folder)",
                                          filetypes=[("Client.txt", "Client.txt"), ("Text", "*.txt")])
        if path:
            self.tracker.set_log_path(path)
            if not self.tracker.run["league"]:
                self.new_league()

    def restart_for_update(self):
        if self.updater.ready:
            self.tracker.save()
            updater.restart()
            self.root.destroy()

    # ---------- loops ----------

    def read_log(self):
        more = self.tracker.poll()
        # catching up on a big log: keep reading in small steps so the window stays responsive
        self.root.after(10 if more else 1000, self.read_log)

    def close(self):
        try:
            self.tracker.save()
        finally:
            self.root.destroy()

    def draw(self):
        t, run = self.tracker, self.tracker.run
        phase = t.phase()
        names, splits, pb, golds = t.splits()
        now_time = t.timer()
        current = len(splits) if phase != "done" else None

        # Title
        part = {"campaign": "Campaign", "atlas": "Atlas", "done": "Done!"}[phase]
        self.title.config(text=f"{run['league'] or 'Path of Exile'} - {part}")
        if run["character"]:
            self.subtitle.config(text=f"{run['character']}  ·  Lvl {run['level']}  ·  Deaths {run['deaths']}")
        elif not t.log_path:
            self.subtitle.config(text="Right-click > Find Client.txt...")
        else:
            self.subtitle.config(text="Timer starts at your first level up")

        # Splits
        for i, (row, name, delta, time) in enumerate(self.rows):
            if i >= len(names):
                for w in (row, name, delta, time):
                    w.config(bg=BG)
                name.config(text="")
                delta.config(text="")
                time.config(text="")
                continue
            bg = CURRENT if i == current else BG
            for w in (row, name, delta, time):
                w.config(bg=bg)
            name.config(text=names[i])
            if i < len(splits):                       # done
                time.config(text=fmt(splits[i]), fg=TEXT)
                segment = splits[i] - (splits[i - 1] if i else 0)
                if pb:
                    diff = splits[i] - pb[i]
                    color = GOLD if golds[i] is not None and segment <= golds[i] else (AHEAD if diff <= 0 else BEHIND)
                    delta.config(text=fmt(diff, sign=True), fg=color)
                else:
                    delta.config(text="", fg=TEXT)
            else:                                     # still to come
                time.config(text=fmt(pb[i]) if pb else "-", fg=GRAY)
                # show the live delta once you're behind your PB on this split
                if i == current and pb and run["character"] and now_time > pb[i]:
                    delta.config(text=fmt(now_time - pb[i], sign=True), fg=BEHIND)
                else:
                    delta.config(text="")

        # Big timer
        if not run["character"]:
            color = GRAY
        elif phase == "done" or not pb or current is None:
            color = AHEAD
        else:
            color = AHEAD if now_time <= pb[current] else BEHIND
        self.timer.config(text=fmt(now_time), fg=color)
        last = splits[-1] if splits else 0
        self.segment.config(text=f"Segment  {fmt(now_time - last)}" if phase != "done" else "")

        # Info lines
        lines = []
        if splits and pb:
            i = len(splits) - 1
            prev = (splits[i] - (splits[i - 1] if i else 0)) - (pb[i] - (pb[i - 1] if i else 0))
            lines.append(("Previous Segment", fmt(prev, sign=True), AHEAD if prev <= 0 else BEHIND))
        else:
            lines.append(("Previous Segment", "-", TEXT))
        sob = sum(golds) if None not in golds else None
        lines.append(("Sum of Best", fmt(sob), TEXT))
        if phase == "campaign":
            lines.append(("Personal Best", fmt(pb[-1]) if pb else "-", TEXT))
        else:
            tier = f"  ·  T{run['best_tier']}" if run["best_tier"] else ""
            lines.append((f"Maps {len(run['map_seeds'])}{tier}", f"Total {fmt(t.total())}", TEXT))
        for (left, right), (a, b, color) in zip(self.info, lines):
            left.config(text=a)
            right.config(text=b, fg=color)

        ready = self.updater.ready
        self.update_label.config(text=self.updater.status, fg=GOLD if ready else "#555",
                                 cursor="hand2" if ready else "",
                                 font=(FONT, 7, "underline") if ready else (FONT, 7))
        self.root.after(200, self.draw)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
    os._exit(0)   # make sure nothing (like an update check) keeps the program running
