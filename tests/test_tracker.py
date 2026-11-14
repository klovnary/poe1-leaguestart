"""python -m unittest discover tests"""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tracker import Tracker


def line(t, msg, day="2026/12/01"):
    return f"{day} {t} 1 a [INFO Client 1] {msg}\n"


def area(t, level, area_id, seed, day="2026/12/01"):
    return line(t, f'Generating level {level} area "{area_id}" with seed {seed}', day)


class TrackerTest(unittest.TestCase):
    def setUp(self):
        folder = tempfile.mkdtemp()
        self.log = os.path.join(folder, "Client.txt")
        open(self.log, "w").close()
        self.t = Tracker(os.path.join(folder, "save.json"))
        self.t.set_log_path(self.log)
        self.t.new_league("Test")

    def write(self, *lines):
        with open(self.log, "a") as f:
            f.writelines(lines)
        self.t.poll()

    def play_campaign(self, step=2):
        lines = [area("10:00:00", 1, "1_1_1", 1), line("10:00:30", ": Rags (Duelist) is now level 2"),
                 line("10:00:40", ": Pal has joined the area."), line("10:00:50", ": Pal (Witch) is now level 9")]
        minute = 0
        for act in range(2, 11):
            minute += step
            lines.append(area(f"10:{minute:02d}:30", 30, f"{1 if act < 6 else 2}_{act}_1", act))
        lines.append(area(f"10:{minute + step:02d}:30", 68, "2_11_town", 99))
        self.write(*lines)

    def test_campaign_then_atlas(self):
        self.play_campaign()
        r = self.t.run
        self.assertEqual(r["character"], "Rags")
        self.assertEqual(r["level"], 2)                       # Pal's level up ignored
        self.assertEqual(len(r["campaign_splits"]), 10)
        self.assertEqual(r["campaign_splits"][0], 150)        # Strand 10:00:00 -> 10:02:30
        self.assertEqual(self.t.phase(), "atlas")
        self.assertEqual(self.t.records["campaign_pb"][-1], 1230)

        self.write(area("10:21:00", 68, "MapWorldsStrand", 5), area("10:22:00", 68, "MapWorldsStrand", 5),
                   area("10:25:00", 83, "MapWorldsCrater", 6), line("11:30:00", ": x"))   # AFK gap
        self.assertEqual(len(r["map_seeds"]), 2)
        self.assertEqual(r["best_tier"], 16)
        self.assertEqual(r["atlas_time"], 270)               # 10:20:30 -> 10:25:00
        for _ in range(4):
            self.t.split_voidstone()
        self.assertEqual(self.t.phase(), "done")
        self.assertEqual(self.t.records["atlas_pb"], [270] * 4)

    def test_faster_run_beats_pb_and_restart_keeps_state(self):
        self.play_campaign(step=3)
        slow = self.t.records["campaign_pb"][-1]
        self.t.new_league("Again")
        self.play_campaign(step=2)
        self.assertLess(self.t.records["campaign_pb"][-1], slow)
        again = Tracker(self.t.save_path)                     # app restarted
        self.assertEqual(again.run["league"], "Again")
        self.assertEqual(again.phase(), "atlas")

    def test_timer_ticks_between_lines(self):
        self.write(line("10:00:00", ": Rags (Duelist) is now level 2"))
        self.assertEqual(self.t.timer(datetime(2026, 12, 1, 10, 0, 45)), 45)
        self.assertEqual(self.t.timer(datetime(2026, 12, 1, 10, 30, 0)), 0)   # AFK

    def test_first_launch_ignores_old_log_lines(self):
        with open(self.log, "a") as f:
            f.write(area("09:00:00", 1, "1_1_1", 1))           # from before the tracker existed
        save = os.path.join(os.path.dirname(self.log), "fresh.json")
        with open(save, "w") as f:                             # only the log path known so far
            json.dump({"log_path": self.log}, f)
        fresh = Tracker(save)
        self.assertEqual(fresh.run["offset"], os.path.getsize(self.log))
        fresh.poll()
        self.assertFalse(fresh.run["started"])

    def test_league_comes_from_the_date(self):
        aug, dec = "2026/08/01", "2026/12/01"
        self.t.run["league"], self.t.run["league_key"] = "", None   # like a first launch
        self.write(area("10:00:00", 1, "1_1_1", 1, aug), line("10:00:30", ": Rags (Duelist) is now level 2", aug),
                   area("10:02:00", 12, "1_2_1", 2, aug))
        self.assertEqual(self.t.run["league"], "Curse of the Allflame")
        self.assertEqual(len(self.t.run["campaign_splits"]), 1)
        # an alt in the same league doesn't reset the run
        self.write(area("11:00:00", 1, "1_1_1", 3, aug), line("11:00:30", ": Alt (Witch) is now level 2", aug))
        self.assertEqual(self.t.run["character"], "Rags")
        self.assertEqual(len(self.t.run["campaign_splits"]), 1)
        # a new character after Covens of Umbra launched starts a fresh run, PB/golds kept
        gold = self.t.records["campaign_gold"][0]
        self.write(area("10:00:00", 1, "1_1_1", 4, dec), line("10:00:30", ": Fresh (Ranger) is now level 2", dec))
        self.assertEqual(self.t.run["league"], "Covens of Umbra")
        self.assertEqual(self.t.run["character"], "Fresh")
        self.assertEqual(self.t.run["campaign_splits"], [])
        self.assertEqual(self.t.records["campaign_gold"][0], gold)

    def test_big_log_is_read_in_small_steps(self):
        import tracker
        old = tracker.CHUNK
        tracker.CHUNK = 200
        try:
            lines = [line("10:00:00", ": Rags (Duelist) is now level 2")]
            lines += [line(f"10:00:{s:02d}", ": filler") for s in range(1, 40)]
            with open(self.log, "a") as f:
                f.writelines(lines)
            steps = 1
            while self.t.poll():
                steps += 1
            self.assertGreater(steps, 5)
            self.assertEqual(self.t.run["offset"], os.path.getsize(self.log))
            self.assertEqual(self.t.timer(datetime(2026, 12, 1, 10, 0, 39)), 39)
        finally:
            tracker.CHUNK = old

    def test_timer_starts_at_the_twilight_strand(self):
        self.write(line("09:59:00", ": waiting on character select"),
                   area("10:00:00", 1, "1_1_1", 1),
                   line("10:00:40", ": Rags (Duelist) is now level 2"),
                   area("10:03:00", 12, "1_2_1", 2))
        self.assertTrue(self.t.run["started"])
        self.assertEqual(self.t.run["character"], "Rags")
        self.assertEqual(self.t.run["campaign_splits"], [180])   # 10:00:00 -> 10:03:00

    def test_existing_character_starts_at_first_level_up(self):
        self.write(area("10:00:00", 40, "1_5_1", 1), line("10:01:00", ": Rags (Duelist) is now level 41"))
        self.assertTrue(self.t.run["started"])
        self.assertEqual(self.t.run["campaign_time"], 0)

    def test_manual_reset_keeps_custom_name(self):
        self.t.new_league("Covens of Umbra HC")               # e.g. done before launch
        self.write(area("10:00:00", 1, "1_1_1", 1), line("10:00:30", ": Rags (Duelist) is now level 2"))
        self.assertEqual(self.t.run["league"], "Covens of Umbra HC")
        self.assertEqual(self.t.run["league_key"], "Covens of Umbra")
        self.assertEqual(self.t.run["character"], "Rags")

    def test_pause_stops_the_clock(self):
        self.write(area("10:00:00", 1, "1_1_1", 1), line("10:01:00", ": x"))
        self.t.toggle_pause()
        self.write(line("10:02:00", ": x"), line("10:03:00", ": x"))
        self.assertEqual(self.t.timer(datetime(2026, 12, 1, 10, 3, 30)), 60)   # frozen
        self.t.toggle_pause()
        self.write(line("10:04:00", ": x"))
        self.assertEqual(self.t.run["campaign_time"], 120)

    def test_labyrinth(self):
        self.write(area("10:00:00", 1, "1_1_1", 1),
                   area("11:00:00", 33, "Labyrinth_Airlock", 2),           # Aspirants' Plaza: not timed
                   area("11:01:00", 33, "1_Labyrinth_OH_straight", 3),
                   area("11:04:00", 33, "1_Labyrinth_boss_1", 4),
                   area("11:05:00", 33, "Labyrinth_Airlock", 5))           # died / left early
        lab = self.t.run["labs"]["Normal"]
        self.assertFalse(lab["done"])
        self.assertEqual(lab["time"], 240)
        self.write(area("11:10:00", 33, "1_Labyrinth_OH_straight", 6),
                   area("11:14:00", 33, "1_Labyrinth_boss_2_end", 7),
                   area("11:16:00", 13, "1_3_town", 8))                    # left Izaro's last room = done
        self.assertTrue(lab["done"])
        self.assertEqual(lab["time"], 240 + 360)
        self.assertEqual(self.t.records["lab_best"]["Normal"], 600)
        self.assertIsNone(self.t.run["lab_now"])
        # time after finishing doesn't add to it
        self.write(area("11:20:00", 13, "1_3_1", 9))
        self.assertEqual(lab["time"], 600)

    def test_voidstone_objectives_and_any_order(self):
        self.play_campaign()
        self.write(area("10:30:00", 79, "MapWorldsPrimordialBoss1", 10),
                   area("10:40:00", 83, "MapWorldsPrimordialBoss3", 11),
                   area("10:50:00", 83, "MavenHub", 12))
        objs = dict((label, (d, total)) for label, d, total in self.t.objectives("Eldritch"))
        self.assertEqual(objs["Star & Hunger"], (1, 2))
        self.assertEqual(objs["Exarch"], (1, 1))
        self.assertEqual(objs["Eater"], (0, 1))
        self.t.split_voidstone("Ceremonial")                  # got the Maven one first
        self.t.split_voidstone("Ceremonial")                  # clicking again does nothing
        self.assertEqual(self.t.got_voidstones(), ["Ceremonial"])
        self.assertEqual(len(self.t.run["atlas_splits"]), 1)
        self.t.undo_voidstone()
        self.assertEqual(self.t.got_voidstones(), [])

    def test_start_timer_by_hand(self):
        self.t.new_league("Reroll")
        self.t.start_now()
        self.assertTrue(self.t.run["started"])
        self.assertTrue(self.t.run["league_key"])
        self.assertEqual(self.t.run["league"], "Reroll")

    def test_zones_in_the_current_act(self):
        load = lambda t, name: line(t, f"[LOADING SCREEN] ({name}) Duration: 1200ms")
        self.write(area("10:00:00", 1, "1_1_1", 1), load("10:00:02", "The Twilight Strand"),
                   area("10:03:00", 2, "1_1_town", 2), load("10:03:02", "Lioneye's Watch"),
                   area("10:04:00", 3, "1_1_2", 3), load("10:04:02", "The Coast"),
                   area("10:07:00", 2, "1_1_town", 4), line("10:08:00", ": x"))
        rows = self.t.zone_times(datetime(2026, 12, 1, 10, 8, 30))
        by_name = {r[0]: r for r in rows}
        # every zone of the act is listed, in the usual order
        self.assertEqual([r[0] for r in rows[:4]],
                         ["The Twilight Strand", "Lioneye's Watch", "The Coast", "The Mud Flats"])
        self.assertNotIn("The Fetid Pool", by_name)                        # optional, not visited
        self.assertEqual(by_name["The Twilight Strand"][1:], (180, 180, False, True))
        self.assertEqual(by_name["The Coast"][1:], (180, 420, False, True))   # left at 7:00 into the act
        self.assertEqual(by_name["Lioneye's Watch"][1:3], (150, None))       # here now, ticking
        self.assertTrue(by_name["Lioneye's Watch"][3])
        self.assertEqual(by_name["The Mud Flats"][1:], (None, None, False, False))   # not yet
        # next act: act 1's zones are kept, the list starts over
        self.write(area("10:10:00", 13, "1_2_1", 5), load("10:10:02", "The Southern Forest"))
        self.assertEqual(len(self.t.run["act_history"]["1"]), 3)
        self.assertEqual(self.t.run["act_started_ts"], "2026/12/01 10:10:00")
        self.assertTrue(self.t.zone_times()[0][3])                         # Southern Forest, here

    def test_backfill_after_update_and_na_before_the_timer(self):
        load = lambda t, name: line(t, f"[LOADING SCREEN] ({name}) Duration: 1200ms")
        with open(self.log, "a") as f:     # played before the tracker knew about this run
            f.writelines([area("09:00:00", 1, "1_1_1", 1), area("09:02:00", 2, "1_1_town", 2),
                          area("09:05:00", 3, "1_1_2", 3), load("09:05:01", "The Coast"),
                          area("09:08:00", 4, "1_1_3", 4), line("09:09:00", ": x")])
        save = self.t.save_path
        # timer started by hand at 09:04, the zones themselves weren't recorded
        self.t.run.update(started=True, offset=os.path.getsize(self.log), last_ts="2026/12/01 09:09:00",
                          act_started_ts="2026/12/01 09:04:00", campaign_time=300.0, act_zones=[], zone_now=None)
        self.t.save()
        again = Tracker(save)
        rows = {r[0]: r for r in again.zone_times(datetime(2026, 12, 1, 9, 9, 0))}
        self.assertEqual(rows["The Twilight Strand"][1:], (None, None, False, True))   # N/A
        self.assertEqual(rows["Lioneye's Watch"][1:3], (60, 60))     # 09:04 -> 09:05 counted
        self.assertEqual(rows["The Coast"][1:3], (180, 240))
        self.assertTrue(rows["The Mud Flats"][3])

    def test_rebuild_league_ignores_a_later_reroll(self):
        lines = [area("10:00:00", 1, "1_1_1", 1)]
        m = 0
        for act in range(2, 11):
            m += 2
            lines.append(area(f"10:{m:02d}:00", 30, f"{1 if act < 6 else 2}_{act}_1", act))
        lines += [area("10:22:00", 68, "2_11_town", 50),
                  area("10:23:00", 68, "MapWorldsPit", 60), line("10:26:00", ": x"),
                  area("10:27:00", 1, "1_1_1", 70), line("10:30:00", ": x"),       # reroll: Act 1
                  area("10:31:00", 2, "1_1_town", 71), line("10:33:00", ": x"),
                  area("10:34:00", 68, "MapWorldsMarshes", 80), line("10:36:00", ": x")]
        with open(self.log, "a") as f:
            f.writelines(lines)
        self.t.run["league_key"] = "Covens of Umbra"
        import leagues
        old = leagues.LEAGUES
        leagues.LEAGUES = old + [("Test League", "2026-11-30 00:00")]   # before the fake log in any time zone
        try:
            self.t.run["league_key"] = "Test League"
            self.t.rebuild_league()
        finally:
            leagues.LEAGUES = old
        r = self.t.run
        self.assertEqual(len(r["campaign_splits"]), 10)
        self.assertEqual(r["campaign_splits"][0], 120)
        self.assertEqual(len(r["map_seeds"]), 2)
        # atlas: 10:22-10:27 (5 min, not the reroll's Act 1 zones) + 10:34-10:36
        self.assertEqual(r["atlas_time"], 300 + 120)
        self.assertIsNotNone(self.t.previous_run)


if __name__ == "__main__":
    unittest.main()
