import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.config import PATHS, ensure_dirs


def clean():
    ensure_dirs()
    removed = []
    for fname in ["selected_work.json"]:
        path = os.path.join(PATHS["temp"], fname)
        if os.path.exists(path):
            os.remove(path)
            removed.append(path)
    return removed


if __name__ == "__main__":
    removed = clean()
    if removed:
        print("已清理:")
        for p in removed:
            print("-", p)
    else:
        print("无可清理内容")
