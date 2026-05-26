#!/usr/bin/env python3
"""
MEGA Sync - Synchronisation intelligente disque dur -> MEGA
Lancer avec : ./run.sh
"""
import sys
from pathlib import Path

project_dir = Path(__file__).parent
if str(project_dir) not in sys.path:
    sys.path.insert(0, str(project_dir))

from gui import App

if __name__ == "__main__":
    app = App()
    app.mainloop()
