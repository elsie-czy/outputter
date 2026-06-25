import os
import time
import subprocess
import signal
from flask import Blueprint, jsonify, send_file

bp = Blueprint("web_health", __name__, url_prefix="/_health")

HEARTBEAT_TIMEOUT = 60  # 心跳超时秒数


def _check_worker_heartbeat():
    """通过心跳文件判断 worker 是否在线"""
    # scripts/web/routes/ -> .. -> scripts/web -> .. -> scripts -> .. -> project_root
    base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    heartbeat_file = os.path.join(base, "data", "queue", "worker_heartbeat.txt")
    if not os.path.exists(heartbeat_file):
        return False, False, None
    try:
        with open(heartbeat_file, "r", encoding="utf-8") as f:
            ts = int((f.read() or "").strip())
        age = int(time.time()) - ts
        return True, age <= HEARTBEAT_TIMEOUT, age
    except Exception:
        return False, False, None


@bp.get("/images/<path:filepath>")
def serve_image(filepath):
    """服务本地图片: /_health/images/dir/filename.png"""
    base = os.path.join(os.path.dirname(__file__), "..", "..", "..")
    base = os.path.abspath(base)
    # 优先用完整相对路径（支持子目录，如 temp/generated_images/rid/xhs_card_01.png）
    full = os.path.join(base, filepath)
    if os.path.exists(full):
        return send_file(full, mimetype="image/png")
    # 兼容裸文件名（不含前缀目录）
    for prefix in ["temp/generated_images", "temp/jimeng_cache", "temp/html_cards"]:
        full = os.path.join(base, prefix, filepath)
        if os.path.exists(full):
            return send_file(full, mimetype="image/png")
    return jsonify({"ok": False, "error": "image not found: " + filepath}), 404


@bp.get("")
def health():
    return jsonify({"ok": True, "service": "personal-supertool-web"})


@bp.get("/worker-status")
def worker_status():
    """检查 Worker 运行状态（通过心跳文件，不依赖 ps/pgrep）"""
    try:
        # 检查锁文件
        lock_file = os.path.join(os.path.dirname(__file__), "..", "..", "data", "queue", "deconstruct_queue.lock")
        lock_file = os.path.abspath(lock_file)
        lock_exists = os.path.exists(lock_file)
        
        # 检查心跳文件
        hb_exists, hb_fresh, hb_age = _check_worker_heartbeat()
        
        # 综合判断：锁存在 或 心跳新鲜 → 认为在跑
        is_running = lock_exists or (hb_exists and hb_fresh)
        
        return jsonify({
            "ok": True,
            "data": {
                "name": "deconstruct-worker",
                "status": "running" if is_running else "stopped",
                "healthy": is_running,
                "lock_exists": lock_exists,
                "heartbeat_exists": hb_exists,
                "heartbeat_fresh": hb_fresh,
                "heartbeat_age_sec": hb_age,
            }
        })
    except Exception as e:
        return jsonify({
            "ok": True,
            "data": {
                "name": "deconstruct-worker",
                "status": "unknown",
                "healthy": False,
                "error": str(e),
            }
        })


@bp.post("/worker-restart")
def worker_restart():
    """重启 Worker"""
    try:
        project_root = "/Users/lalalaba/Desktop/personal-supertool"
        
        # 1. 写停止信号文件（如果 worker 在跑，让它自己退出）
        stop_signal = os.path.join(project_root, "data", "queue", "worker_stop_signal.txt")
        with open(stop_signal, "w") as f:
            f.write("stop")
        
        # 2. 等待并清理
        import time
        time.sleep(2)
        
        # 删除锁文件和心跳文件
        lock_file = os.path.join(project_root, "data", "queue", "deconstruct_queue.lock")
        heartbeat_file = os.path.join(project_root, "data", "queue", "worker_heartbeat.txt")
        for f in [lock_file, heartbeat_file, stop_signal]:
            if os.path.exists(f):
                os.remove(f)
        
        # 3. 启动新 Worker
        log_file = os.path.join(project_root, "logs", "worker_restart.log")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        with open(log_file, "a") as f:
            subprocess.Popen(
                [".venv/bin/python", "scripts/deconstruct_worker.py"],
                cwd=project_root,
                stdout=f,
                stderr=f,
                start_new_session=True
            )
        
        # 4. 等待一下检查心跳文件
        time.sleep(3)
        hb_exists, hb_fresh, hb_age = _check_worker_heartbeat()
        
        return jsonify({
            "ok": True,
            "data": {
                "started": hb_fresh,
                "message": "Worker 已重启" if hb_fresh else "Worker 启动中..."
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
