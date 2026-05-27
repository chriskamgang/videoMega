"""
Genere des fichiers CSV par categorie avec les liens MEGA embed.
Format : Chapitre, N°, Titre Video, Lien, Date, Slug
"""
import csv
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

REMOTE_NAME = "mega-sync"
RCLONE_CONF = Path.home() / "Documents" / "mega-sync" / "rclone.conf"
EXPORTS_DIR = Path.home() / "Documents" / "mega-sync" / "exports"

VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v"}


# ------------------------------------------------------------------ helpers

def slugify(text):
    text = text.lower().strip()
    for src, dst in [("àáâãä","a"),("èéêë","e"),("ìíîï","i"),
                     ("òóôõö","o"),("ùúûü","u"),("ç","c"),("ñ","n")]:
        for c in src:
            text = text.replace(c, dst)
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def get_mega_link(dest_folder, relative_path):
    """Retourne le lien embed MEGA pour un fichier deja uploade."""
    from sync import _find_rclone
    remote = f"{REMOTE_NAME}:{dest_folder}/{relative_path}"
    r = subprocess.run(
        [_find_rclone(), "link", remote, "--config", str(RCLONE_CONF)],
        capture_output=True, text=True, timeout=30
    )
    link = r.stdout.strip()
    if not link:
        return None
    # Convertir /file/ -> /embed/
    link = link.replace("mega.nz/file/", "mega.nz/embed/")
    return link


# ------------------------------------------------------------------ CSV builder

def _organize(files_links):
    """
    Organise (relative_path, link) en :
      structure[category][course][chapter] = [(title, link), ...]
    """
    structure = {}

    for rel_path, link in files_links:
        if not link:
            continue
        if Path(rel_path).suffix.lower() not in VIDEO_EXT:
            continue

        parts = Path(rel_path).parts

        if len(parts) == 1:
            category = "DIVERS"
            course   = "DIVERS"
            chapter  = "introduction"
        elif len(parts) == 2:
            category = parts[0]
            course   = parts[0]
            chapter  = "introduction"
        elif len(parts) == 3:
            category = parts[0]
            course   = parts[1]
            chapter  = "introduction"
        else:
            category = parts[0]
            course   = parts[1]
            chapter  = parts[2]

        title = Path(rel_path).stem

        structure.setdefault(category, {})
        structure[category].setdefault(course, {})
        structure[category][course].setdefault(chapter, [])
        structure[category][course][chapter].append((title, link))

    return structure


def write_csvs(files_links, on_log=None):
    """
    Ecrit un CSV par categorie dans ~/Documents/mega-sync/exports/.
    Retourne la liste des chemins CSV generes.
    """
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    structure = _organize(files_links)
    today     = datetime.now().strftime("%d.%m.%Y")
    vid_id    = [1]
    csv_paths = []

    for category, courses in structure.items():
        csv_path = EXPORTS_DIR / f"{slugify(category)}.csv"

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            for course, chapters in courses.items():
                writer.writerow([category.upper()] + [""] * 5)
                writer.writerow([course]            + [""] * 5)
                writer.writerow(["Chapitre", "N°", "Titre Video", "Lien", "Date", "Slug"])

                for chapter, videos in chapters.items():
                    for i, (title, link) in enumerate(videos):
                        chap_cell = chapter if i == 0 else ""
                        slug = slugify(title) + f"-{vid_id[0]}"
                        vid_id[0] += 1
                        writer.writerow([chap_cell, i + 1, title, link, today, slug])

        csv_paths.append(csv_path)
        if on_log:
            on_log(f"CSV : {csv_path.name}  ({sum(len(v) for ch in courses.values() for v in ch.values())} videos)")

    return csv_paths


# ------------------------------------------------------------------ main entry

def generate_links_and_csv(uploaded_files, dest_folder,
                            on_log=None, on_progress=None, stop_event=None):
    """
    uploaded_files : liste de relative_path (str)
    dest_folder    : e.g. "TOSHIBA EXT Backup"
    Retourne la liste des CSV generes.
    """
    # Filtrer uniquement les videos
    videos = [p for p in uploaded_files if Path(p).suffix.lower() in VIDEO_EXT]
    total  = len(videos)

    if on_log:
        on_log(f"Generation des liens pour {total} videos...")

    results = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(get_mega_link, dest_folder, p): p for p in videos}

        for i, future in enumerate(as_completed(futures)):
            if stop_event and stop_event.is_set():
                executor.shutdown(wait=False, cancel_futures=True)
                break

            rel = futures[future]
            try:
                link = future.result()
            except Exception:
                link = None

            results.append((rel, link))

            if on_progress:
                on_progress(f"Lien : {rel}", i + 1, total)

            if on_log and (i + 1) % 100 == 0:
                on_log(f"Liens : {i + 1} / {total}")

    if on_log:
        ok = sum(1 for _, l in results if l)
        on_log(f"Liens recuperes : {ok} / {total}")

    return write_csvs(results, on_log)
