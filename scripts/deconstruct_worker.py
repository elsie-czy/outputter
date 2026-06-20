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
    update_task_fields,
)
from scripts.quality_scorer import score_note
from scripts.data_normalizer import normalize_feishu_record, normalize_feishu_value
from scripts.generation_context import build_generation_context, context_counts

# Import from deconstruct_daily
from scripts.deconstruct_daily import (
    build_report, build_xhs_note, build_experiment_log,
    sync_to_feishu, sync_xhs_note_table, _build_image_prompts,
)


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _check_xhs_cache(work, need_prompts=True):
    """从小红书笔记库获取已有图片提示词和笔记内容"""
    try:
        from scripts.feishu_config import get_feishu_config
        client = FeishuClient()
        if not client.is_configured():
            return None
        cfg = get_feishu_config()
        table_id = (cfg.get("related_table_ids") or {}).get("小红书笔记库")
        if not table_id:
            return None
        records = client.list_records(table_id, page_size=500)
        name = (work.get("作品名称", "") or "").strip()
        for r in records:
            f = r.get("fields", {}) or {}
            f_name = str(f.get("作品名称", ""))
            if isinstance(f_name, list):
                f_name = str(f_name[0]) if f_name else ""
            f_name = f_name.strip()
            if f_name == name:
                if need_prompts:
                    has_prompts = any(normalize_feishu_value(f.get(f"生成配图提示词{i}")) for i in range(1, 6))
                    if not has_prompts:
                        continue
                return f
    except Exception:
        pass
    return None


def _check_cache(work):
    """检查飞书主表是否已有拆解记录，有则返回旧 analysis，否则返回 None"""
    try:
        client = FeishuClient()
        if not client.is_configured():
            return None
        records = client.list_records(client.table_id, page_size=500)
        name = work.get("作品名称", "")
        author = work.get("作者", "")
        for r in records:
            f = r.get("fields", {}) or {}
            if (str(f.get("作品名称", "")) == name
                    and str(f.get("作者", "")) == author
                    and f.get("拆解时间")):
                return f
    except Exception:
        pass
    return None


def _log(rid, msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{rid}] {msg}")
    log_path = os.path.join(PATHS["logs"], "deconstruct_worker.log")
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] [{rid}] {msg}\n")


def _set_status(rid, status, **kwargs):
    update_status(rid, status, **kwargs)
    if kwargs.get("error"):
        _log(rid, f"状态变更 -> {status}, error={kwargs.get('error')}")
    else:
        _log(rid, f"状态变更 -> {status}")


def _lock_path():
    return os.path.join(PATHS["queue"], "deconstruct_queue.lock")


def _lock_pid():
    try:
        with open(_lock_path(), "r", encoding="utf-8") as f:
            return int((f.read() or "").strip())
    except Exception:
        return None


def _write_heartbeat():
    """写入心跳文件，供 web 状态灯读取"""
    try:
        hb_path = os.path.join(PATHS["queue"], "worker_heartbeat.txt")
        with open(hb_path, "w", encoding="utf-8") as f:
            f.write(str(int(time.time())))
    except Exception:
        pass


def _is_pid_alive(pid):
    """检查指定 PID 的进程是否还在运行"""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return True


def _acquire_worker_lock():
    if _acquire_lock():
        return True
    # 当前进程自己的残留锁
    if _lock_pid() == os.getpid():
        _log("worker", f"发现当前 PID 的残留队列锁，清理后重新获取 pid={os.getpid()}")
        _release_lock()
        return _acquire_lock()
    # 其他进程的残留锁（进程已退出但锁未清理）
    locked_pid = _lock_pid()
    if locked_pid and not _is_pid_alive(locked_pid):
        _log("worker", f"发现残留队列锁 (pid={locked_pid} 已退出)，自动清理")
        _release_lock()
        return _acquire_lock()
    return False


def _score_note_for_task(rid, note_text, step_times):
    t_score = time.perf_counter()
    _set_status(rid, "ai_scoring")
    try:
        score = score_note(note_text)
        _log(rid, f"AI评分完成: {score.get('total', 0)}")
    except Exception as e:
        _log(rid, f"AI评分失败，使用降级评分: {e}")
        score = {
            "title_appeal": 0,
            "emotion_density": 0,
            "collection_value": 0,
            "interaction_guide": 0,
            "xhs_style_match": 0,
            "ai_trace": 0,
            "total": 0,
            "grade": "retry",
            "suggestion": f"评分失败: {e}",
            "_fallback": True,
        }
    step_times["ai_scoring"] = {
        "done": _now(),
        "duration": round(time.perf_counter() - t_score, 1),
    }
    update_task_fields(rid, quality_score=score)
    return score


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
    step_times = {}

    try:
        # 构建 work 对象（格式对齐 deconstruct_daily 的 load_selected_work 返回值）
        work = {
            "作品名称": task.get("work_name", ""),
            "作者": task.get("author", ""),
            "平台": task.get("platform", ""),
            "分类": task.get("category", ""),
            "简介": task.get("synopsis", ""),
            "取向": task.get("orientation", ""),
        }

        # 标记处理中
        _set_status(rid, "processing")
        step_times["waiting"] = {"done": _now(), "duration": 0}

        # 1. 搜索补全
        search_info = search_work_info(work)
        for k in ["作品名称", "作者", "平台", "分类", "评分", "字数（万）", "完结状态", "简介", "取向"]:
            if not work.get(k) and search_info.get(k):
                work[k] = search_info.get(k)
        # 简介优先用搜索到的版本（通常更详细准确）
        if search_info.get("简介") and len(str(search_info.get("简介"))) > len(str(work.get("简介", ""))):
            work["简介"] = search_info["简介"]
            if search_info.get("搜索来源链接"):
                work["简介来源"] = search_info["搜索来源链接"]
        
        # 确保必填字段有默认值
        if not work.get("简介"):
            work["简介"] = ""

        if dry:
            _log(rid, "dry=True，跳过模型调用")
            return {"ok": True, "record_id": rid}

        # 1.5 缓存检查：作品已拆解则跳过 LLM，但仍生成图片
        force = os.getenv("FORCE_REDECONSTRUCT", "").strip().lower() in ("1", "true", "yes")
        cached_main = _check_cache(work) if not force else None
        if cached_main:
            _log(rid, "缓存命中，跳过 LLM 调用，尝试补生成图片")

            # 从小红书笔记库获取笔记内容和配图提示词
            cached_xhs = _check_xhs_cache(work, need_prompts=False)
            if cached_xhs:
                xhs_title = normalize_feishu_value(cached_xhs.get("小红书标题模板", ""))
                xhs_body = normalize_feishu_value(cached_xhs.get("正文开头模板", ""))
                xhs_cta = normalize_feishu_value(cached_xhs.get("互动话术模板", ""))
                xhs_tags = cached_xhs.get("热门标签推荐", [])
                if isinstance(xhs_tags, list):
                    xhs_tags = ", ".join(str(t) for t in xhs_tags)
                else:
                    xhs_tags = str(xhs_tags or "")
                note_content = f"标题：{xhs_title}\n\n{xhs_body}\n\n互动话术：{xhs_cta}\n\n标签：{xhs_tags}"
            else:
                note_content = "标题：" + work.get("作品名称", "") + " 拆解笔记\n\n请运行拆文任务获取笔记内容"

            # 映射为前端可读的 analysis 格式
            analysis = normalize_feishu_record(cached_main, source="main")
            images = {}

            # 从小红书笔记库获取配图提示词（用于生图）
            cached_xhs_img = _check_xhs_cache(work, need_prompts=True)
            if not cached_xhs_img:
                cached_xhs_img = cached_main

            quality_score = _score_note_for_task(rid, note_content, step_times)
            if os.getenv("IMAGE_GEN_ENABLED", "false").strip().lower() in ("1", "true", "yes"):
                try:
                    from scripts.image_provider import generate_images_for_task
                    _set_status(rid, "generating_image")
                    img_result = generate_images_for_task(cached_xhs)
                    if img_result["ok"]:
                        images = img_result["images"]
                        _log(rid, f"图片补生成成功: {list(images.keys())}")
                    else:
                        _log(rid, f"图片补生成失败: {img_result.get('error','未知')}")
                except Exception as e:
                    _log(rid, f"图片补生成异常: {e}")
            _set_status(rid, "done",
                        deconstruct_result=analysis,
                        note_content=note_content,
                        quality_score=quality_score,
                        step_times=step_times,
                        images=images)
            result["ok"] = True
            return result

        # 2. 调用模型拆解
        t_deconstruct = time.perf_counter()
        _set_status(rid, "deconstructing")
        generation_context = build_generation_context(task)
        counts = context_counts(generation_context)
        _log(
            rid,
            "模型上下文: "
            f"参考笔记 {counts['reference_notes']} 条, "
            f"近期反馈 {counts['recent_feedback']} 条",
        )
        analysis = analyze_work(work, **generation_context)
        source = (analysis.get("元信息", {}) or {}).get("来源", "")
        if "openai_parse_fallback" in str(source):
            raise RuntimeError(f"模型解析失败: {source}")
        analysis["配图提示词"] = _build_image_prompts(work, analysis)
        step_times["deconstructing"] = {"done": _now(), "duration": round(time.perf_counter() - t_deconstruct, 1)}

        # 3. 生成报告文件
        t_note = time.perf_counter()
        _set_status(rid, "generating_note")
        run_date = get_run_date()
        safe_name = f"{work.get('作品名称', '未知作品')}_{work.get('作者', '未知作者')}"
        report = build_report(work, search_info, analysis)
        xhs_note = build_xhs_note(work, analysis)
        quality_score = _score_note_for_task(rid, xhs_note, step_times)

        # 评分闭环：grade=retry 且非降级分数时，重试一次
        if (
            not quality_score.get("_fallback")
            and quality_score.get("grade") == "retry"
            and os.getenv("QUALITY_AUTO_RETRY", "1").strip().lower() in ("1", "true", "yes")
        ):
            _log(rid, f"评分 {quality_score['total']} < 75，按建议重试: {quality_score.get('suggestion', '')}")
            retry_feedback = [{"time": _now(), "field": "整体", "reason": quality_score.get("suggestion", "")}]
            retry_ctx = {
                "reference_notes": generation_context.get("reference_notes"),
                "recent_feedback": retry_feedback,
            }
            analysis = analyze_work(work, **retry_ctx)
            analysis["配图提示词"] = _build_image_prompts(work, analysis)
            report = build_report(work, search_info, analysis)
            xhs_note = build_xhs_note(work, analysis)
            quality_score = _score_note_for_task(rid, xhs_note, step_times)
            _log(rid, f"重试后评分: {quality_score.get('total', 0)} ({quality_score.get('grade', '')})")

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
        t_feishu = time.perf_counter()
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
        step_times["generating_note"] = {"done": _now(), "duration": round(time.perf_counter() - t_note, 1)}
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
        step_times["done"] = {"done": _now(), "duration": 0}
        _set_status(rid, "done",
                    deconstruct_result=analysis,
                    note_content=xhs_note,
                    quality_score=quality_score,
                    step_times=step_times)
        update_task_fields(rid, main_record_id=record_id, xhs_record_id=xhs_record_id)

        # 9. 生成图片（如果启用）
        images = {}
        if os.getenv("IMAGE_GEN_ENABLED", "false").strip().lower() in ("1", "true", "yes"):
            t_image = time.perf_counter()
            _log(rid, "开始生成图片...")
            try:
                from scripts.image_provider import generate_images_for_task
                _set_status(rid, "generating_image")
                img_result = generate_images_for_task(analysis)
                if img_result["ok"]:
                    images = img_result["images"]
                    _log(rid, f"图片生成成功: {list(images.keys())}")
                else:
                    _log(rid, f"图片生成失败: {img_result['error']}")
                step_times["generating_image"] = {"done": _now(), "duration": round(time.perf_counter() - t_image, 1)}
                # 更新完成状态（包含完整的 step_times）
                step_times["done"] = {"done": _now(), "duration": 0}
                _set_status(rid, "done", images=images, step_times=step_times)
            except Exception as e:
                _log(rid, f"图片生成异常: {e}")
                step_times["generating_image"] = {"done": _now(), "duration": round(time.perf_counter() - t_image, 1)}
                step_times["done"] = {"done": _now(), "duration": 0}
                _set_status(rid, "done", images=images, step_times=step_times)
        else:
            _log(rid, "图片生成未启用，跳过")
            step_times["generating_image"] = {"done": _now(), "duration": 0}

        # 10. owner 模式：保存结果到本地（待归档）
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
                "images": images,
                "archive_status": "pending",
            })
            _log(rid, "结果已保存到本地（待归档）")

        duration = round(time.perf_counter() - t0, 1)
        _log(rid, f"完成, 耗时 {duration}s")
        result["ok"] = True

    except Exception as e:
        error_msg = str(e)[:500]
        _log(rid, f"失败: {error_msg}")
        _set_status(rid, "failed", error=error_msg)
        result["error"] = error_msg

    return result


def run_loop(limit=0, sleep_sec=5.0, dry=False, stay_alive=True):
    """
    循环消费队列。
    limit=0 表示不设上限。
    stay_alive=True 时，队列为空也会继续等待（常驻模式）。
    """
    ensure_dirs()
    _log("worker", f"启动队列消费: stay_alive={stay_alive}, limit={limit}, sleep_sec={sleep_sec}, dry={dry}")
    while not _acquire_worker_lock():
        if not stay_alive:
            _log("worker", "另一个 worker 实例正在运行，已跳过")
            return
        pid = _lock_pid()
        suffix = f" pid={pid}" if pid else ""
        _log("worker", f"另一个 worker 实例正在运行，等待队列锁释放{suffix}")
        time.sleep(30)

    try:
        _write_heartbeat()  # 启动时立即写心跳
        processed = 0
        idle_count = 0
        last_heartbeat = 0
        while True:
            # 检查停止信号
            stop_file = os.path.join(PATHS["queue"], "worker_stop_signal.txt")
            if os.path.exists(stop_file):
                _log("worker", "收到停止信号，准备退出")
                try:
                    os.remove(stop_file)
                except Exception:
                    pass
                break

            # 每30秒写一次心跳
            now_ts = time.time()
            if now_ts - last_heartbeat >= 30:
                _write_heartbeat()
                last_heartbeat = now_ts

            task = get_next_pending()
            if not task:
                if not stay_alive:
                    _log("worker", "队列为空，退出")
                    break
                # 常驻模式：等待新任务
                idle_count += 1
                if idle_count % 12 == 0:  # 每60秒打印一次
                    _log("worker", f"等待新任务中... (已空闲 {idle_count * sleep_sec}s)")
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
                _log("worker", f"已达到处理上限 {limit}，退出")
                break

            time.sleep(sleep_sec)

        _log("worker", f"结束，共处理 {processed} 个任务")

    finally:
        # 清理心跳文件（停止时标记为离线）
        try:
            hb_path = os.path.join(PATHS["queue"], "worker_heartbeat.txt")
            if os.path.exists(hb_path):
                os.remove(hb_path)
        except Exception:
            pass
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
