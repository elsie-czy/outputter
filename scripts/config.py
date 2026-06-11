import os
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

PATHS = {
    "data": os.path.join(BASE_DIR, "data"),
    "outputs": os.path.join(BASE_DIR, "outputs"),
    "temp": os.path.join(BASE_DIR, "temp"),
    "memory": os.path.join(BASE_DIR, "memory"),
    "logs": os.path.join(BASE_DIR, "logs"),
    "state_db": os.path.join(BASE_DIR, "data", "shared_state", "state.db"),
    "topic_library": os.path.join(BASE_DIR, "data", "topic_library.jsonl"),
    "queue": os.path.join(BASE_DIR, "data", "queue"),
}


def get_run_date():
    run_date = os.getenv("RUN_DATE", "").strip()
    if run_date:
        return run_date
    return datetime.now().strftime("%Y%m%d")


def ensure_dirs():
    for key in ["data", "outputs", "temp", "memory", "logs"]:
        os.makedirs(PATHS[key], exist_ok=True)
    # outputs subdirs
    for sub in ["拆解报告", "小红书笔记_v3", "实验记录", "字段优化分析", "修复记录"]:
        os.makedirs(os.path.join(PATHS["outputs"], sub), exist_ok=True)
    os.makedirs(os.path.dirname(PATHS["state_db"]), exist_ok=True)
