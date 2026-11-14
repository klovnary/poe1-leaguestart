"""League Start Tracker - a LiveSplit-style timer for a Path of Exile league start.

Right-click the window for the menu. Click the highlighted voidstone (or press
Space) when you get it.
Not affiliated with or endorsed by Grinding Gear Games.
"""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import tkinter.font as tkfont

from datetime import datetime

import leagues
import updater
from tracker import ATLAS, Tracker

# LiveSplit's default colours
BG = "#0f0f0f"
CURRENT = "#1c3f8a"      # highlighted split
TEXT = "#ffffff"
GRAY = "#c4c4c4"
AHEAD = "#00cc36"
BEHIND = "#cc1200"
GOLD = "#d8af1f"
FONT = "Segoe UI"
ZONE_BG = "#13213f"      # zones under the open act
ROW_BUDGET = 28          # most split lines shown at once (acts fold to stay under it)


class Label(tk.Label):
    """A label that skips updates that don't change anything. The window redraws
    5 times a second; without this every redraw re-lays out the whole window."""
    def config(self, cnf=None, **kw):
        if cnf is not None:
            return super().config(cnf, **kw)
        cache = self.__dict__.setdefault("_set", {})
        changed = {k: v for k, v in kw.items() if k not in cache or cache[k] != v}
        if changed:
            cache.update(changed)
            super().config(**changed)
    configure = config


class Frame(tk.Frame):
    def config(self, cnf=None, **kw):
        if cnf is not None:
            return super().config(cnf, **kw)
        cache = self.__dict__.setdefault("_set", {})
        changed = {k: v for k, v in kw.items() if k not in cache or cache[k] != v}
        if changed:
            cache.update(changed)
            super().config(**changed)
    configure = config


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


def countdown(seconds):
    days, rest = divmod(int(seconds), 86400)
    h, rest = divmod(rest, 3600)
    m, s = divmod(rest, 60)
    return f"{days}d {h}h {m:02d}m" if days else f"{h}:{m:02d}:{s:02d}"


class App:
    def __init__(self, root):
        self.root = root
        self.tracker = Tracker()
        root.title("League Start")
        root.configure(bg=BG)
        root.geometry(self.tracker.window or "300x700")   # position and width; height fits itself
        root.attributes("-topmost", True)
        self.on_top = tk.BooleanVar(value=True)
        self.fonts = {}           # (size, bold) -> font; all resized together with the window
        self.scale = 1.0
        root.bind("<Configure>", self.window_resized)

        self.title = Label(root, text="", bg=BG, fg=TEXT, font=self.font(11, bold=True))
        self.title.pack(fill="x", pady=(8, 0))
        self.subtitle = Label(root, text="", bg=BG, fg=GRAY, font=self.font(10))
        self.subtitle.pack(fill="x", pady=(0, 6))

        # Split lines (acts, zones, voidstones). If the window is too short, these are
        # what gets cut, never the timer: the block below gets its space first.
        self.splits_frame = Frame(root, bg=BG)
        self.splits_frame.pack(fill="both", expand=True)
        self.lower = Frame(root, bg=BG)
        self.rows = []
        self.obj_labels = []
        for i in range(32):   # 10 acts + every zone of the open act
            row = Frame(self.splits_frame, bg=BG)
            row.pack(fill="x")   # (re-packed by show_rows so only used rows take space)
            name = Label(row, bg=BG, fg=TEXT, font=self.font(10), anchor="w")
            name.pack(side="left", padx=8)
            # used on the voidstone objective lines: one label per objective
            objs = [Label(row, bg=BG, font=self.font(9, bold=True), anchor="w") for _ in range(3)]
            for o in objs:
                o.pack(side="left", padx=(0, 10))
            self.obj_labels.append(objs)
            time = Label(row, bg=BG, fg=TEXT, font=self.font(10), width=8, anchor="e")
            time.pack(side="right", padx=8)
            delta = Label(row, bg=BG, fg=TEXT, font=self.font(10), width=7, anchor="e")
            delta.pack(side="right")
            for widget in (row, name, delta, time, *objs):
                widget.bind("<Button-1>", lambda e, i=i: self.row_clicked(i))
            self.rows.append((row, name, delta, time))

        self.timer = Label(self.lower, text="0:00", bg=BG, fg=GRAY, font=self.font(30, bold=True), anchor="e")
        self.timer.pack(fill="x", padx=8, pady=(10, 0))
        self.timer.bind("<Button-1>", lambda e: self.tracker.toggle_pause())   # click the timer to pause
        self.segment = Label(self.lower, text="", bg=BG, fg=GRAY, font=self.font(10), anchor="e")
        self.segment.pack(fill="x", padx=8)

        self.info = []
        for _ in range(6):
            row = Frame(self.lower, bg=BG)
            row.pack(fill="x", padx=8)
            left = Label(row, bg=BG, fg=TEXT, font=self.font(10), anchor="w")
            left.pack(side="left")
            right = Label(row, bg=BG, fg=TEXT, font=self.font(10), anchor="e")
            right.pack(side="right")
            self.info.append((left, right))

        # Tiny bottom bar: version on the left, update status on the right
        Label(root, text="Not affiliated with Grinding Gear Games", bg=BG, fg="#8a8a8a",
                 font=self.font(8)).pack(side="bottom", pady=(0, 3), before=self.title)
        self.bar = Frame(root, bg=BG)
        self.bar.pack(side="bottom", fill="x", padx=8, before=self.title)
        self.lower.pack(side="bottom", fill="x", before=self.title)
        Label(self.bar, text=updater.version_text(), bg=BG, fg="#b0b0b0", font=self.font(9)).pack(side="left")
        self.update_label = Label(self.bar, text="", bg=BG, fg="#b0b0b0", font=self.font(9))
        self.update_label.pack(side="right")
        self.update_label.config(cursor="hand2")
        self.update_label.bind("<Button-1>", lambda e: self.updater.check_now())   # click: check now
        # Rounded gold button, only shown once an update is downloaded
        self.update_button = tk.Canvas(root, bg=BG, highlightthickness=0, cursor="hand2", height=40)
        self.update_button.bind("<Configure>", lambda e: self.draw_update_button())
        self.update_button.bind("<Enter>", lambda e: self.draw_update_button(hover=True))
        self.update_button.bind("<Leave>", lambda e: self.draw_update_button())
        self.update_button.bind("<Button-1>", lambda e: self.restart_for_update())
        self.update_shown = False
        self.updater = updater.Updater()
        self.updater.check_in_background()

        self.menu = tk.Menu(root, tearoff=0)
        self.menu.add_command(label="Start timer now", command=self.tracker.start_now)
        self.menu.add_command(label="Pause / resume (P)", command=self.tracker.toggle_pause)
        self.menu.add_command(label="Undo last voidstone", command=self.undo)
        self.menu.add_separator()
        self.menu.add_command(label="Reset run...", command=self.new_league)
        self.menu.add_command(label="Find Client.txt...", command=self.choose_log)
        self.menu.add_checkbutton(label="Always on top", variable=self.on_top,
                                  command=lambda: root.attributes("-topmost", self.on_top.get()))
        root.bind("<Button-3>", lambda e: self.menu.tk_popup(e.x_root, e.y_root))
        root.bind("<p>", lambda e: self.tracker.toggle_pause())
        root.bind("<P>", lambda e: self.tracker.toggle_pause())
        root.protocol("WM_DELETE_WINDOW", self.close)

        if not self.tracker.log_path:
            root.after(300, self.choose_log)

        self.read_log()
        self.draw()

    # ---------- text that scales with the window ----------

    def font(self, size, bold=False):
        key = (size, bold)
        if key not in self.fonts:
            self.fonts[key] = tkfont.Font(family=FONT, size=size, weight="bold" if bold else "normal")
        return self.fonts[key]

    def window_resized(self, event):
        """Width sets the text size (300 wide = normal); the height follows the content."""
        if event.widget is not self.root:
            return
        if abs(event.width - getattr(self, "last_width", 0)) < 2:
            return
        self.last_width = event.width
        self.set_scale(max(0.7, min(event.width / 300, 4.0)))

    def set_scale(self, scale):
        if abs(scale - self.scale) < 0.02:
            return
        self.scale = scale
        for (size, bold), f in self.fonts.items():
            f.configure(size=max(6, round(size * scale)))
        if self.update_shown:
            self.draw_update_button()
        self.root.after_idle(self.fit_height)

    def fit_height(self):
        """Make the window as tall as what it shows (it changes as acts open and close),
        up to the screen's height. Only runs when the number of lines changes."""
        root = self.root
        root.update_idletasks()
        need = min(root.winfo_reqheight(), root.winfo_screenheight() - 80)
        if root.winfo_width() > 50 and abs(root.winfo_height() - need) > 2:
            root.geometry(f"{root.winfo_width()}x{need}")

    # ---------- actions ----------

    def undo(self):
        self.tracker.undo_voidstone()

    def row_clicked(self, i):
        """Click a voidstone (or its objectives line) when you get it."""
        if self.tracker.phase() == "atlas" and i // 2 < len(ATLAS):
            self.tracker.split_voidstone(ATLAS[i // 2])

    def new_league(self):
        """Manual reset. Normally not needed: a new league starts by itself when a
        new character enters The Twilight Strand after the league's start date."""
        if self.tracker.run["league"] and not messagebox.askyesno(
                "Reset run", "Reset the timer and start over? Your PB and golds are kept."):
            return
        name = simpledialog.askstring("Reset run", "League name:", parent=self.root,
                                      initialvalue=leagues.league_at(datetime.now()))
        if name:
            self.tracker.new_league(name.strip())

    def choose_log(self):
        path = filedialog.askopenfilename(title="Find Client.txt (in Path of Exile's logs folder)",
                                          filetypes=[("Client.txt", "Client.txt"), ("Text", "*.txt")])
        if path:
            self.tracker.set_log_path(path)

    def draw_update_button(self, hover=False):
        c = self.update_button
        title, small = self.font(10, bold=True), self.font(8)
        h = title.metrics("linespace") + small.metrics("linespace") + 14
        c.config(height=h)
        w = max(c.winfo_width(), 50)
        c.delete("all")
        r, x1, y1, x2, y2 = 10, 1, 1, w - 1, h - 1
        points = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
                  x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        c.create_polygon(points, smooth=True, fill="#e8c35a" if hover else GOLD, outline="")
        mid = h // 2
        c.create_text(w // 2, mid - small.metrics("linespace") // 2, text="\u2b06  Update ready",
                      font=title, fill="#111")
        c.create_text(w // 2, mid + title.metrics("linespace") // 2, text="click to restart \u00b7 your run is kept",
                      font=small, fill="#3a2f12")

    def restart_for_update(self):
        if self.updater.ready:
            self.tracker.window = self.root.geometry()
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
            self.tracker.window = self.root.geometry()   # reopen at the same size and place
            self.tracker.save()
        finally:
            self.root.destroy()

    def show_rows(self, n):
        """Only the first n split rows take up space; the rest are hidden."""
        if n == getattr(self, "rows_shown", None):
            return
        self.rows_shown = n
        for row, *_ in self.rows:
            row.pack_forget()
        for row, *_ in self.rows[:n]:
            row.pack(fill="x")
        self.root.after_idle(self.fit_height)

    def _draw_campaign(self, names, splits, pb, golds, now_time, current):
        """Acts 1-10. The act you're in opens up to list all of its zones: time spent
        in each and the act time when you moved on ("end"); the zone you're in is
        highlighted. Done acts show one line with their total."""
        run = self.tracker.run
        specs = [("act", i) for i in range(len(names))]
        if current is not None and run["started"]:
            zones = self.tracker.zone_times()
            specs[current + 1:current + 1] = [("zone", z) for z in zones]
            # too many lines for the window: fold finished acts, then upcoming ones
            if len(specs) > ROW_BUDGET and current >= 2:
                specs = [("acts", (0, current - 1))] + specs[current:]
            if len(specs) > ROW_BUDGET and current <= 7:
                cut = next(i for i, sp in enumerate(specs) if sp == ("act", current + 1))
                specs = specs[:cut] + [("acts", (current + 1, 9))]
        self.show_rows(len(specs))

        for i, (row, name, delta, time) in enumerate(self.rows):
            delta.config(width=7)
            time.config(width=8)
            for o in self.obj_labels[i]:
                o.config(text="")
            if i >= len(specs):
                continue
            kind, value = specs[i]
            if kind == "zone":                           # a zone of the open act
                zone_name, secs, left, here, visited = value
                for w in (row, name, delta, time, *self.obj_labels[i]):
                    w.config(bg=ZONE_BG)
                color = GOLD if here else ("#e0e0e0" if visited else "#7f8794")
                name.config(text=("\u25b8 " if here else "   ") + zone_name, font=self.font(9), fg=color)
                if visited and secs is None:
                    spent = "N/A"
                else:
                    spent = fmt(secs) if visited else "-"
                delta.config(text=spent, font=self.font(9), fg=color)
                time.config(text=fmt(left) if left is not None else ("" if here else "-"),
                            font=self.font(9), fg=color)
                continue

            name.config(font=self.font(10))
            delta.config(font=self.font(10))
            time.config(font=self.font(10))
            if kind == "acts":                           # several acts folded into one line
                first, last = value
                for w in (row, name, delta, time, *self.obj_labels[i]):
                    w.config(bg=BG)
                name.config(text=f"Acts {first + 1}-{last + 1}", fg=GRAY)
                seg = lambda lst, a: lst[a] - (lst[a - 1] if a else 0)
                if last < len(splits):                   # done ones: their total
                    total = sum(seg(splits, a) for a in range(first, last + 1))
                    time.config(text=fmt(total), fg=TEXT)
                    if pb:
                        diff = total - sum(seg(pb, a) for a in range(first, last + 1))
                        delta.config(text=fmt(diff, sign=True), fg=AHEAD if diff <= 0 else BEHIND)
                    else:
                        delta.config(text="")
                else:                                    # upcoming: your PB's time for them
                    time.config(text=fmt(sum(seg(pb, a) for a in range(first, last + 1))) if pb else "-",
                                fg=GRAY)
                    delta.config(text="")
                continue

            a = value                                    # an act
            bg = CURRENT if a == current else BG
            for w in (row, name, delta, time, *self.obj_labels[i]):
                w.config(bg=bg)
            name.config(text=names[a], fg=TEXT)
            # Each act shows how long it took on its own (not a running total),
            # and the +/- compares it with the same act of your PB run.
            pb_seg = (pb[a] - (pb[a - 1] if a else 0)) if pb else None
            if a < len(splits):                          # done
                segment = splits[a] - (splits[a - 1] if a else 0)
                time.config(text=fmt(segment), fg=TEXT)
                if golds[a] is not None and segment <= golds[a] and pb:
                    delta.config(text=fmt(segment - pb_seg, sign=True), fg=GOLD)
                elif pb:
                    diff = segment - pb_seg
                    delta.config(text=fmt(diff, sign=True), fg=AHEAD if diff <= 0 else BEHIND)
                else:
                    delta.config(text="", fg=TEXT)
            elif a == current and run["started"]:        # running now
                live = now_time - (splits[-1] if splits else 0)
                time.config(text=fmt(live), fg=TEXT)
                if pb_seg is not None and live > pb_seg:
                    delta.config(text=fmt(live - pb_seg, sign=True), fg=BEHIND)
                else:
                    delta.config(text="")
            else:                                        # still to come: your PB's time for it
                time.config(text=fmt(pb_seg) if pb_seg is not None else "-", fg=GRAY)
                delta.config(text="")

    def _draw_voidstones(self, splits, pb, golds):
        """Atlas part: each voidstone on a row, its objectives on the line below.
        Rows show the atlas time when you got it; +/- is against your PB's
        1st/2nd/3rd/4th voidstone (whichever one it was)."""
        t = self.tracker
        got = t.got_voidstones()
        self.show_rows(2 * len(ATLAS))
        for i, (row, name, delta, time) in enumerate(self.rows):
            for w in (row, name, delta, time):
                w.config(bg=BG)
            # objective lines use the whole row; voidstone rows keep the time columns
            delta.config(width=0 if i % 2 else 7)
            time.config(width=0 if i % 2 else 8, font=self.font(10))
            k = i // 2
            if k >= len(ATLAS):
                for o in self.obj_labels[i]:
                    o.config(text="", bg=BG)
                name.config(text="", font=self.font(10))
                delta.config(text="")
                time.config(text="")
                continue
            stone = ATLAS[k]
            objs = t.objectives(stone)
            if i % 2 == 0:                                   # the voidstone itself
                name.config(text=f"{stone} Voidstone", font=self.font(10), fg=TEXT)
                if stone in got:
                    n = got.index(stone)
                    time.config(text=fmt(splits[n]), fg=TEXT)
                    if pb:
                        diff = splits[n] - pb[n]
                        seg = splits[n] - (splits[n - 1] if n else 0)
                        is_gold = golds[n] is not None and seg <= golds[n]
                        delta.config(text=fmt(diff, sign=True), fg=GOLD if is_gold else (AHEAD if diff <= 0 else BEHIND))
                    else:
                        delta.config(text="\u2713", fg=AHEAD)
                else:
                    done = sum(1 for _, d, total in objs if d == total)
                    time.config(text=f"{done}/{len(objs)}", fg=GRAY)
                    delta.config(text="")
            else:                                            # its objectives
                name.config(text="", font=self.font(10))
                for j, o in enumerate(self.obj_labels[i]):
                    if j < len(objs):
                        label, d, total = objs[j]
                        count = f" {d}/{total}" if total > 1 and d < total else ""
                        mark = "\u2713" if d == total else "\u2022"
                        o.config(text=f"{mark} {label}{count}", bg=BG, fg=AHEAD if d == total else "#e6e6e6")
                    else:
                        o.config(text="", bg=BG)
                delta.config(text="")
                time.config(text="")
                continue
            for o in self.obj_labels[i]:
                o.config(text="", bg=BG)

    def draw(self):
        t, run = self.tracker, self.tracker.run
        phase = t.phase()
        names, splits, pb, golds = t.splits()
        now_time = t.timer()
        current = len(splits) if phase != "done" else None

        # Title
        part = {"campaign": "Campaign", "atlas": "Atlas", "done": "Done!"}[phase]
        upcoming = None if run["started"] else leagues.next_league(datetime.now())
        if run["started"]:
            league = run["league"]
        elif upcoming:
            league = upcoming[0]          # a league is about to launch: show that one
        else:
            league = leagues.league_at(datetime.now())
        self.title.config(text=f"{league} - {part}")
        if run["character"]:
            self.subtitle.config(text=f"{run['character']}  ·  Lvl {run['level']}  ·  Deaths {run['deaths']}")
        elif not t.log_path:
            self.subtitle.config(text="Right-click > Find Client.txt...")
        elif run["started"]:
            zone = run.get("zone") or "Go!"
            lvl = f"  ·  area level {run['area_level']}" if run.get("area_level") else ""
            self.subtitle.config(text=f"{zone}{lvl}")
        elif upcoming:
            self.subtitle.config(text=f"Launches in {countdown(upcoming[1])}  ·  then enter The Twilight Strand")
        else:
            self.subtitle.config(text="Starts when a new character enters The Twilight Strand")

        # Splits
        if phase != "campaign":
            self._draw_voidstones(splits, pb, golds)
        if phase == "campaign":
            self._draw_campaign(names, splits, pb, golds, now_time, current)

        # Big timer
        if not run["started"] or run.get("paused"):
            color = GRAY
        elif phase == "done" or not pb or current is None:
            color = AHEAD
        else:
            color = AHEAD if now_time <= pb[current] else BEHIND
        self.timer.config(text=fmt(now_time), fg=color)
        self.segment.config(text="PAUSED - press P or click the timer" if run.get("paused") else "",
                            fg=GOLD)

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
            lines.append(("Campaign", fmt(run["campaign_splits"][-1]), TEXT))
        # Labyrinth: time in each lab (ticks while you're in one), and your bests
        labs = run.get("labs", {})
        if labs:
            parts = []
            for name in ("Normal", "Cruel", "Merciless", "Eternal"):
                if name == "Eternal" and name not in labs:
                    continue
                lab_t = t.lab_time(name)
                if lab_t is None:
                    parts.append(f"{name[0]} -")
                else:
                    live = "" if labs[name]["done"] else "\u25b8"
                    parts.append(f"{name[0]} {fmt(lab_t)}{live}")
            lines.append(("Labs", "  ".join(parts), GOLD if run.get("lab_now") else TEXT))
        bests = t.records.get("lab_best", {})
        if bests:
            lines.append(("Lab bests", "  ".join(f"{n[0]} {fmt(bests[n])}" for n in
                                                  ("Normal", "Cruel", "Merciless", "Eternal") if n in bests), GRAY))
        while len(lines) < len(self.info):
            lines.append(("", "", TEXT))
        for (left, right), (a, b, color) in zip(self.info, lines):
            left.config(text=a)
            right.config(text=b, fg=color)

        self.update_label.config(text=self.updater.status)
        if self.updater.ready and not self.update_shown:
            # packed before the title so it always gets room, right above the version line
            self.update_button.pack(side="bottom", fill="x", padx=8, pady=(6, 4), before=self.lower)
            self.update_shown = True
            self.draw_update_button()
            self.root.after_idle(self.fit_height)
        self.root.after(200, self.draw)


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
    os._exit(0)   # make sure nothing (like an update check) keeps the program running
