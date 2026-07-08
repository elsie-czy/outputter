import os
import time
import subprocess
import signal
from flask import Blueprint, jsonify, send_file

bp = Blueprint("web_health", __name__, url_prefix="/_health")

HEARTBEAT_TIMEOUT = 60  # 心跳超时秒数


def _project_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _queue_file(name):
    return os.path.join(_project_root(), "data", "queue", name)


def _worker_lock_file():
    return _queue_file("deconstruct_queue.lock")


def _worker_heartbeat_file():
    return _queue_file("worker_heartbeat.txt")


def _worker_stop_file():
    return _queue_file("worker_stop_signal.txt")


def _read_lock_pid():
    try:
        with open(_worker_lock_file(), "r", encoding="utf-8") as f:
            value = (f.read() or "").strip()
        return int(value) if value else None
    except Exception:
        return None


def _is_pid_alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _remove_if_exists(path):
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _start_worker():
    project_root = _project_root()
    log_file = os.path.join(project_root, "logs", "worker_restart.log")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    with open(log_file, "a") as f:
        return subprocess.Popen(
            [".venv/bin/python", "scripts/deconstruct_worker.py"],
            cwd=project_root,
            stdout=f,
            stderr=f,
            start_new_session=True,
        )


def ensure_worker_running():
    """Start the worker only when no live lock holder or fresh heartbeat exists."""
    lock_pid = _read_lock_pid()
    hb_exists, hb_fresh, hb_age = _check_worker_heartbeat()
    if lock_pid and _is_pid_alive(lock_pid):
        return {"started": False, "running": True, "reason": "lock_pid_alive", "pid": lock_pid}
    if hb_fresh:
        return {"started": False, "running": True, "reason": "heartbeat_fresh", "heartbeat_age_sec": hb_age}

    _remove_if_exists(_worker_lock_file())
    _remove_if_exists(_worker_heartbeat_file())
    _remove_if_exists(_worker_stop_file())
    proc = _start_worker()
    time.sleep(1)
    hb_exists, hb_fresh, hb_age = _check_worker_heartbeat()
    return {
        "started": True,
        "running": hb_fresh or _is_pid_alive(proc.pid),
        "pid": proc.pid,
        "heartbeat_fresh": hb_fresh,
        "heartbeat_age_sec": hb_age,
    }


def _check_worker_heartbeat():
    """通过心跳文件判断 worker 是否在线"""
    heartbeat_file = _worker_heartbeat_file()
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
    base = _project_root()
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
        lock_file = _worker_lock_file()
        lock_exists = os.path.exists(lock_file)
        lock_pid = _read_lock_pid()
        lock_pid_alive = _is_pid_alive(lock_pid)
        
        # 检查心跳文件
        hb_exists, hb_fresh, hb_age = _check_worker_heartbeat()
        
        # 综合判断：锁 PID 存活 或 心跳新鲜 → 认为在跑
        is_running = lock_pid_alive or (hb_exists and hb_fresh)
        
        return jsonify({
            "ok": True,
            "data": {
                "name": "deconstruct-worker",
                "status": "running" if is_running else "stopped",
                "healthy": is_running,
                "lock_exists": lock_exists,
                "lock_pid": lock_pid,
                "lock_pid_alive": lock_pid_alive,
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
        old_pid = _read_lock_pid()

        # 1. 写停止信号文件（如果 worker 在跑，让它自己退出）
        os.makedirs(os.path.dirname(_worker_stop_file()), exist_ok=True)
        with open(_worker_stop_file(), "w", encoding="utf-8") as f:
            f.write("stop")

        # 2. 等旧 worker 主动退出。模型/生图阶段可能需要一点时间，不能直接删锁硬启。
        deadline = time.time() + float(os.getenv("WORKER_RESTART_WAIT_SEC", "30"))
        while old_pid and _is_pid_alive(old_pid) and time.time() < deadline:
            time.sleep(0.5)

        if old_pid and _is_pid_alive(old_pid):
            return jsonify({
                "ok": False,
                "error": "Worker 正在处理任务，已发送停止信号；为避免重复 worker，本次未启动新实例。",
                "data": {"old_pid": old_pid, "still_running": True},
            }), 409

        # 3. 确认旧 PID 已退出后再清理运行态文件并启动新 Worker
        for f in [_worker_lock_file(), _worker_heartbeat_file(), _worker_stop_file()]:
            _remove_if_exists(f)

        proc = _start_worker()

        # 4. 等待一下检查心跳文件
        time.sleep(3)
        hb_exists, hb_fresh, hb_age = _check_worker_heartbeat()
        
        return jsonify({
            "ok": True,
            "data": {
                "started": hb_fresh,
                "pid": proc.pid,
                "old_pid": old_pid,
                "message": "Worker 已重启" if hb_fresh else "Worker 启动中..."
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@bp.post("/worker-ensure")
def worker_ensure():
    """确保 Worker 存活；不会启动第二个实例。"""
    try:
        result = ensure_worker_running()
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
