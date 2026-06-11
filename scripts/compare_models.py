import json
import os
import re
import sys
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.config import PATHS, ensure_dirs, get_run_date
from scripts.deconstruct_daily import build_report, build_xhs_note, load_selected_work
from scripts.env_loader import load_dotenv
from scripts.model_adapter import analyze_work
from scripts.search import search_work_info


def _safe_name(text):
    return re.sub(r"[\\\\/:*?\"<>|]+", "_", str(text))


def _prepare_work():
    work = load_selected_work()
    search_info = search_work_info(work)
    for key in ["作品名称", "作者", "平台", "分类", "评分", "字数（万）", "完结状态", "简介", "取向"]:
        if not work.get(key) and search_info.get(key):
            work[key] = search_info[key]
    if not work.get("字数（万）"):
        for alt in ["字数", "字数（万字）", "字数_万_"]:
            if work.get(alt):
                work["字数（万）"] = work.get(alt)
                break
    return work, search_info


def run_compare():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    load_dotenv(os.path.join(base_dir, ".env"), override=False)
    ensure_dirs()

    models_raw = os.getenv("COMPARE_MODELS", "glm-4-flash,glm-4-air,glm-4-plus")
    models = [m.strip() for m in models_raw.split(",") if m.strip()]
    if not models:
        raise RuntimeError("COMPARE_MODELS 为空")

    work, search_info = _prepare_work()
    run_date = get_run_date()
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_work = _safe_name(f"{work.get('作品名称','未知作品')}_{work.get('作者','未知作者')}")

    out_dir = os.path.join(PATHS["outputs"], "模型对比", f"{run_date}_{now}_{safe_work}")
    os.makedirs(out_dir, exist_ok=True)

    provider = os.getenv("MODEL_PROVIDER", "openai")
    original_model = os.getenv("OPENAI_MODEL", "")

    summary = []
    for model in models:
        os.environ["MODEL_PROVIDER"] = provider
        os.environ["OPENAI_MODEL"] = model
        model_safe = _safe_name(model)
        try:
            analysis = analyze_work(work)
            report = build_report(work, search_info, analysis)
            xhs_note = build_xhs_note(work, analysis)

            report_path = os.path.join(out_dir, f"{model_safe}_拆解报告.md")
            note_path = os.path.join(out_dir, f"{model_safe}_小红书笔记.md")
            analysis_path = os.path.join(out_dir, f"{model_safe}_analysis.json")

            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report)
            with open(note_path, "w", encoding="utf-8") as f:
                f.write(xhs_note)
            with open(analysis_path, "w", encoding="utf-8") as f:
                json.dump(analysis, f, ensure_ascii=False, indent=2)

            summary.append(
                {
                    "model": model,
                    "status": "ok",
                    "report_path": report_path,
                    "note_path": note_path,
                    "analysis_path": analysis_path,
                }
            )
            print(f"[ok] {model}")
        except Exception as e:
            err_path = os.path.join(out_dir, f"{model_safe}_error.txt")
            with open(err_path, "w", encoding="utf-8") as f:
                f.write(str(e))
            summary.append({"model": model, "status": "error", "error": str(e), "error_path": err_path})
            print(f"[error] {model}: {e}")

    if original_model:
        os.environ["OPENAI_MODEL"] = original_model

    summary_path = os.path.join(out_dir, "SUMMARY.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("对比完成:")
    print("- 输出目录:", out_dir)
    print("- 汇总文件:", summary_path)


if __name__ == "__main__":
    run_compare()
