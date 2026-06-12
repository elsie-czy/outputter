import os
import subprocess
import signal
from flask import Blueprint, jsonify

bp = Blueprint("web_health", __name__, url_prefix="/_health")


@bp.get("")
def health():
    return jsonify({"ok": True, "service": "personal-supertool-web"})


@bp.get("/worker-status")
def worker_status():
    """检查 Worker 运行状态"""
    try:
        # 检查锁文件
        lock_file = os.path.join(os.path.dirname(__file__), "..", "..", "data", "queue", "deconstruct_queue.lock")
        lock_exists = os.path.exists(lock_file)
        
        # 检查进程
        worker_running = False
        try:
            result = subprocess.run(
                ["pgrep", "-f", "deconstruct_worker"],
                capture_output=True,
                text=True
            )
            worker_running = result.returncode == 0
        except:
            pass
        
        # 综合判断
        is_running = lock_exists or worker_running
        
        return jsonify({
            "ok": True,
            "data": {
                "name": "deconstruct-worker",
                "status": "running" if is_running else "stopped",
                "healthy": is_running,
                "lock_exists": lock_exists,
                "process_exists": worker_running,
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
        base_dir = os.path.join(os.path.dirname(__file__), "..", "..")
        
        # 1. 停止现有 Worker
        try:
            subprocess.run(["pkill", "-f", "deconstruct_worker"], capture_output=True)
            import time
            time.sleep(1)
        except:
            pass
        
        # 2. 删除锁文件
        lock_file = os.path.join(base_dir, "data", "queue", "deconstruct_queue.lock")
        if os.path.exists(lock_file):
            os.remove(lock_file)
        
        # 3. 启动新 Worker
        log_file = os.path.join(base_dir, "..", "logs", "worker_restart.log")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        
        with open(log_file, "a") as f:
            subprocess.Popen(
                ["python", "scripts/deconstruct_worker.py"],
                cwd=base_dir,
                stdout=f,
                stderr=f,
                start_new_session=True
            )
        
        # 4. 等待一下检查是否启动成功
        import time
        time.sleep(2)
        
        # 检查进程
        result = subprocess.run(
            ["pgrep", "-f", "deconstruct_worker"],
            capture_output=True,
            text=True
        )
        started = result.returncode == 0
        
        return jsonify({
            "ok": True,
            "data": {
                "started": started,
                "message": "Worker 已重启" if started else "Worker 启动中..."
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
