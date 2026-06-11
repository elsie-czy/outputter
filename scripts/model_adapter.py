import json
import os
import re
import time
from datetime import datetime

import requests


def _local_analyze(work):
    name = work.get("作品名称", "")
    author = work.get("作者", "")
    platform = work.get("平台", "")
    category = work.get("分类", "")

    # Minimal deterministic placeholders to keep pipeline running.
    return {
        "开篇套路": [
            f"以高强度冲突开场，快速交代主角处境（{name}）",
            "先给读者一个强钩子问题或悬念",
            "用倒叙或片段式开场制造信息差",
        ],
        "人物设定": {
            "女主": f"目标感强、行动派；与既有身份形成反差（{category}）",
            "男主": "强势/稀缺资源位，掌握关键选择权",
            "亮点配角": "推动冲突升级的关键触发角色",
        },
        "冲突设计": {
            "第一层": "目标与现实阻力冲突",
            "第二层": "价值观/关系选择冲突",
            "第三层": "身份/命运层面的根本冲突",
        },
        "情绪触发": ["爽感", "期待", "心疼"],
        "金句": [
            "我不是来求你给路，我是来把路走出来的。",
            "所有选择，都要为现在的自己负责。",
            "当你决定开始，命运就已经改变。",
            "最狠的报复，是把自己活成想要的样子。",
            "人心最难，是对自己诚实。",
        ],
        "小红书包装": {
            "小红书标题模板": f"{name}：开篇三步把人拉进坑",
            "封面图描述建议": "大字标题+人物剪影+高对比色",
            "热门标签推荐": ["#网文拆解", "#写作套路", "#爆款基因"],
            "正文开头模板": "一句话总结 + 三个爆点预告",
            "正文结构建议": "开篇钩子-人物设定-三层冲突-金句总结",
            "互动话术模板": "你更吃哪种开篇套路？评论区聊聊",
            "受众画像关键词": ["写作者", "内容创作者", "网文爱好者"],
            "内容类型标签": ["拆解", "方法论"],
            "最佳发布时间建议": "工作日午休或晚间 20-22 点",
            "情绪基调": "高能/爽感",
            "视觉风格建议": "干净留白+红黑对比",
            "话题挑战建议": "#三步拆开篇",
            "爆款潜力评分": "中",
            "内容扩展方向": "不同平台开篇套路对比",
            "发布时间记录": datetime.now().strftime("%Y-%m-%d"),
        },
        "配图提示词": [
            "小红书竖版封面，比例3:4，动漫风，女主修真者半身像，红黑高对比，标题留白，细节精致，高清插画",
            "小红书竖版配图，比例3:4，动漫风，宗门大殿夜色场景，群像构图，戏剧光影，电影感，高清插画",
            "小红书竖版配图，比例3:4，动漫风，女主与师侄对峙场面，动作张力，动态线条，高清插画",
            "小红书竖版配图，比例3:4，动漫风，掌门炖鹅的反差喜剧场景，明快配色，轻松氛围，高清插画",
            "小红书竖版配图，比例3:4，动漫风，最终团战群像，热血高能，火焰特效，高清插画",
        ],
        "元信息": {
            "来源": "local_template",
            "平台": platform,
            "分类": category,
            "作者": author,
        },
    }


def _ensure_analysis_shape(result, work):
    result = result or {}
    result.setdefault("开篇套路", ["", "", ""])
    if len(result["开篇套路"]) < 3:
        result["开篇套路"] = (result["开篇套路"] + ["", "", ""])[:3]

    result.setdefault("人物设定", {})
    for k in ["女主", "男主", "亮点配角"]:
        result["人物设定"].setdefault(k, "")

    result.setdefault("冲突设计", {})
    for k in ["第一层", "第二层", "第三层"]:
        result["冲突设计"].setdefault(k, "")

    result.setdefault("情绪触发", ["", "", ""])
    if len(result["情绪触发"]) < 3:
        result["情绪触发"] = (result["情绪触发"] + ["", "", ""])[:3]

    result.setdefault("金句", ["", "", "", "", ""])
    if len(result["金句"]) < 5:
        result["金句"] = (result["金句"] + ["", "", "", "", ""])[:5]

    result.setdefault("小红书包装", {})
    p = result["小红书包装"]
    p.setdefault("小红书标题模板", "")
    p.setdefault("封面图描述建议", "")
    p.setdefault("热门标签推荐", [])
    p.setdefault("正文开头模板", "")
    p.setdefault("正文结构建议", "")
    p.setdefault("互动话术模板", "")
    p.setdefault("受众画像关键词", [])
    p.setdefault("内容类型标签", [])
    p.setdefault("最佳发布时间建议", "")
    p.setdefault("情绪基调", "")
    p.setdefault("视觉风格建议", "")
    p.setdefault("话题挑战建议", "")
    p.setdefault("爆款潜力评分", "")
    p.setdefault("内容扩展方向", "")
    p.setdefault("发布时间记录", datetime.now().strftime("%Y-%m-%d"))

    prompts = result.get("配图提示词", [])
    if not isinstance(prompts, list):
        prompts = [str(prompts)] if prompts else []
    prompts = [str(x).strip() for x in prompts if str(x).strip()]
    if len(prompts) < 4:
        prompts.extend(
            [
                "小红书竖版配图，比例3:4，动漫风，人物特写，高清插画",
                "小红书竖版配图，比例3:4，动漫风，剧情冲突场面，高清插画",
                "小红书竖版配图，比例3:4，动漫风，群像构图，高清插画",
                "小红书竖版配图，比例3:4，动漫风，氛围场景，高清插画",
            ]
        )
    result["配图提示词"] = prompts[:5]

    result.setdefault("元信息", {})
    result["元信息"].setdefault("来源", "openai")
    result["元信息"].setdefault("平台", work.get("平台", ""))
    result["元信息"].setdefault("分类", work.get("分类", ""))
    result["元信息"].setdefault("作者", work.get("作者", ""))
    return result


def analyze_work(work, reference_notes=None):
    provider = os.getenv("MODEL_PROVIDER", "local").strip().lower()
    if provider == "local":
        return _local_analyze(work)
    # OpenAI-compatible providers (chatglm/qwen/deepseek/moonshot, etc.)
    if provider in {
        "openai",
        "chatglm",
        "glm",
        "zhipu",
        "qwen",
        "dashscope",
        "deepseek",
        "moonshot",
        "kimi",
    }:
        return _openai_analyze(work, reference_notes)
    if provider == "ernie":
        raise RuntimeError("MODEL_PROVIDER=ernie 尚未接入。")
    raise RuntimeError(f"未知的 MODEL_PROVIDER: {provider}")


def _openai_analyze(work, reference_notes=None):
    provider = os.getenv("MODEL_PROVIDER", "openai").strip().lower()
    is_qwen = provider in {"qwen", "dashscope"}
    api_key = (os.getenv("QWEN_API_KEY", "") if is_qwen else os.getenv("OPENAI_API_KEY", "")).strip()
    api_key_intl = os.getenv("QWEN_API_KEY_INTL", "").strip() if is_qwen else ""
    if not api_key and not api_key_intl:
        raise RuntimeError("模型 API_KEY 未设置")

    model_default = "qwen-plus" if is_qwen else "gpt-4o-mini"
    model = (os.getenv("QWEN_MODEL", "") if is_qwen else "").strip() or os.getenv("OPENAI_MODEL", model_default).strip()

    if is_qwen:
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
    else:
        base_default = "https://api.openai.com/v1"
        base_urls = [os.getenv("OPENAI_BASE_URL", base_default).strip().rstrip("/")]

    system_prompt = (
        "你是资深网文拆解专家。请严格输出 JSON，不要输出除 JSON 以外的任何内容。"
        "Return valid json only."
        "JSON 字符串中禁止出现未转义的英文双引号（\"）。如需引号，请使用中文引号“”或改写表达。"
        "风格要求：小红书可直接发布，语言自然有网感，避免空泛套话。"
        "内容合规要求：禁止出现导流私信、联系方式、平台外跳转、夸张医疗或违规承诺等违反小红书社区规范的内容。"
        "输出字段必须包含以下结构："
        "{"
        "\"开篇套路\": [string,string,string],"
        "\"人物设定\": {\"女主\":string,\"男主\":string,\"亮点配角\":string},"
        "\"冲突设计\": {\"第一层\":string,\"第二层\":string,\"第三层\":string},"
        "\"情绪触发\": [string,string,string],"
        "\"金句\": [string,string,string,string,string],"
        "\"小红书包装\": {"
        "\"小红书标题模板\":string,"
        "\"封面图描述建议\":string,"
        "\"热门标签推荐\":[string,string,string],"
        "\"正文开头模板\":string,"
        "\"正文结构建议\":string,"
        "\"互动话术模板\":string,"
        "\"受众画像关键词\":[string,string,string],"
        "\"内容类型标签\":[string,string],"
        "\"最佳发布时间建议\":string,"
        "\"情绪基调\":string,"
        "\"视觉风格建议\":string,"
        "\"话题挑战建议\":string,"
        "\"爆款潜力评分\":string,"
        "\"内容扩展方向\":string,"
        "\"发布时间记录\":string"
        "},"
        "\"配图提示词\":[string,string,string,string,string],"
        "\"元信息\": {\"来源\":string,\"平台\":string,\"分类\":string,\"作者\":string}"
        "}"
    )

    user_prompt = {
        "任务": "根据作品信息进行网文拆解与爆款基因提取",
        "作品信息": work,
        "要求": [
            "开篇套路至少3条且具体",
            "人物设定三类均必填且具体",
            "冲突设计三层均必填且具体",
            "情绪触发至少3类",
            "金句至少5条，尽量有写作价值",
            "小红书包装字段全部必填，可发布",
            "小红书包装文案要有明显钩子、对比、结论，不要写成学术报告",
            "正文开头模板和互动话术模板要带平台语气，可包含少量emoji",
            "热门标签推荐要贴近题材，不要泛泛标签",
            "明确规避小红书违规表达：不能引导私信、不能留联系方式、不能导流站外平台",
            "配图提示词输出4-5条，每条都必须包含：小红书竖版比例3:4、动漫风优先、具体人物/场景/光影细节",
        ],
    }

    # Few-shot: 注入历史爆款笔记作为风格参考
    if reference_notes:
        ref_lines = []
        for i, ref in enumerate(reference_notes[:3], 1):
            title = ref.get("标题", "")
            labels = ref.get("标签", "")
            body = ref.get("正文", "")
            likes = ref.get("点赞", 0)
            collects = ref.get("收藏", 0)
            ref_lines.append(
                f"参考笔记{i}（点赞{likes} 收藏{collects}）：\n"
                f"标题：{title}\n标签：{labels}\n正文：{body}\n"
            )
        user_prompt["参考笔记（请模仿其风格和结构，但内容针对当前作品）"] = ref_lines

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
        "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.3")),
        "max_tokens": 2000,
    }
    disable_resp_fmt = os.getenv("OPENAI_DISABLE_RESPONSE_FORMAT", "").strip().lower() in [
        "1",
        "true",
        "yes",
    ]
    if provider not in {"zhipu", "chatglm", "glm"} and not disable_resp_fmt:
        payload["response_format"] = {"type": "json_object"}

    max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "5"))
    backoff = float(os.getenv("OPENAI_RETRY_BASE", "1.5"))
    max_sleep = float(os.getenv("OPENAI_RETRY_MAX", "20"))

    last_err = None
    for attempt in range(max_retries):
        for base_url in base_urls:
            try:
                endpoint_key = api_key
                if is_qwen and "dashscope-intl" in base_url:
                    endpoint_key = api_key_intl or api_key
                if not endpoint_key:
                    continue
                url = f"{base_url}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {endpoint_key}",
                    "Content-Type": "application/json",
                }
                resp = requests.post(url, headers=headers, json=payload, timeout=60)
                if resp.status_code in [429, 500, 502, 503, 504]:
                    last_err = f"{base_url} HTTP {resp.status_code}: {resp.text}"
                    continue
                resp.raise_for_status()
                data = resp.json()
                break
            except Exception as e:
                last_err = f"{base_url} {e}"
                continue
        else:
            sleep_s = min(max_sleep, backoff ** (attempt + 1))
            time.sleep(sleep_s)
            continue
        break
    else:
        raise RuntimeError(f"OpenAI 请求失败: {last_err}")
    content = data["choices"][0]["message"]["content"]

    def _fix_json_quotes(text):
        # Heuristic: escape unescaped quotes inside string values.
        s = str(text or "")
        out = []
        in_str = False
        escape = False
        n = len(s)
        for i, ch in enumerate(s):
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == "\"":
                if not in_str:
                    out.append(ch)
                    in_str = True
                    continue
                # in_str: decide if this is closing quote by peeking ahead
                j = i + 1
                while j < n and s[j].isspace():
                    j += 1
                if j >= n or s[j] in [",", "}", "]", ":"]:
                    out.append(ch)
                    in_str = False
                else:
                    out.append("\\\"")
                continue
            out.append(ch)
        return "".join(out)

    def _fix_json_control_chars(text):
        # Escape control chars inside strings; replace others with spaces.
        s = str(text or "")
        out = []
        in_str = False
        escape = False
        for ch in s:
            if escape:
                out.append(ch)
                escape = False
                continue
            if ch == "\\":
                out.append(ch)
                escape = True
                continue
            if ch == "\"":
                out.append(ch)
                in_str = not in_str
                continue
            if in_str and ch in ["\n", "\r", "\t"]:
                out.append("\\n" if ch in ["\n", "\r"] else "\\t")
                continue
            # Remove other control chars
            if ord(ch) < 32 and ch not in ["\n", "\r", "\t"]:
                out.append(" ")
                continue
            out.append(ch)
        return "".join(out)

    try:
        result = json.loads(content)
    except Exception:
        text = str(content).strip()
        m = re.search(r"```json\s*(\{[\s\S]*\})\s*```", text, flags=re.IGNORECASE)
        if m:
            text = m.group(1).strip()
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                text = text[start : end + 1]
        # If content is double-escaped (e.g., \\n, \\"), unescape safely.
        if "\\n" in text or "\\\"" in text or "\\\\" in text:
            text = (
                text.replace("\\\\", "\\")
                .replace('\\"', '"')
                .replace("\\n", "\n")
                .replace("\\t", "\t")
            )
        # Normalize Chinese quotes/colons and stray escaped newlines/tabs.
        text = re.sub(r'[\"“”]([^\"“”]+)[\"“”]\s*[:：]', r'"\1":', text)
        text = text.replace("“", "\"").replace("”", "\"")
        text = text.replace("：", ":")
        text = text.replace("\\n", "").replace("\\t", " ")
        # Fix common invalid quote cases and control characters inside strings.
        text = _fix_json_quotes(text)
        text = _fix_json_control_chars(text)
        try:
            result = json.loads(text)
        except Exception as e:
            try:
                from scripts.config import PATHS
                from scripts.utils import append_jsonl, now_ts

                append_jsonl(
                    os.path.join(PATHS["logs"], "model_parse_errors.jsonl"),
                    {
                        "ts": now_ts(),
                        "provider": provider,
                        "model": model,
                        "error": str(e),
                        "content_snippet": text[:800],
                    },
                )
                if os.getenv("MODEL_LOG_RAW", "").strip().lower() in ["1", "true", "yes"]:
                    append_jsonl(
                        os.path.join(PATHS["logs"], "model_raw_outputs.jsonl"),
                        {
                            "ts": now_ts(),
                            "provider": provider,
                            "model": model,
                            "error": str(e),
                            "content": text,
                        },
                    )
            except Exception:
                pass
            fallback = _local_analyze(work)
            fallback["元信息"]["来源"] = f"openai_parse_fallback:{e}"
            return _ensure_analysis_shape(fallback, work)

    return _ensure_analysis_shape(result, work)
