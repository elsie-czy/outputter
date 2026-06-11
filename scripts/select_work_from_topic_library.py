import json
import os
import sys

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.config import PATHS, ensure_dirs
from scripts.utils import read_jsonl, write_jsonl, now_ts


def select_work():
    ensure_dirs()
    items = read_jsonl(PATHS["topic_library"])
    if not items:
        raise RuntimeError("topic_library 为空，请在 data/topic_library.jsonl 添加记录")

    selected = None
    for item in items:
        if not item.get("是否拆解"):
            selected = item
            item["是否拆解"] = True
            item["拆解时间"] = now_ts()
            break

    if not selected:
        raise RuntimeError("没有可拆解作品（是否拆解=否）")

    write_jsonl(PATHS["topic_library"], items)

    temp_path = os.path.join(PATHS["temp"], "selected_work.json")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(selected, f, ensure_ascii=False, indent=2)
    return selected


if __name__ == "__main__":
    work = select_work()
    print("选中作品:", work.get("作品名称"), work.get("作者"))
