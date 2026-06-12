import json
import os
import sys
import time
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from scripts.env_loader import load_dotenv
from scripts.config import PATHS, ensure_dirs, get_run_date
from scripts.model_adapter import analyze_work
from scripts.search import search_work_info
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config
from scripts.related_sync import sync_related, update_main_links
from scripts.utils import append_jsonl, now_ts
from scripts.queue_manager import (
    get_next_pending, update_status, retry_task, _acquire_lock, _release_lock,
)

# Import from deconstruct_daily
from scripts.deconstruct_daily import (
    build_report, build_xhs_note, build_experiment_log,
    sync_to_feishu, sync_xhs_note_table, _build_image_prompts,
)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _check_cache(work):
    """检查飞书主表是否已有拆解记录"""
    try:
        client = FeishuClient()
        if not client.is_configured():
            return False
        records = client.list_records(client.table_id, page_size=500)
        name = work.get("作品名称", "")
        author = work.get("作者", "")
        for r in records:
            f = r.get("fields", {}) or {}
            if (str(f.get("作品名称", "")) == name
                    and str(f.get("作者", "")) == author
                    and f.get("拆解时间")):
                return True
    except Exception:
        pass
    return False


def _log(rid, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{rid}] {msg}")
    log_path = os.path.join(PATHS["logs"], "deconstruct_worker.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] [{rid}] {msg}\n")


def process_one(task, dry=False):
    """处理单个拆文任务，返回 {ok, record_id, error}"""
    rid = task.get("record_id", "unknown")
    work_name = task.get("work_name", "")
    author = task.get("author", "")
    _log(rid, f"开始拆解: {work_name} - {author}")

    t0 = time.perf_counter()
    result = {"ok": False, "record_id": rid, "error": None}
    record_id = None
    xhs_record_id = None

    try:
        # 构建 work 对象（格式对齐 deconstruct_daily 的 load_selected_work 返回值）
        work = {
            "作品名称": task.get("work_name", ""),
            "作者": task.get("author", ""),
            "平台": task.get("platform", ""),
            "分类": task.get("category", ""),
        }

        # 标记处理中
        update_status(rid, "processing")

        # 1. 搜索补全
        search_info = search_work_info(work)
        for k in ["作品名称", "作者", "平台", "分类", "评分", "字数（万）", "完结状态", "简介", "取向"]:
            if not work.get(k) and search_info.get(k):
                work[k] = search_info.get(k)
        
        # 确保必填字段有默认值
        if not work.get("简介"):
            work["简介"] = f"{work.get('作品名称', '')} - {work.get('分类', '')}类小说"

        if dry:
            _log(rid, "dry=True，跳过模型调用")
            return {"ok": True, "record_id": rid}

        # 1.5 缓存检查：作品已拆解则跳过
        force = os.getenv("FORCE_REDECONSTRUCT", "").strip().lower() in ("1", "true", "yes")
        if not force and _check_cache(work):
            _log(rid, "缓存命中，跳过 LLM 调用")
            update_status(rid, "done",
                          deconstruct_result={"缓存": True, "跳过模型": True},
                          note_content="（缓存命中，从飞书主表复用）")
            result["ok"] = True
            return result

        # 2. 调用模型拆解
        analysis = analyze_work(work)
        source = (analysis.get("元信息", {}) or {}).get("来源", "")
        if "openai_parse_fallback" in str(source):
            raise RuntimeError(f"模型解析失败: {source}")
        analysis["配图提示词"] = _build_image_prompts(work, analysis)

        # 3. 生成报告文件
        run_date = get_run_date()
        safe_name = f"{work.get('作品名称', '未知作品')}_{work.get('作者', '未知作者')}"
        report = build_report(work, search_info, analysis)
        xhs_note = build_xhs_note(work, analysis)

        report_path = os.path.join(PATHS["outputs"], "拆解报告", f"{run_date}_{safe_name}_拆解报告.md")
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)

        xhs_dir = os.path.join(PATHS["outputs"], "小红书笔记_v3", safe_name)
        os.makedirs(xhs_dir, exist_ok=True)
        xhs_path = os.path.join(xhs_dir, f"{work.get('作品名称', '未知作品')}-小红书笔记初稿.md")
        with open(xhs_path, "w", encoding="utf-8") as f:
            f.write(xhs_note)

        # 4. 写入飞书主表
        client = FeishuClient()
        if client.is_configured():
            record_id = sync_to_feishu(work, search_info, analysis)
            _log(rid, f"飞书主表写入完成, record_id={record_id}")

            if record_id:
                # 5. 写入小红书笔记库
                try:
                    xhs_record_id = sync_xhs_note_table(record_id, work, analysis, xhs_path)
                    _log(rid, f"小红书笔记库写入完成, xhs_record_id={xhs_record_id}")
                except Exception as e:
                    _log(rid, f"小红书笔记库写入失败: {e}")

                # 6. 关联表同步
                if not work.get("_existing_main_record"):
                    try:
                        related_ids = sync_related(record_id, work, analysis)
                        update_main_links(record_id, related_ids)
                        _log(rid, "关联表同步完成")
                    except Exception as e:
                        _log(rid, f"关联表同步失败: {e}")
        else:
            _log(rid, "飞书未配置，跳过同步")

        # 7. 本地记录
        append_jsonl(
            os.path.join(PATHS["logs"], "records.jsonl"),
            {
                "ts": now_ts(),
                "run_date": run_date,
                "work_name": work.get("作品名称", ""),
                "author": work.get("作者", ""),
                "record_id": record_id,
                "xhs_record_id": xhs_record_id,
                "report_path": report_path,
                "xhs_path": xhs_path,
                "image_prompts": analysis.get("配图提示词", []),
                "published": False,
            },
        )

        # 8. 标记完成
        update_status(rid, "done",
                       deconstruct_result=analysis,
                       note_content=xhs_note)

        # 9. owner 模式：保存结果到本地（待归档）
        from scripts.local_data_manager import get_work_mode, save_result_to_local
        if get_work_mode() == "owner":
            save_result_to_local({
                "record_id": rid,
                "work_name": work.get("作品名称", ""),
                "author": work.get("作者", ""),
                "platform": work.get("平台", ""),
                "category": work.get("分类", ""),
                "deconstruct_result": analysis,
                "note_content": xhs_note,
                "archive_status": "pending",
            })
            _log(rid, "结果已保存到本地（待归档）")

        duration = round(time.perf_counter() - t0, 1)
        _log(rid, f"完成, 耗时 {duration}s")
        result["ok"] = True

    except Exception as e:
        error_msg = str(e)[:500]
        _log(rid, f"失败: {error_msg}")
        update_status(rid, "failed", error=error_msg)
        result["error"] = error_msg

    return result


def run_loop(limit=0, sleep_sec=5.0, dry=False, stay_alive=True):
    """
    循环消费队列。
    limit=0 表示不设上限。
    stay_alive=True 时，队列为空也会继续等待（常驻模式）。
    """
    ensure_dirs()
    if not _acquire_lock():
        print("另一个 worker 实例正在运行，已跳过")
        return

    try:
        processed = 0
        idle_count = 0
        while True:
            task = get_next_pending()
            if not task:
                if not stay_alive:
                    print("队列为空，退出")
                    break
                # 常驻模式：等待新任务
                idle_count += 1
                if idle_count % 12 == 0:  # 每60秒打印一次
                    print(f"等待新任务中... (已空闲 {idle_count * sleep_sec}s)")
                time.sleep(sleep_sec)
                continue
            
            idle_count = 0  # 重置空闲计数
            result = process_one(task, dry=dry)
            if result["ok"]:
                processed += 1
            else:
                # 如果是模型解析失败，自动重试一次
                if "openai_parse_fallback" in str(result.get("error", "")):
                    retry_task(task["record_id"])

            if limit > 0 and processed >= limit:
                print(f"已达到处理上限 {limit}，退出")
                break

            time.sleep(sleep_sec)

        print(f"结束，共处理 {processed} 个任务")

    finally:
        _release_lock()


def run_single(record_id):
    """处理单个指定任务"""
    from scripts.queue_manager import read_jsonl, QUEUE_FILE
    items = read_jsonl(QUEUE_FILE)
    task = None
    for i in items:
        if i.get("record_id") == record_id:
            task = i
            break
    if not task:
        print(f"未找到任务: {record_id}")
        return
    result = process_one(task)
    print(f"结果: ok={result['ok']}, error={result.get('error')}")


if __name__ == "__main__":
    load_dotenv(os.path.join(BASE_DIR, ".env"))
    run_loop()
