import os
import queue
import threading
from pathlib import Path

import customtkinter as ctk

from config import load_config, save_config
from sync import SyncManager

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

SKIP_DIRS = {"$RECYCLE.BIN", "System Volume Information", "autorun.inf", "__pycache__"}


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, parent, config, on_save):
        super().__init__(parent)
        self.title("Parametres")
        self.geometry("460x340")
        self.resizable(False, False)
        self.grab_set()
        self.on_save = on_save
        self.cfg = config.copy()

        fields = [
            ("Email MEGA",                    "mega_email",       False),
            ("Mot de passe MEGA",             "mega_password",    True),
            ("Dossier source (disque)",       "source_path",      False),
            ("Dossier destination sur MEGA",  "mega_dest_folder", False),
        ]
        self._vars = {}
        for label, key, secret in fields:
            ctk.CTkLabel(self, text=label, font=ctk.CTkFont(size=13)).pack(
                anchor="w", padx=30, pady=(10, 0))
            var = ctk.StringVar(value=config.get(key, ""))
            self._vars[key] = var
            ctk.CTkEntry(self, textvariable=var, width=400,
                         show="*" if secret else "").pack(padx=30)

        ctk.CTkButton(self, text="Enregistrer", width=160,
                      command=self._save).pack(pady=20)

    def _save(self):
        for key, var in self._vars.items():
            self.cfg[key] = var.get().strip()
        self.on_save(self.cfg)
        self.destroy()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MEGA Sync")
        self.geometry("700x780")
        self.resizable(False, False)

        self.config_data   = load_config()
        self.sync_manager  = None
        self.sync_thread   = None
        self._queue        = queue.Queue()
        self._paused       = False
        self._running      = False
        self._folder_vars  = {}   # folder_name -> BooleanVar

        self._build_ui()
        self._check_disk()
        self._poll()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        ctk.CTkLabel(self, text="MEGA Sync",
                     font=ctk.CTkFont(size=26, weight="bold")).pack(pady=(16, 2))
        ctk.CTkLabel(self, text="Synchronisation intelligente  Disque  ->  MEGA",
                     font=ctk.CTkFont(size=12), text_color="gray").pack()

        # Status row
        sf = ctk.CTkFrame(self)
        sf.pack(fill="x", padx=20, pady=10)
        self.disk_lbl = ctk.CTkLabel(sf, text="Disque : detection...",
                                     font=ctk.CTkFont(size=13))
        self.disk_lbl.pack(side="left", padx=16, pady=8)
        self.mega_lbl = ctk.CTkLabel(sf, text="MEGA : non connecte",
                                     font=ctk.CTkFont(size=13))
        self.mega_lbl.pack(side="right", padx=16, pady=8)

        # ---- Folder selector ----
        folder_header = ctk.CTkFrame(self, fg_color="transparent")
        folder_header.pack(fill="x", padx=20, pady=(6, 2))

        ctk.CTkLabel(folder_header, text="Dossiers a synchroniser",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")

        ctk.CTkButton(folder_header, text="Tout", width=60, height=26,
                      command=self._select_all).pack(side="right", padx=(4, 0))
        ctk.CTkButton(folder_header, text="Aucun", width=60, height=26,
                      fg_color="gray30", hover_color="gray20",
                      command=self._select_none).pack(side="right", padx=4)

        self.folder_frame = ctk.CTkScrollableFrame(self, height=180)
        self.folder_frame.pack(fill="x", padx=20, pady=(0, 8))

        self.folder_placeholder = ctk.CTkLabel(
            self.folder_frame,
            text="Branchez le disque pour voir les dossiers...",
            text_color="gray", font=ctk.CTkFont(size=12))
        self.folder_placeholder.pack(pady=20)

        # Stats
        sf2 = ctk.CTkFrame(self)
        sf2.pack(fill="x", padx=20, pady=4)
        self.stats_lbl = ctk.CTkLabel(sf2, text="0 / 0 fichiers synchronises",
                                      font=ctk.CTkFont(size=13, weight="bold"))
        self.stats_lbl.pack(pady=8)

        # Progress
        pf = ctk.CTkFrame(self)
        pf.pack(fill="x", padx=20, pady=4)
        self.pbar = ctk.CTkProgressBar(pf, width=640)
        self.pbar.pack(pady=(10, 6), padx=16)
        self.pbar.set(0)
        self.file_lbl = ctk.CTkLabel(pf, text="En attente...",
                                     font=ctk.CTkFont(size=11), text_color="gray",
                                     wraplength=640)
        self.file_lbl.pack(pady=(0, 10))

        # Buttons
        bf = ctk.CTkFrame(self, fg_color="transparent")
        bf.pack(pady=10)

        self.btn_start = ctk.CTkButton(
            bf, text="DEMARRER", width=155, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#2E7D32", hover_color="#1B5E20",
            command=self._on_start)
        self.btn_start.grid(row=0, column=0, padx=8)

        self.btn_pause = ctk.CTkButton(
            bf, text="PAUSE", width=130, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#E65100", hover_color="#BF360C",
            state="disabled", command=self._on_pause)
        self.btn_pause.grid(row=0, column=1, padx=8)

        self.btn_stop = ctk.CTkButton(
            bf, text="STOP", width=110, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#B71C1C", hover_color="#7F0000",
            state="disabled", command=self._on_stop)
        self.btn_stop.grid(row=0, column=2, padx=8)

        ctk.CTkButton(bf, text="Parametres", width=120, height=40,
                      command=self._open_settings).grid(row=0, column=3, padx=8)

        # Log
        ctk.CTkLabel(self, text="Journal d'activite",
                     font=ctk.CTkFont(size=12)).pack(anchor="w", padx=22)
        self.log_box = ctk.CTkTextbox(
            self, height=160, font=ctk.CTkFont(size=11, family="Courier New"))
        self.log_box.pack(fill="both", expand=True, padx=20, pady=(4, 16))
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------ folder browser
    def _scan_folders(self, source_path):
        """Scanne les dossiers de premier niveau du disque (thread background)."""
        src = Path(source_path)
        folders = []
        try:
            for item in sorted(src.iterdir()):
                if item.is_dir() and item.name not in SKIP_DIRS:
                    folders.append(item.name)
        except PermissionError:
            pass
        self._queue.put({"action": "folders_loaded", "folders": folders})

    def _populate_folders(self, folders):
        """Affiche les checkboxes dans le folder_frame."""
        # Vider le frame
        for w in self.folder_frame.winfo_children():
            w.destroy()
        self._folder_vars.clear()

        if not folders:
            ctk.CTkLabel(self.folder_frame,
                         text="Aucun dossier trouve (verifiez les permissions disque)",
                         text_color="orange").pack(pady=10)
            return

        # Grille 2 colonnes
        for i, name in enumerate(folders):
            var = ctk.BooleanVar(value=True)
            self._folder_vars[name] = var
            cb = ctk.CTkCheckBox(
                self.folder_frame, text=name, variable=var,
                font=ctk.CTkFont(size=12), checkbox_width=18, checkbox_height=18)
            cb.grid(row=i // 2, column=i % 2, sticky="w", padx=12, pady=3)

    def _select_all(self):
        for var in self._folder_vars.values():
            var.set(True)

    def _select_none(self):
        for var in self._folder_vars.values():
            var.set(False)

    def _get_selected_folders(self):
        selected = [name for name, var in self._folder_vars.items() if var.get()]
        # Si tout est selectionne ou rien de selectionne -> sync complet
        if not selected or len(selected) == len(self._folder_vars):
            return None
        return selected

    # ------------------------------------------------------------------ helpers
    def _check_disk(self):
        src = Path(self.config_data["source_path"])
        if src.exists():
            self.disk_lbl.configure(text=f"Disque : detecte")
            # Scan des dossiers en arriere-plan
            threading.Thread(
                target=self._scan_folders,
                args=(self.config_data["source_path"],),
                daemon=True
            ).start()
        else:
            self.disk_lbl.configure(text="Disque : non detecte")

    def _append_log(self, msg):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    # ------------------------------------------------------------------ queue poll
    def _poll(self):
        try:
            while True:
                ev = self._queue.get_nowait()
                act = ev["action"]
                if act == "log":
                    self._append_log(ev["msg"])
                elif act == "progress":
                    self._update_progress(ev["file"], ev["done"], ev["total"])
                elif act == "mega_ok":
                    self.mega_lbl.configure(text="MEGA : connecte")
                elif act == "complete":
                    self._on_complete(ev["data"])
                elif act == "folders_loaded":
                    self._populate_folders(ev["folders"])
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def _update_progress(self, fname, done, total):
        if total > 0:
            pct = int(done / total * 100)
            self.pbar.set(done / total)
            self.stats_lbl.configure(
                text=f"{done} / {total} fichiers synchronises  ({pct}%)")
        if fname:
            short = fname if len(fname) < 85 else "..." + fname[-82:]
            self.file_lbl.configure(text=f"Upload : {short}")

    def _on_complete(self, data):
        self._running = False
        self._paused  = False
        self.btn_start.configure(state="normal", text="DEMARRER")
        self.btn_pause.configure(state="disabled", text="PAUSE")
        self.btn_stop.configure(state="disabled")
        self.file_lbl.configure(
            text="Termine !" if data.get("ok") else "Termine avec erreurs.")
        self._check_disk()

    # ------------------------------------------------------------------ controls
    def _on_start(self):
        if not self.config_data.get("mega_email") or \
           not self.config_data.get("mega_password"):
            self._append_log("Configurez vos identifiants MEGA (bouton Parametres)")
            self._open_settings()
            return

        src = Path(self.config_data["source_path"])
        if not src.exists():
            self._append_log(f"Disque non detecte : {src}")
            return

        selected = self._get_selected_folders()
        if selected:
            self._append_log(f"Dossiers selectionnes : {', '.join(selected)}")
        else:
            self._append_log("Synchronisation complete du disque")

        self._running = True
        self._paused  = False
        self.btn_start.configure(state="disabled", text="En cours...")
        self.btn_pause.configure(state="normal", text="PAUSE")
        self.btn_stop.configure(state="normal")
        self.mega_lbl.configure(text="MEGA : connexion...")

        def q(action, **kw):
            self._queue.put({"action": action, **kw})

        self.sync_manager = SyncManager(
            config=self.config_data,
            selected_folders=selected,
            on_progress=lambda f, d, t: q("progress", file=f, done=d, total=t),
            on_log=lambda msg: q("log", msg=msg),
            on_complete=lambda data: q("complete", data=data),
            on_mega_connected=lambda: q("mega_ok"),
        )
        self.sync_thread = threading.Thread(target=self.sync_manager.run, daemon=True)
        self.sync_thread.start()

    def _on_pause(self):
        if not self.sync_manager:
            return
        if not self._paused:
            self.sync_manager.stop()
            self._paused  = True
            self._running = False
            self.btn_pause.configure(text="REPRENDRE")
            self.btn_start.configure(state="normal", text="DEMARRER")
            self.btn_stop.configure(state="disabled")
            self.file_lbl.configure(text="En pause - progression sauvegardee sur MEGA")
        else:
            self._paused = False
            self._on_start()

    def _on_stop(self):
        if self.sync_manager:
            self.sync_manager.stop()
        self._running = False
        self._paused  = False
        self.btn_start.configure(state="normal", text="DEMARRER")
        self.btn_pause.configure(state="disabled", text="PAUSE")
        self.btn_stop.configure(state="disabled")
        self.file_lbl.configure(text="Arrete.")

    def _open_settings(self):
        SettingsWindow(self, self.config_data, self._on_settings_saved)

    def _on_settings_saved(self, cfg):
        self.config_data = cfg
        save_config(cfg)
        self._append_log("Parametres enregistres")
        self._check_disk()
