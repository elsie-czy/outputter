import json
import os

from scripts.config import PATHS, ensure_dirs

_XHS_NOTE_CANDIDATE_FILE = os.path.join(PATHS["logs"], "xhs_note_candidates.json")


def load_xhs_note_candidates():
    try:
        if not os.path.exists(_XHS_NOTE_CANDIDATE_FILE):
            return {}
        with open(_XHS_NOTE_CANDIDATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_xhs_note_candidates(data):
    ensure_dirs()
    with open(_XHS_NOTE_CANDIDATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data or {}, f, ensure_ascii=False, indent=2)
