import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

import notifier
import csv_writer

REMOTE_NAME  = "mega-sync"
RCLONE_CONF  = Path.home() / "Documents" / "mega-sync" / "rclone.conf"
EXCLUDE_DIRS = ["$RECYCLE.BIN/**", "System Volume Information/**", "autorun.inf/**"]


class SyncManager:
    def __init__(self, config, on_progress=None, on_log=None,
                 on_complete=None, on_mega_connected=None):
        self.config             = config
        self.on_progress        = on_progress
        self.on_log             = on_log
        self.on_complete        = on_complete
        self.on_mega_connected  = on_mega_connected

        self._stop_event    = threading.Event()
        self._process       = None
        self._uploaded_files = []   # liste des fichiers uploades avec succes

    # ------------------------------------------------------------------ helpers
    def log(self, msg):
        if self.on_log:
            self.on_log(msg)

    # ------------------------------------------------------------------ setup
    def _ensure_rclone(self):
        if shutil.which("rclone"):
            return
        self.log("Installation de rclone (Homebrew)...")
        r = subprocess.run(["brew", "install", "rclone"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("Impossible d'installer rclone.\n"
                               "Installez-le manuellement : brew install rclone")
        self.log("rclone installe")

    def _write_config(self):
        r = subprocess.run(["rclone", "obscure", self.config["mega_password"]],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("Erreur chiffrement mot de passe MEGA")
        obscured = r.stdout.strip()
        RCLONE_CONF.write_text(
            f"[{REMOTE_NAME}]\ntype = mega\n"
            f"user = {self.config['mega_email']}\n"
            f"pass = {obscured}\n"
        )

    # ------------------------------------------------------------------ main loop
    def run(self):
        try:
            self._ensure_rclone()
            self._write_config()
            self.log("Configuration MEGA enregistree - demarrage de la synchronisation...")
            if self.on_mega_connected:
                self.on_mega_connected()

            source = self.config["source_path"]
            dest   = f"{REMOTE_NAME}:{self.config['mega_dest_folder']}"

            cmd = [
                "rclone", "sync", source, dest,
                "--config",          str(RCLONE_CONF),
                "--use-json-log",
                "--log-level",       "INFO",
                "--stats",           "2s",
                "--transfers",       "1",
                "--retries",         "10",
                "--retries-sleep",   "5s",
                "--no-update-modtime",
            ]
            for pat in EXCLUDE_DIRS:
                cmd += ["--exclude", pat]

            self.log(f"Synchronisation : {source}  ->  MEGA/{self.config['mega_dest_folder']}")

            self._process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )

            transferred = 0
            total       = 0
            current     = ""

            for raw in self._process.stdout:
                if self._stop_event.is_set():
                    self._process.terminate()
                    self.log("Arrete - la progression est sauvegardee sur MEGA")
                    break

                raw = raw.strip()
                if not raw:
                    continue

                try:
                    data  = json.loads(raw)
                    msg   = data.get("msg", "")
                    level = data.get("level", "")

                    # File copied / updated
                    if re.search(r":\s+(Copied|Updated|Moved|Deleted)\s*\(", msg):
                        transferred += 1
                        fname = re.sub(r":\s+(Copied|Updated|Moved|Deleted).*", "", msg).strip()
                        current = fname
                        self._uploaded_files.append(fname)
                        self.log(f"OK  {fname}")
                        if self.on_progress and total > 0:
                            self.on_progress(fname, transferred, total)

                    # Stats block (may contain multiple lines in one msg)
                    elif "Transferred:" in msg:
                        m = re.search(r"Transferred:\s+(\d+)\s*/\s*(\d+)", msg)
                        if m:
                            transferred = int(m.group(1))
                            total       = int(m.group(2))
                            if self.on_progress:
                                self.on_progress(current, transferred, total)

                    elif level in ("error", "warning") and msg:
                        self.log(f"[{level.upper()}] {msg}")

                except (json.JSONDecodeError, ValueError):
                    if raw:
                        self.log(raw)

            exit_code = self._process.wait()

            if not self._stop_event.is_set():
                if exit_code == 0:
                    self.log(f"Upload termine : {transferred} fichier(s) uploade(s)")
                    # --- Generation des liens et CSV ---
                    if self._uploaded_files:
                        self.log(f"Generation des liens MEGA et CSV en cours...")
                        csv_paths = csv_writer.generate_links_and_csv(
                            uploaded_files=self._uploaded_files,
                            dest_folder=self.config["mega_dest_folder"],
                            on_log=self.log,
                            on_progress=self.on_progress,
                            stop_event=self._stop_event,
                        )
                        self.log(f"{len(csv_paths)} CSV genere(s) dans : ~/Documents/mega-sync/exports/")
                        notifier.notify(
                            "MEGA Sync termine",
                            f"{transferred} fichiers uploades, {len(csv_paths)} CSV generes"
                        )
                    else:
                        notifier.notify("MEGA Sync termine",
                                        f"{transferred} fichier(s) synchronise(s)")
                    if self.on_complete:
                        self.on_complete({"transferred": transferred,
                                          "total": total, "ok": True})
                else:
                    self.log(f"Termine avec des erreurs (code {exit_code}). "
                             "Relancez pour reprendre.")
                    if self.on_complete:
                        self.on_complete({"transferred": transferred,
                                          "total": total, "ok": False})

        except Exception as exc:
            self.log(f"ERREUR : {exc}")
            if self.on_complete:
                self.on_complete({"transferred": 0, "total": 0, "ok": False})

    # ------------------------------------------------------------------ controls
    def stop(self):
        self._stop_event.set()
        if self._process:
            self._process.terminate()
