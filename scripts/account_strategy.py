import copy
import json
import os


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CONFIG_PATH = os.path.join(BASE_DIR, "data", "config", "account_strategies.json")


DEFAULT_STRATEGIES = {
    "xhs_default": {
        "id": "xhs_default",
        "name": "小红书通用策略",
        "positioning": "面向小红书图文内容的通用发布策略",
        "target_audience": ["小红书泛内容读者"],
        "content_pillars": ["具体标题", "首屏结论", "收藏价值", "低门槛互动"],
        "title_formulas": [
            {"name": "痛点型", "template": "{pain_point}？先看这篇"},
            {"name": "收益型", "template": "{category}一篇讲清楚"},
            {"name": "反差型", "template": "{hook}，结果更上头"},
            {"name": "搜索长尾型", "template": "{category}新手必看"},
            {"name": "互动型", "template": "{category}你更想看哪种"},
        ],
        "cover_rules": {
            "main_title_max_len": 16,
            "subtitle_max_len": 24,
            "style": "大字标题，信息一眼可读，避免堆满细节",
        },
        "opening_rules": [
            "第一行直接给结论或适合谁",
            "第二行给最大看点、冲突或收益",
            "第三行给收藏理由或行动判断",
        ],
        "cta_rules": [
            "只问一个具体问题",
            "优先二选一、站队、求补充",
            "避免欢迎评论、大家怎么看等泛互动",
        ],
        "quality_focus": [
            "标题具体",
            "前三行留人",
            "收藏理由明确",
            "评论钩子低门槛",
            "真人语气",
        ],
        "forbidden_patterns": ["私信", "加群", "站外链接", "欢迎评论"],
        "benchmark_accounts": [],
    },
    "yuanzi_webnovel": {
        "id": "yuanzi_webnovel",
        "name": "和圆子一起看网文",
        "positioning": "女性向网文推荐与拆解账号，帮书荒读者快速判断一本书值不值得追",
        "target_audience": ["书荒读者", "女性向网文读者", "喜欢爽点/人设/反差判断的读者"],
        "content_pillars": ["书荒场景", "题材长尾词", "爽点判断", "避雷价值", "评论区求投喂"],
        "title_formulas": [
            {"name": "痛点型", "template": "{pain_point}？这本{category}给答案"},
            {"name": "爽点型", "template": "这本{category}爽点太密了"},
            {"name": "反差型", "template": "{hook}，居然写成了爽文"},
            {"name": "搜索长尾型", "template": "书荒必看{category}推荐"},
            {"name": "互动求投喂型", "template": "{category}党求投喂同款"},
        ],
        "cover_rules": {
            "main_title_max_len": 16,
            "subtitle_max_len": 24,
            "style": "网文大字报，主标题短狠，副标题补充题材和阅读收益",
        },
        "opening_rules": [
            "第一行说明适合哪类书荒读者或值不值得看",
            "第二行给最强爽点、反差或人设钩子",
            "第三行告诉读者收藏后能判断什么",
        ],
        "cta_rules": [
            "围绕书名、题材偏好或同款求投喂提问",
            "优先二选一、站队、求投喂书单",
            "避免只写欢迎评论或聊聊",
        ],
        "quality_focus": [
            "题材和爽点要具体",
            "首图像大字报",
            "前三行先给阅读判断",
            "收藏价值要像书单/避雷/判断工具",
            "评论钩子能让读者顺手报书名",
        ],
        "forbidden_patterns": ["私信", "加群", "站外链接", "晋江", "起点", "番茄", "欢迎评论"],
        "benchmark_accounts": [
            "Alexayal看文记录",
            "元宝的读书笔记",
            "一只订书机",
            "阿宁的书架",
        ],
    },
}


def _deep_merge(base, override):
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_account_strategies():
    strategies = copy.deepcopy(DEFAULT_STRATEGIES)
    current_id = os.getenv("ACCOUNT_STRATEGY_ID", "yuanzi_webnovel").strip() or "yuanzi_webnovel"
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
            current_id = str(data.get("current") or current_id).strip() or current_id
            for item in data.get("strategies", []):
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                sid = str(item["id"]).strip()
                strategies[sid] = _deep_merge(strategies.get(sid, {}), item)
        except Exception:
            pass
    return {"current": current_id, "strategies": strategies}


def save_current_account_strategy(strategy_id):
    data = load_account_strategies()
    sid = str(strategy_id or "").strip()
    if sid not in data["strategies"]:
        raise ValueError(f"unknown account strategy: {sid}")
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    payload = {
        "current": sid,
        "strategies": list(data["strategies"].values()),
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return get_account_strategy(sid)


def get_account_strategy(strategy_id=None):
    data = load_account_strategies()
    sid = str(strategy_id or data["current"] or "yuanzi_webnovel").strip()
    strategies = data["strategies"]
    strategy = strategies.get(sid) or strategies.get("xhs_default")
    return copy.deepcopy(strategy)


def render_strategy_prompt(strategy):
    if not strategy:
        return ""
    cover = strategy.get("cover_rules") or {}
    lines = [
        f"账号策略：{strategy.get('name', '')}",
        f"账号定位：{strategy.get('positioning', '')}",
        f"目标读者：{'、'.join(strategy.get('target_audience') or [])}",
        f"内容支柱：{'、'.join(strategy.get('content_pillars') or [])}",
        f"封面规则：主标题≤{cover.get('main_title_max_len', 16)}字，副标题≤{cover.get('subtitle_max_len', 24)}字；{cover.get('style', '')}",
        f"前三行规则：{'；'.join(strategy.get('opening_rules') or [])}",
        f"评论钩子规则：{'；'.join(strategy.get('cta_rules') or [])}",
        f"质量重点：{'、'.join(strategy.get('quality_focus') or [])}",
        f"禁用表达：{'、'.join(strategy.get('forbidden_patterns') or [])}",
    ]
    formulas = []
    for formula in strategy.get("title_formulas") or []:
        if isinstance(formula, dict):
            formulas.append(f"{formula.get('name', '')}: {formula.get('template', '')}")
    if formulas:
        lines.append(f"标题公式：{'；'.join(formulas)}")
    return "\n".join(line for line in lines if line.strip())


def strategy_trace(strategy):
    return {
        "id": strategy.get("id", ""),
        "name": strategy.get("name", ""),
        "positioning": strategy.get("positioning", ""),
        "benchmark_accounts": strategy.get("benchmark_accounts", []),
        "quality_focus": strategy.get("quality_focus", []),
    }
