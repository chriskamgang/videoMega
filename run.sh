#!/bin/bash
# Lancer MEGA Sync
cd "$(dirname "$0")"

# Creer le venv si absent
if [ ! -d "venv" ]; then
    echo "Preparation de l'environnement Python..."
    python3 -m venv venv
    venv/bin/pip install -r requirements.txt -q
fi

# Installer rclone si absent
if ! command -v rclone &>/dev/null; then
    echo "Installation de rclone..."
    brew install rclone
fi

venv/bin/python main.py
