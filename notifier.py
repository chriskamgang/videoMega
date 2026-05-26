import subprocess

def notify(title, message):
    script = f'display notification "{message}" with title "{title}" sound name "Glass"'
    try:
        subprocess.run(["osascript", "-e", script], check=True, timeout=5)
    except Exception:
        pass
