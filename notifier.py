import subprocess
import sys


def notify(title, message):
    if sys.platform == "darwin":
        script = f'display notification "{message}" with title "{title}" sound name "Glass"'
        try:
            subprocess.run(["osascript", "-e", script], check=True, timeout=5)
        except Exception:
            pass

    elif sys.platform == "win32":
        try:
            from win10toast import ToastNotifier
            ToastNotifier().show_toast(title, message, duration=6, threaded=True)
        except Exception:
            pass

    else:
        # Linux
        try:
            subprocess.run(["notify-send", title, message], timeout=5)
        except Exception:
            pass
