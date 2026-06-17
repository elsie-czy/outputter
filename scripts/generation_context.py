def build_generation_context(task=None, reference_limit=3, feedback_limit=5):
    """Collect optional model context without making generation depend on Feishu."""
    reference_notes = []
    recent_feedback = []

    current_feedback = _feedback_from_task(task, limit=feedback_limit)
    if current_feedback:
        recent_feedback.extend(current_feedback)

    try:
        from scripts.feishu_client import FeishuClient

        client = FeishuClient()
        if client.is_configured():
            reference_notes = client.get_top_notes(limit=reference_limit) or []
            remaining = max(feedback_limit - len(recent_feedback), 0)
            if remaining:
                recent_feedback.extend(client.get_recent_modifications(limit=remaining) or [])
    except Exception:
        pass

    return {
        "reference_notes": reference_notes[:reference_limit],
        "recent_feedback": recent_feedback[:feedback_limit],
    }


def context_counts(context):
    context = context or {}
    return {
        "reference_notes": len(context.get("reference_notes") or []),
        "recent_feedback": len(context.get("recent_feedback") or []),
    }


def _feedback_from_task(task, limit=5):
    if not task:
        return []
    log = str(task.get("modification_log") or "").strip()
    if not log:
        return []

    feedback = []
    for line in reversed(log.splitlines()):
        line = line.strip()
        if not line:
            continue
        parsed = _parse_feedback_line(line)
        if parsed:
            feedback.append(parsed)
        if len(feedback) >= limit:
            break
    return feedback


def _parse_feedback_line(line):
    parts = [p.strip() for p in str(line or "").split("|")]
    if len(parts) < 2:
        return None
    return {
        "time": parts[0],
        "field": parts[1],
        "reason": parts[2] if len(parts) > 2 else "",
    }
