import json
import os
import time
import hashlib
from datetime import datetime

from scripts.env_loader import load_dotenv
from scripts.feishu_client import FeishuClient
from scripts.feishu_config import get_feishu_config
from scripts.image_generator import generate_images_from_prompt, is_image_generation_enabled
from scripts.deconstruct_daily import _sanitize_image_prompt_for_jimeng, _sanitize_prompt_for_image_gen


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _hash_job(xhs_record_id, prompts, per_field_images):
    h = hashlib.sha256()
    h.update(str(xhs_record_id or "").encode("utf-8"))
    h.update(b"\n")
    h.update(str(per_field_images or 2).encode("utf-8"))
    h.update(b"\n")
    for p in (prompts or [])[:5]:
        h.update(str(p or "").encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()[:24]


def _acquire_lock(path):
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
        return True
    except FileExistsError:
        return False


def _release_lock(path):
    try:
        os.remove(path)
    except Exception:
        pass


def _read_cursor(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return int(f.read().strip() or "0")
    except Exception:
        return 0


def _write_cursor(path, pos):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(str(int(pos)))
    os.replace(tmp, path)


def _count_attachments(v):
    return len(v) if isinstance(v, list) else 0


def _get_prompts(fields):
    prompts = []
    for i in range(1, 6):
        prompts.append(str(fields.get(f"生成配图提示词{i}", "")).strip())
    return prompts


def _backfill_one_record(client, table_id, record, per_field_images=2, sleep_sec=0.0):
    rid = record.get("record_id")
    fields = record.get("fields", {}) or {}
    work_name = str(fields.get("作品名称", "")).strip()

    prompts = _get_prompts(fields)
    if not any(prompts):
        return {"record_id": rid, "work_name": work_name, "status": "skipped_no_prompts"}

    safe_en = "anime style portrait, vertical 3:4, clean background, no text, no logo, no watermark"
    patch = {}
    errors = []
    for i in range(1, 6):
        target_field = f"即梦生图{i}"
        cur = fields.get(target_field, [])
        cur = cur if isinstance(cur, list) else []
        need = max(0, per_field_images - len(cur))
        if need <= 0:
            continue

        prompt = prompts[i - 1]
        # 先净化prompt（去除文字引导 + 追加禁止文字），再尝试生成
        clean_prompt = _sanitize_prompt_for_image_gen(prompt)
        tries = [t for t in [clean_prompt, _sanitize_image_prompt_for_jimeng(prompt), safe_en] if t]
        tokens = []
        for tp in tries:
            if len(tokens) >= need:
                break
            try:
                paths = generate_images_from_prompt(tp, n=need - len(tokens))
                for ph in paths:
                    try:
                        tok = client.upload_file_to_bitable(ph)
                        tokens.append({"file_token": tok})
                    except Exception as e:
                        errors.append(f"upload {target_field}: {e}")
            except Exception as e:
                errors.append(f"gen {target_field}: {e}")
                continue

        if tokens:
            patch[target_field] = (cur + tokens)[:per_field_images]
        if sleep_sec:
            time.sleep(sleep_sec)

    if not patch:
        return {"record_id": rid, "work_name": work_name, "status": "skipped_no_patch", "errors": errors[-5:]}

    client.update_record_in_table(table_id, rid, patch)
    return {
        "record_id": rid,
        "work_name": work_name,
        "status": "updated",
        "patched_fields": list(patch.keys()),
        "errors": errors[-5:],
    }


def run(mode="missing", limit=0, max_retries=2, sleep_sec=0.0):
    """
    mode:
      - missing: scan xhs table, fill missing 即梦生图1-5 (<=2 per field)
      - jobs: consume logs/image_jobs.jsonl and backfill those record_ids
    """
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    load_dotenv(os.path.join(base_dir, ".env"))

    if not is_image_generation_enabled():
        raise RuntimeError("IMAGE_GEN_ENABLED is false; refusing to run jimeng worker")

    client = FeishuClient()
    cfg = get_feishu_config()
    table_id = cfg["related_table_ids"]["小红书笔记库"]
    meta = client.get_table_field_meta(table_id)
    for i in range(1, 6):
        if f"即梦生图{i}" not in meta:
            raise RuntimeError("xhs table missing 即梦生图1-5 fields; create columns first")

    report = {
        "ts": _now(),
        "mode": mode,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "details": [],
    }

    logs_dir = os.path.join(base_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)
    results_path = os.path.join(logs_dir, "image_job_results.jsonl")

    records = []
    if mode == "jobs":
        jobs_path = os.path.join(base_dir, "logs", "image_jobs.jsonl")
        if not os.path.exists(jobs_path):
            raise RuntimeError(f"jobs file not found: {jobs_path}")
        lock_path = os.path.join(logs_dir, "jimeng_worker.lock")
        if not _acquire_lock(lock_path):
            raise RuntimeError(f"jimeng worker already running (lock exists): {lock_path}")
        cursor_path = os.path.join(logs_dir, "image_jobs.cursor")
        start_pos = _read_cursor(cursor_path)
        try:
            # Read jobs from cursor onward; only keep the latest job per record_id.
            latest = {}
            with open(jobs_path, "r", encoding="utf-8") as f:
                f.seek(start_pos)
                while True:
                    pos = f.tell()
                    line = f.readline()
                    if not line:
                        _write_cursor(cursor_path, pos)
                        break
                    line = line.strip()
                    if not line:
                        continue
                    job = json.loads(line)
                    rid = str(job.get("xhs_record_id", "")).strip()
                    if not rid:
                        continue
                    prompts = job.get("prompts", []) or []
                    per = int(job.get("per_field_images") or 2)
                    job_id = str(job.get("job_id") or _hash_job(rid, prompts, per))
                    latest[rid] = {
                        "job_id": job_id,
                        "xhs_record_id": rid,
                        "prompts": prompts[:5],
                        "per_field_images": per,
                        "enqueued_ts": job.get("ts"),
                    }
            if not latest:
                return report

            # Fetch all and filter locally (still bounded by xhs table size).
            for r in client.list_records(table_id):
                rrid = r.get("record_id")
                if rrid in latest:
                    r["_job"] = latest[rrid]
                    records.append(r)
        finally:
            _release_lock(lock_path)
    else:
        for r in client.list_records(table_id):
            f = r.get("fields", {}) or {}
            if not any(str(f.get(f"生成配图提示词{i}", "")).strip() for i in range(1, 6)):
                continue
            counts = [_count_attachments(f.get(f"即梦生图{i}", [])) for i in range(1, 6)]
            if min(counts) < 2:
                records.append(r)

    if limit and limit > 0:
        records = records[:limit]

    for r in records:
        rid = r.get("record_id")
        job = r.get("_job") if isinstance(r, dict) else None
        try:
            per = int((job or {}).get("per_field_images") or 2)
            attempts = 0
            last = None
            while attempts <= max_retries:
                try:
                    last = _backfill_one_record(
                        client, table_id, r, per_field_images=per, sleep_sec=sleep_sec
                    )
                    break
                except Exception as e:
                    attempts += 1
                    last = {"record_id": rid, "status": "retrying", "error": str(e)}
                    time.sleep(min(15, 2 * attempts))
            res = last
            report["details"].append(res)
            if res["status"].startswith("updated"):
                report["updated"] += 1
            else:
                report["skipped"] += 1
            # Append result line for observability
            with open(results_path, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": _now(),
                            "job_id": (job or {}).get("job_id"),
                            "xhs_record_id": rid,
                            "work_name": res.get("work_name"),
                            "status": res.get("status"),
                            "patched_fields": res.get("patched_fields", []),
                            "errors": res.get("errors", []),
                            "enqueued_ts": (job or {}).get("enqueued_ts"),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception as e:
            report["failed"] += 1
            report["details"].append({"record_id": rid, "status": "failed", "error": str(e)})
            with open(results_path, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": _now(),
                            "job_id": (job or {}).get("job_id"),
                            "xhs_record_id": rid,
                            "status": "failed",
                            "error": str(e),
                            "enqueued_ts": (job or {}).get("enqueued_ts"),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    out = os.path.join(base_dir, "logs", f"jimeng_worker_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return out


if __name__ == "__main__":
    import sys

    mode = sys.argv[1] if len(sys.argv) > 1 else "missing"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    max_retries = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    sleep_sec = float(sys.argv[4]) if len(sys.argv) > 4 else 0.0
    path = run(mode=mode, limit=limit, max_retries=max_retries, sleep_sec=sleep_sec)
    print(path)
