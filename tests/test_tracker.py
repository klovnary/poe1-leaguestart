"""python -m unittest discover tests"""
import os
import sys
import tempfile
import unittest
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tracker import Tracker


def line(t, msg):
    return f"2026/12/01 {t} 1 a [INFO Client 1] {msg}\n"


def area(t, level, area_id, seed):
    return line(t, f'Generating level {level} area "{area_id}" with seed {seed}')


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
        self.assertEqual(r["campaign_splits"][0], 120)        # 10:00:30 -> 10:02:30
        self.assertEqual(self.t.phase(), "atlas")
        self.assertEqual(self.t.records["campaign_pb"][-1], 1200)

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

    def test_no_reading_before_a_league(self):
        self.t.run["league"] = ""
        self.write(line("10:00:00", ": Rags (Duelist) is now level 2"))
        self.assertIsNone(self.t.run["character"])

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


if __name__ == "__main__":
    unittest.main()
