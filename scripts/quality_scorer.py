import json
import os
import time

import requests

from scripts.env_loader import load_dotenv
from scripts.account_strategy import get_account_strategy, render_strategy_prompt, strategy_trace

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(BASE_DIR, ".env"))


SCORE_PROMPT = (
    "你是小红书内容质量评审专家。请严格输出 JSON，不要输出除 JSON 以外的任何内容。"
    "对给定的笔记内容进行六维评分，满分 100 分。"
    "JSON 格式："
    "{"
    "\"title_appeal\": 0-20,"
    "\"emotion_density\": 0-20,"
    "\"collection_value\": 0-20,"
    "\"interaction_guide\": 0-15,"
    "\"xhs_style_match\": 0-15,"
    "\"ai_trace\": 0-10,"
    "\"total\": 0-100,"
    "\"grade\": \"good|review|retry\","
    "\"suggestion\": \"一句话改进建议\","
    "\"suggestions\": ["
    "{\"dimension\":\"标题|前三行|收藏价值|评论钩子|账号策略|AI痕迹\","
    "\"problem\":\"发现的问题\","
    "\"action\":\"具体修改动作\","
    "\"reason\":\"判断依据\"}"
    "]"
    "}"
    "评分标准："
    "- title_appeal: 标题是否尖锐具体，包含题材/人群/爽点/反差/收益之一，0=平淡泛标题 20=忍不住点开"
    "- emotion_density: 前三行是否快速给结论并制造共鸣/好奇/站队，0=先铺剧情且无波澜 20=开头三行就能留人"
    "- collection_value: 是否让人想收藏，尤其是否有清晰阅读判断、拆解框架或避雷价值，0=毫无价值 20=干货/洞察力强"
    "- interaction_guide: 是否有具体评论钩子，二选一/站队/求投喂优先，0=没有引导或只写欢迎评论 15=读者顺手就能回复"
    "评论钩子不能只判断有没有，还要判断是否低门槛。低门槛优先级：1 报书名，2 求同款，3 雷点投票，4 二选一，5 求投喂。"
    "出现“欢迎评论”“评论区聊聊”“你怎么看”“大家怎么看”“喜欢就关注”必须在 interaction_guide 扣分。"
    "- xhs_style_match: 是否像真人写的小红书笔记，首图/标题/正文节奏是否原生，0=一眼AI 15=完全像真人"
    "- ai_trace: AI痕迹评分，分数越高表示AI痕迹越低（0=明显AI痕迹 10=毫无AI痕迹）"
    "- total: 六项加总"
    "- grade: total>=85→\"good\", total>=75→\"review\", total<75→\"retry\""
    "- suggestions: 仅输出最值得改的1-4条，必须结合账号策略、前三行、评论钩子、收藏价值或AI痕迹，不要泛泛而谈"
    "- 事实约束：suggestions 的 action 只能改写笔记中已经出现的事实、人物、设定和题材；"
    "不要新增笔记里没有的女主/男主/变异兽/基建/囤货/感情线等具体设定。"
    "如果笔记素材不足，只能建议补充资料或降低为简介快筛，不能脑补爽点。"
)


def _fact_check_prompt(fact_check):
    if not isinstance(fact_check, dict) or not fact_check:
        return ""
    usable = [str(x.get("text", "")) for x in fact_check.get("usable_facts", [])[:6] if isinstance(x, dict)]
    cautious = [str(x.get("text", "")) for x in fact_check.get("cautious_facts", [])[:6] if isinstance(x, dict)]
    return (
        "\n本次评分还需遵守素材证据卡："
        f"\n- generation_mode: {fact_check.get('generation_mode', '')}"
        f"\n- read_scope: {fact_check.get('read_scope', '')}"
        f"\n- usable_facts: {usable}"
        f"\n- cautious_facts: {cautious}"
        "\n如果 generation_mode=insufficient，评分建议只能围绕补充官方简介/试读/目录/书评、改成素材征集型标题、降低伪深度；"
        "不得建议加入证据卡没有的人物、设定、爽点、雷点或阅读结论。"
    )


def _sanitize_score_suggestions(result, note_text, fact_check=None):
    if not isinstance(result, dict):
        return result
    fact_check = fact_check if isinstance(fact_check, dict) else {}
    insufficient = fact_check.get("generation_mode") == "insufficient"
    forbidden = ["女主", "男主", "基建", "囤货", "感情线", "武力值", "不圣母", "圣母", "爽点太密"]
    if not insufficient:
        return result
    safe_action = "改成素材征集型：这本先不硬推，求看过的人补充开局、雷点和是否值得追。"
    cleaned = []
    for item in result.get("suggestions", []) if isinstance(result.get("suggestions"), list) else []:
        text = " ".join(str(item.get(k, "")) for k in ["problem", "action", "reason"])
        if any(word in text for word in forbidden):
            item = dict(item)
            item["action"] = safe_action
            item["reason"] = "当前证据卡显示素材不足，不能新增未验证的人设、爽点或雷点。"
        cleaned.append(item)
    if not cleaned:
        cleaned = [{
            "dimension": "素材",
            "problem": "当前笔记已经降级为素材不足提醒，不适合按正常推荐笔记优化。",
            "action": safe_action,
            "reason": "缺少可追溯官方简介、试读章节、目录或读者评论，不能伪装成深度拆书。",
        }]
    result["suggestions"] = cleaned[:4]
    result["suggestion"] = "素材不足时应先补证据卡，或改成素材征集型笔记，不能脑补推荐点。"
    result["grade"] = "retry"
    result["total"] = min(int(result.get("total") or 0), 60)
    return result


def score_note(note_text, account_strategy=None, fact_check=None):
    """对笔记进行六维质量评分，返回 dict"""
    account_strategy = account_strategy or get_account_strategy()
    provider = os.getenv("MODEL_PROVIDER", "zhipu").strip().lower()
    if provider == "local":
        return _default_score("MODEL_PROVIDER=local，跳过远端评分")
    is_qwen = provider in {"qwen", "dashscope"}
    is_deepseek = provider == "deepseek"

    if is_qwen:
        api_key = os.getenv("QWEN_API_KEY", "").strip()
    elif is_deepseek:
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    else:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return _default_score("API Key 未配置")

    if is_qwen:
        model = os.getenv("QWEN_MODEL", "").strip() or os.getenv("OPENAI_MODEL", "qwen-plus").strip()
    elif is_deepseek:
        model = os.getenv("DEEPSEEK_MODEL", "").strip() or os.getenv("OPENAI_MODEL", "deepseek-chat").strip()
    else:
        model = os.getenv("OPENAI_MODEL", "glm-4-plus").strip()
    endpoints = _score_endpoints(provider)

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    SCORE_PROMPT
                    + "\n本次评分还需参考账号策略：\n"
                    + render_strategy_prompt(account_strategy)
                    + _fact_check_prompt(fact_check)
                ),
            },
            {"role": "user", "content": f"请评分以下笔记内容：\n\n{note_text[:3000]}"},
        ],
        "temperature": 0.1,
        "max_tokens": 900,
    }

    last_error = None
    for attempt in range(3):
        for base_url, endpoint_key in endpoints:
            if not endpoint_key:
                continue
            try:
                resp = requests.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {endpoint_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=60,
                )
                if resp.status_code >= 400:
                    last_error = _format_http_error(resp, base_url)
                    continue
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                # Extract JSON
                start = content.find("{")
                end = content.rfind("}") + 1
                if start >= 0 and end > start:
                    result = json.loads(content[start:end])
                    result.setdefault("total", sum([
                        result.get("title_appeal", 0),
                        result.get("emotion_density", 0),
                        result.get("collection_value", 0),
                        result.get("interaction_guide", 0),
                        result.get("xhs_style_match", 0),
                        result.get("ai_trace", 0),
                    ]))
                    result.setdefault("grade", _calc_grade(result.get("total", 0)))
                    result.setdefault("suggestion", "")
                    result.setdefault("suggestions", [])
                    if not isinstance(result["suggestions"], list):
                        result["suggestions"] = []
                    result.setdefault("strategy_trace", strategy_trace(account_strategy))
                    return _sanitize_score_suggestions(result, note_text, fact_check=fact_check)
                last_error = "评分模型未返回 JSON"
            except Exception as e:
                last_error = str(e)
        if attempt < 2:
            time.sleep(1 * (attempt + 1))
    return _default_score(f"评分失败: {last_error or '未知错误'}")


def _score_endpoints(provider):
    is_qwen = provider in {"qwen", "dashscope"}
    if provider == "deepseek":
        base = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
        key = os.getenv("DEEPSEEK_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
        return [(base, key)]

    if not is_qwen:
        base = os.getenv("OPENAI_BASE_URL", "https://open.bigmodel.cn/api/paas/v4").strip().rstrip("/")
        return [(base, os.getenv("OPENAI_API_KEY", "").strip())]

    api_key = os.getenv("QWEN_API_KEY", "").strip()
    api_key_intl = os.getenv("QWEN_API_KEY_INTL", "").strip()
    raw_urls = os.getenv("QWEN_BASE_URLS", "").strip()
    if raw_urls:
        base_urls = [u.strip().rstrip("/") for u in raw_urls.split(",") if u.strip()]
    else:
        base_urls = []
        qwen_base = os.getenv("QWEN_BASE_URL", "").strip()
        if qwen_base:
            base_urls.append(qwen_base.rstrip("/"))
        if "https://dashscope.aliyuncs.com/compatible-mode/v1" not in base_urls:
            base_urls.append("https://dashscope.aliyuncs.com/compatible-mode/v1")
        if "https://dashscope-intl.aliyuncs.com/compatible-mode/v1" not in base_urls:
            base_urls.append("https://dashscope-intl.aliyuncs.com/compatible-mode/v1")

    endpoints = []
    for base_url in base_urls:
        endpoint_key = api_key_intl if "dashscope-intl" in base_url and api_key_intl else api_key
        endpoints.append((base_url, endpoint_key))
    return endpoints


def _format_http_error(resp, base_url):
    detail = ""
    try:
        payload = resp.json()
        err = payload.get("error") or {}
        code = err.get("code") or err.get("type") or ""
        message = err.get("message") or ""
        detail = f"{code}: {message}".strip(": ")
    except Exception:
        detail = (resp.text or "")[:300]
    return f"{base_url} HTTP {resp.status_code}: {detail}"


def _calc_grade(total):
    if total >= 85:
        return "good"
    # 75分以上直接通过，不进入待审核状态（拆解完成即 done）
    if total >= 75:
        return "good"
    return "retry"


def _default_score(reason):
    return {
        "title_appeal": 0,
        "emotion_density": 0,
        "collection_value": 0,
        "interaction_guide": 0,
        "xhs_style_match": 0,
        "ai_trace": 0,
        "total": 0,
        "grade": "retry",
        "suggestion": reason,
        "suggestions": [{
            "dimension": "评分",
            "problem": reason,
            "action": "检查模型配置或稍后重新评分",
            "reason": "质量评分未能完成，当前建议来自系统降级逻辑",
        }],
        "_fallback": True,
    }
