# League Start Tracker (PoE1)

A LiveSplit-style timer for a Path of Exile league start. It reads the game's `Client.txt` while you play.

> **Disclaimer:** an unofficial, fan-made tool. Not affiliated with, endorsed by, or sponsored by
> Grinding Gear Games. Path of Exile and all related names are trademarks of Grinding Gear Games.

## Install
1. Download **League-Start-Tracker-Setup.exe** from the
   [latest release](https://github.com/klovnary/poe1-leaguestart/releases/latest) and run it.
   SmartScreen warns the first time (the installer isn't signed): *More info → Run anyway*.
2. It installs for your user only (no admin) into `%LOCALAPPDATA%\Programs\League Start Tracker`,
   with its own copy of Python, and adds it to the Start menu.
3. It updates itself: when **Update ready - click to restart** shows at the bottom, click it.
   Only changed files are downloaded.

Uninstall from Windows Settings → Apps. Your times in `%LOCALAPPDATA%\LeagueStartTracker` are kept.

## Using it
- **Campaign:** Act 1-10 split by themselves when you enter the next act. Act 10 ends at the
  Epilogue or your first map.
- **Atlas:** then it switches to Voidstone 1-4. Click the highlighted voidstone (or press Space)
  when you get one. Shows maps run, highest tier and total time.
- Compares against your **PB** (+/-, green/red), **golds** for best segments, Previous Segment and
  Sum of Best, like LiveSplit.
- The timer starts at your first level up and follows that character. Gaps over 5 minutes in the
  log (AFK, game closed) don't count.

Right-click the window for: split / undo voidstone, New league, Find Client.txt, Always on top.

## Development
- Run from source: `run.bat` (or `python main.py`). Tests: `python -m unittest discover tests`.
- **Release:** push a tag like `v0.2.0` (or Actions → *Build installer* → Run workflow with
  *publish* ticked). GitHub builds `League-Start-Tracker-Setup.exe` and publishes it as a release.
- Build the installer yourself: Python 3.13 + Inno Setup 6, then `pwsh installer\build.ps1 -Version 0.2.0`.

Files: `main.py` (window), `tracker.py` (log reading, splits, saving), `updater.py` (updates from
GitHub), `installer/` (launcher, Inno Setup script, build script).
