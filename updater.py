"""Updates from GitHub, like Path of Building: an installed copy asks GitHub for
the newest version, downloads only the files that changed, and swaps them in
when you restart.

Only an installed copy updates (its folder has version.json, written by the
installer). Running from the source code does nothing here; use git for that.
The repository has to be public for this to work.
"""
import hashlib
import json
import os
import sys
import subprocess
import threading
import urllib.request

REPO = "klovnary/poe1-leaguestart"
BRANCH = "main"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(APP_DIR, "version.json")


def installed_copy():
    return os.path.exists(VERSION_FILE)


def get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "league-start-tracker"})
    with urllib.request.urlopen(request, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "league-start-tracker"})
    with urllib.request.urlopen(request, timeout=60) as r:
        return r.read()


def blob_sha(data):
    """The fingerprint GitHub gives every file (git's blob hash)."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def is_app_file(path):
    """Files that make up the app: the .py files in the top folder."""
    return "/" not in path and path.endswith(".py")


class Updater:
    def __init__(self):
        self.status = ""          # what to show in the window
        self.ready = False        # files are downloaded; restart to use them

    def check_in_background(self):
        if installed_copy():
            threading.Thread(target=self._update, daemon=True).start()

    def _update(self):
        try:
            with open(VERSION_FILE, encoding="utf-8-sig") as f:
                version = json.load(f)
            newest = get_json(f"https://api.github.com/repos/{REPO}/commits/{BRANCH}")["sha"]
            if newest == version.get("commit"):
                return

            tree = get_json(f"https://api.github.com/repos/{REPO}/git/trees/{newest}")["tree"]
            changed = []
            for item in tree:
                if item["type"] != "blob" or not is_app_file(item["path"]):
                    continue
                local = os.path.join(APP_DIR, item["path"])
                if os.path.exists(local):
                    with open(local, "rb") as f:
                        if blob_sha(f.read()) == item["sha"]:
                            continue
                changed.append(item)

            # Download everything first, then swap, so a failed download changes nothing
            new_files = {}
            for item in changed:
                data = download(f"https://raw.githubusercontent.com/{REPO}/{newest}/{item['path']}")
                if blob_sha(data) != item["sha"]:
                    raise ValueError(f"{item['path']} didn't download correctly")
                new_files[item["path"]] = data
            for path, data in new_files.items():
                temp = os.path.join(APP_DIR, path + ".new")
                with open(temp, "wb") as f:
                    f.write(data)
                os.replace(temp, os.path.join(APP_DIR, path))

            version["commit"] = newest
            with open(VERSION_FILE, "w", encoding="utf-8") as f:
                json.dump(version, f, indent=2)
            if new_files:
                self.status = "Update ready - click to restart"
                self.ready = True
        except Exception:
            self.status = ""      # offline, GitHub busy, private repo... try again next start


def restart():
    """Start the app again (the window closes itself after calling this)."""
    subprocess.Popen([sys.executable, os.path.join(APP_DIR, "main.py")], cwd=APP_DIR)
