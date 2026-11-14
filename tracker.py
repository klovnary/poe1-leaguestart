"""Reads Path of Exile's Client.txt and keeps track of a league start "run".

The run has two parts, like two speedrun categories back to back:
  Campaign  - Act 1 to Act 10 (splits automatically when you enter the next act)
  Atlas     - Voidstone 1 to 4 (you split these yourself)
Everything is saved to one JSON file, including your best times (PB and golds).
"""
import json
import os
import re
from datetime import datetime

import leagues

CAMPAIGN = [f"Act {n}" for n in range(1, 11)]
# The four voidstones and what leads to each. An objective is ticked when you
# enter that boss's arena (the log doesn't say when a boss dies).
VOIDSTONES = [
    ("Eldritch", [("Star & Hunger", ["MapWorldsPrimordialBoss1", "MapWorldsPrimordialBoss2"]),
                  ("Exarch", ["MapWorldsPrimordialBoss3"]),
                  ("Eater", ["MapWorldsPrimordialBoss4"])]),
    ("Ceremonial", [("Crucible", ["MavenHub"]),
                    ("Maven", ["MavenBoss"])]),
    ("Decayed", [("Guardians", ["MapWorldsMinotaur", "MapWorldsChimera", "MapWorldsHydra", "MapWorldsPhoenix"]),
                 ("Shaper", ["MapWorldsShapersRealm"]),
                 ("Elder", ["MapWorldsElderArena"])]),
    ("Originator", [("Fear & Neglect", ["MapWorldsMemoryBoss1", "MapWorldsMemoryBoss2"]),
                    ("Dread", ["MapWorldsMemoryBoss3"])]),
]
ATLAS = [name for name, _ in VOIDSTONES]
OBJECTIVE_AREAS = {a for _, objs in VOIDSTONES for _, areas in objs for a in areas}

CHUNK = 500_000  # bytes of Client.txt read per step
MAX_GAP = 300   # seconds between log lines; longer = AFK/offline, not counted
TIME_FORMAT = "%Y/%m/%d %H:%M:%S"

LOG_PATHS = [
    r"C:\Program Files (x86)\Steam\steamapps\common\Path of Exile\logs\Client.txt",
    r"C:\Program Files\Steam\steamapps\common\Path of Exile\logs\Client.txt",
    r"C:\Program Files (x86)\Grinding Gear Games\Path of Exile\logs\Client.txt",
    r"C:\Program Files\Grinding Gear Games\Path of Exile\logs\Client.txt",
]

GENERATING = re.compile(r'Generating level (\d+) area "([^"]+)" with seed (\d+)')
LEVEL_UP = re.compile(r"\] : (\S+) \(([^)]+)\) is now level (\d+)$")
DEATH = re.compile(r"\] : (\S+) has been slain\.$")
LOADING = re.compile(r"\[LOADING SCREEN\] \((.+)\) Duration")   # gives the zone's real name
JOINED = re.compile(r"\] : (\S+) has joined the area\.$")
# Labyrinth rooms: 1_ Normal, 2_ Cruel, 3_ Merciless, EndGame_ Eternal. Izaro's last room is boss_2_end.
LAB_AREA = re.compile(r"^(1|2|3|EndGame)_Labyrinth_(.+)$")
LAB_NAMES = {"1": "Normal", "2": "Cruel", "3": "Merciless", "EndGame": "Eternal"}
CAMPAIGN_AREA = re.compile(r"^\d_(\d+)_")   # 1_3_5 = part 1, act 3, zone 5


def save_folder():
    folder = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "LeagueStartTracker")
    os.makedirs(folder, exist_ok=True)
    return folder


def new_run():
    return {
        "league": "",           # name shown in the window
        "league_key": None,     # the league from the date list (decides when a new run starts)
        "offset": 0,            # how far into Client.txt we've read
        "last_ts": None,        # time of the last log line
        "started": False,
        "paused": False,        # paused by you (break): no time is counted       # timer running (entered The Twilight Strand, or first level up)
        "character": None,      # league starter = first character to level up
        "level": 1,
        "deaths": 0,
        "others": [],           # party members (their level ups/deaths are ignored)
        "act": 1,
        "zone": "",             # where you are now (from the loading screen line)
        "area_level": 0,
        "campaign_time": 0.0,
        "atlas_time": 0.0,
        "campaign_splits": [],  # time at the end of each act
        "atlas_splits": [],     # atlas time at each voidstone
        "labs": {},             # "Normal": {"time": seconds, "done": True/False}
        "lab_now": None,        # the lab you're in right now
        "lab_final": False,     # in Izaro's last room (leaving it = lab done)
        "voidstone_order": [],  # which voidstone each atlas split was, in the order you got them
        "atlas_seen": [],       # boss arenas entered (voidstone objectives)
        "map_seeds": [],
        "best_tier": 0,
    }


def new_records():
    return {
        "campaign_pb": None, "atlas_pb": None,                 # split times of your best run
        "campaign_gold": [None] * 10, "atlas_gold": [None] * 4,  # best time for each segment
        "lab_best": {},                                          # best time for each lab
    }


class Tracker:
    def __init__(self, save_path=None):
        self.save_path = save_path or os.path.join(save_folder(), "save.json")
        self.run, self.records, self.log_path = new_run(), new_records(), None
        self.window = None        # window size/position, e.g. "420x700+100+50"
        if os.path.exists(self.save_path):
            with open(self.save_path, encoding="utf-8") as f:
                data = json.load(f)
            self.run.update(data.get("run", {}))
            self.records.update(data.get("records", {}))
            self.log_path = data.get("log_path")
            self.window = data.get("window")
            if data.get("version", 1) < 2:
                self._clear_bad_records()
        if self.run["character"] and not self.run["started"]:
            self.run["started"] = True   # save from before "started" existed
        if self.run["league"] and not self.run["league_key"]:
            self.run["league_key"] = self.run["league"]   # save from before league_key existed
        if not self.log_path or not os.path.exists(self.log_path):
            self.log_path = next((p for p in LOG_PATHS if os.path.exists(p)), None)
        if not self.run["league"] and self.run["offset"] == 0 and self.log_path:
            self.run["offset"] = os.path.getsize(self.log_path)   # first run: watch from now on

    def _clear_bad_records(self):
        """Saves from the first version have PB/golds built from reading the whole
        Client.txt history (e.g. a 41-hour Act 6). Throw those away and rebuild the
        golds from the run in progress, which was timed correctly."""
        self.records = new_records()
        for part in ("campaign", "atlas"):
            splits = self.run[f"{part}_splits"]
            for i, t in enumerate(splits):
                self.records[f"{part}_gold"][i] = t - (splits[i - 1] if i else 0)

    def save(self):
        temp = self.save_path + ".tmp"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump({"version": 2, "run": self.run, "records": self.records, "log_path": self.log_path,
                       "window": self.window}, f, indent=1)
        os.replace(temp, self.save_path)

    # ---------- where are we ----------

    def phase(self):
        if len(self.run["campaign_splits"]) < 10:
            return "campaign"
        if len(self.run["atlas_splits"]) < 4:
            return "atlas"
        return "done"

    def splits(self):
        """(names, split times, pb, golds) for the part being shown."""
        if self.phase() == "campaign":
            return CAMPAIGN, self.run["campaign_splits"], self.records["campaign_pb"], self.records["campaign_gold"]
        return ATLAS, self.run["atlas_splits"], self.records["atlas_pb"], self.records["atlas_gold"]

    def timer(self, now=None):
        """Time for the current part, ticking along between log lines."""
        phase = self.phase()
        if phase == "done":
            return self.run["atlas_splits"][-1]
        t = self.run["campaign_time"] if phase == "campaign" else self.run["atlas_time"]
        if self.run["started"] and self.run["last_ts"] and not self.run.get("paused"):
            gap = ((now or datetime.now()) - datetime.strptime(self.run["last_ts"], TIME_FORMAT)).total_seconds()
            if 0 < gap <= MAX_GAP:
                t += gap
        return t

    def total(self, now=None):
        if self.phase() == "campaign":
            return self.timer(now)
        return self.run["campaign_splits"][-1] + self.timer(now)

    # ---------- actions ----------

    def new_league(self, name):
        """Manual reset from the menu (e.g. a restart, or a name like "Covens of Umbra HC")."""
        self.run = new_run()
        self.run["league"] = name
        self.run["league_key"] = None   # taken from your next Twilight Strand (keeps your name)
        if self.log_path and os.path.exists(self.log_path):
            self.run["offset"] = os.path.getsize(self.log_path)   # skip old lines
        self.save()

    def _auto_new_run(self, league):
        """A new character entered The Twilight Strand in a different league: fresh run.
        Reading carries on from the same spot in the log; PBs and golds are kept."""
        old = self.run
        self.run = new_run()
        self.run["league"] = self.run["league_key"] = league
        self.run["offset"], self.run["last_ts"] = old["offset"], old["last_ts"]

    def set_log_path(self, path):
        self.log_path = path
        self.run["offset"] = os.path.getsize(path)
        self.save()

    def toggle_pause(self):
        self.run["paused"] = not self.run.get("paused")
        self.save()

    def got_voidstones(self):
        order = self.run.setdefault("voidstone_order", [])
        # older saves split "Voidstone 1, 2..." without a name: give them the first free ones
        for name in ATLAS:
            if len(order) >= len(self.run["atlas_splits"]):
                break
            if name not in order:
                order.append(name)
        return order

    def split_voidstone(self, name=None):
        """You got a voidstone (any order). name=None: the first one you don't have yet."""
        if self.phase() != "atlas":
            return
        got = self.got_voidstones()
        name = name or next(n for n in ATLAS if n not in got)
        if name in got:
            return
        got.append(name)
        self._split("atlas", self.run["atlas_time"])
        self.save()

    def undo_voidstone(self):
        if self.run["atlas_splits"] and len(self.run["campaign_splits"]) == 10:
            got = self.got_voidstones()
            self.run["atlas_splits"].pop()
            if got:
                got.pop()
            self.save()

    def objectives(self, name):
        """[(label, done, total), ...] for one voidstone."""
        seen = set(self.run.get("atlas_seen", []))
        for stone, objs in VOIDSTONES:
            if stone == name:
                return [(label, sum(a in seen for a in areas), len(areas)) for label, areas in objs]
        return []

    def _split(self, part, time):
        splits = self.run[f"{part}_splits"]
        segment = time - (splits[-1] if splits else 0)
        golds = self.records[f"{part}_gold"]
        i = len(splits)
        if golds[i] is None or segment < golds[i]:
            golds[i] = segment
        splits.append(time)
        # Finished this part: new PB if it's faster
        pb = self.records[f"{part}_pb"]
        if len(splits) == len(golds) and (pb is None or time < pb[-1]):
            self.records[f"{part}_pb"] = list(splits)

    def _track_lab(self, area):
        run = self.run
        m = LAB_AREA.match(area)
        if m:
            name = LAB_NAMES[m.group(1)]
            run["labs"].setdefault(name, {"time": 0.0, "done": False})
            run["lab_now"] = name
            run["lab_final"] = m.group(2).startswith("boss_2_end")
            return
        # Left the lab. Leaving Izaro's last room means you beat him.
        name = run.get("lab_now")
        if name and run.get("lab_final") and not run["labs"][name]["done"]:
            run["labs"][name]["done"] = True
            t = run["labs"][name]["time"]
            best = self.records["lab_best"].get(name)
            if best is None or t < best:
                self.records["lab_best"][name] = t
        run["lab_now"], run["lab_final"] = None, False

    def lab_time(self, name, now=None):
        """Time spent in a lab, ticking along while you're in it."""
        lab = self.run["labs"].get(name)
        if not lab:
            return None
        t = lab["time"]
        if self.run.get("lab_now") == name and not lab["done"] and not self.run.get("paused") and self.run["last_ts"]:
            gap = ((now or datetime.now()) - datetime.strptime(self.run["last_ts"], TIME_FORMAT)).total_seconds()
            if 0 < gap <= MAX_GAP:
                t += gap
        return t

    # ---------- reading the log ----------

    def poll(self):
        """Read new lines from Client.txt, at most CHUNK bytes at a time so the
        window never freezes. Returns True if there's more waiting to be read."""
        if not self.log_path or not os.path.exists(self.log_path):
            return False
        size = os.path.getsize(self.log_path)
        if size < self.run["offset"]:
            self.run["offset"] = 0     # the game started a fresh log
        if size == self.run["offset"]:
            return False
        with open(self.log_path, "rb") as f:
            f.seek(self.run["offset"])
            chunk = f.read(CHUNK)
        end = chunk.rfind(b"\n")       # only whole lines
        if end == -1:
            if len(chunk) == CHUNK:    # a giant broken line: skip it
                self.run["offset"] += CHUNK
                return True
            return False
        self.run["offset"] += end + 1
        for line in chunk[: end + 1].decode("utf-8", errors="ignore").splitlines():
            self.read_line(line)
        more = self.run["offset"] < size
        if not more:
            self.save()    # saving once caught up keeps each step quick
        return more

    def read_line(self, line):
        run = self.run
        try:
            ts = datetime.strptime(line[:19], TIME_FORMAT)
        except ValueError:
            return

        # played time since the last line goes to whichever part we're in
        if run["last_ts"] and run["started"]:
            gap = (ts - datetime.strptime(run["last_ts"], TIME_FORMAT)).total_seconds()
            if 0 < gap <= MAX_GAP and not run.get("paused"):
                lab = run["labs"].get(run.get("lab_now") or "")
                if lab and not lab["done"]:
                    lab["time"] += gap
                if self.phase() == "campaign":
                    run["campaign_time"] += gap
                elif self.phase() == "atlas":
                    run["atlas_time"] += gap
        run["last_ts"] = line[:19]

        m = JOINED.search(line)
        if m:
            if m.group(1) not in run["others"]:
                run["others"].append(m.group(1))
            return

        m = LEVEL_UP.search(line)
        if m and m.group(1) not in run["others"]:
            if run["character"] is None:
                run["character"] = m.group(1)   # the first character to level up is the league starter
                run["started"] = True           # backup start, if you never passed the Strand
                if not run["league_key"]:
                    run["league_key"] = leagues.league_at(ts)
                    run["league"] = run["league"] or run["league_key"]
            if m.group(1) == run["character"]:
                run["level"] = int(m.group(3))
            return

        m = DEATH.search(line)
        if m and m.group(1) == run["character"]:
            run["deaths"] += 1
            return

        m = LOADING.search(line)
        if m:
            run["zone"] = m.group(1)
            return

        m = GENERATING.search(line)
        if m:
            # Loading into The Twilight Strand (1_1_1) on a new character starts the timer,
            # and a new league (by date) starts a fresh run
            if m.group(2) == "1_1_1":
                league = leagues.league_at(ts)
                if run["league_key"] is None:          # first launch or a manual reset
                    run["league_key"] = league
                    run["league"] = run["league"] or league
                elif league != run["league_key"]:      # a new league has started
                    self._auto_new_run(league)
                    run = self.run
                run["started"] = True
            run["area_level"] = int(m.group(1))
            if run["started"]:
                self._entered_area(m.group(2), int(m.group(1)), m.group(3))

    def _entered_area(self, area, level, seed):
        run = self.run
        self._track_lab(area)
        if area in OBJECTIVE_AREAS and area not in run.setdefault("atlas_seen", []):
            run["atlas_seen"].append(area)
        is_map = area.startswith("MapWorlds") and level >= 68

        if self.phase() == "campaign":
            act_match = CAMPAIGN_AREA.match(area)
            act = int(act_match.group(1)) if act_match else None
            if act == run["act"] + 1 and act <= 10:
                self._split("campaign", run["campaign_time"])
                run["act"] = act
            elif run["act"] == 10 and (act == 11 or is_map):   # epilogue or first map = Act 10 done
                self._split("campaign", run["campaign_time"])

        if self.phase() == "atlas" and is_map and seed not in run["map_seeds"]:
            run["map_seeds"].append(seed)
            run["best_tier"] = max(run["best_tier"], min(level - 67, 16))
