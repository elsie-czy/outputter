import json
import os
import time

import requests

from scripts.env_loader import load_dotenv

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
    "\"suggestion\": \"一句话改进建议\""
    "}"
    "评分标准："
    "- title_appeal: 标题是否抓人眼球，0=平淡 20=忍不住点开"
    "- emotion_density: 是否有共鸣/好奇心/情绪钩子，0=毫无波澜 20=情绪饱满"
    "- collection_value: 是否让人想收藏，0=毫无价值 20=干货/洞察力强"
    "- interaction_guide: 是否有钩子引导评论互动，0=没有引导 15=强烈互动引导"
    "- xhs_style_match: 是否像真人写的笔记而非AI生成，0=一眼AI 15=完全像真人"
    "- ai_trace: AI痕迹评分，分数越高表示AI痕迹越低（0=明显AI痕迹 10=毫无AI痕迹）"
    "- total: 六项加总"
    "- grade: total>=85→\"good\", total>=75→\"review\", total<75→\"retry\""
)


def score_note(note_text):
    """对笔记进行六维质量评分，返回 dict"""
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
            {"role": "system", "content": SCORE_PROMPT},
            {"role": "user", "content": f"请评分以下笔记内容：\n\n{note_text[:3000]}"},
        ],
        "temperature": 0.1,
        "max_tokens": 500,
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
                    return result
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
        "_fallback": True,
    }
