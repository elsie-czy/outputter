import os
import subprocess
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
