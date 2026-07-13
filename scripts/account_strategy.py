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
        "note_types": {
            "normal_recommendation": {
                "label": "正常单本推荐",
                "ratio": 0.7,
                "goal": "收藏、搜索长尾、稳定涨粉",
            },
            "comment_experiment": {
                "label": "求投喂/书荒互助",
                "ratio": 0.2,
                "goal": "拉评论、激活账号",
            },
            "warning_review": {
                "label": "避雷/争议判断",
                "ratio": 0.1,
                "goal": "拉点击和讨论",
            },
            "booklist": {
                "label": "书单合集",
                "goal": "提高收藏和搜索长尾",
            },
        },
        "opening_templates": {
            "strong_recommend": [
                "这本适合想看「{genre_hook}」的姐妹。",
                "我最吃的是「{specific_hook}」，不是那种「{common_thunder}」。",
                "如果你最近书荒，可以先试前 10 章。",
            ],
            "warning_reversal": [
                "我一开始差点把这本划走，因为「{apparent_risk}」。",
                "但看下去发现「{reversal_hook}」还挺稳。",
                "介意「{real_threshold}」的先慎入，能吃这个点的可以试试。",
            ],
            "book_shortage_rescue": [
                "书荒的时候，这种「{genre}」真的很好用。",
                "不用动太多脑子，爽点就在「{specific_hook}」。",
                "想找「{search_keyword}」的，可以先把这本放进待看。",
            ],
            "audience_filter": [
                "想看「{preference_a}」但怕又是空壳设定的，可以先停一下。",
                "这本抓人的点是「{specific_hook}」。",
                "重点看规则、代价和破局目标，少一个都容易水。",
            ],
            "rant_entry": [
                "我真的受不了那种「{common_thunder}」的末世文。",
                "所以这本让我舒服的点很简单：「{anti_thunder_hook}」。",
                "女主「{specific_behavior}」，看着就很省心。",
            ],
        },
        "cover_templates": {
            "normal_recommendation": {
                "main_title_max_len": 8,
                "subtitle_max_len": 12,
                "examples": ["末世种田文\n这本能追", "女主清醒\n基建很安心"],
            },
            "warning_review": {
                "main_title_max_len": 8,
                "subtitle_max_len": 12,
                "examples": ["末世文避雷\n但这本能看", "女主不圣母\n靠本事吃饭"],
            },
            "comment_experiment": {
                "main_title_max_len": 8,
                "subtitle_max_len": 14,
                "examples": ["求投喂！\n女主不圣母的\n末世文"],
            },
        },
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
        "note_types": {
            "normal_recommendation": {
                "label": "正常单本推荐",
                "ratio": 0.7,
                "goal": "收藏、搜索长尾、稳定涨粉",
            },
            "comment_experiment": {
                "label": "求投喂/书荒互助",
                "ratio": 0.2,
                "goal": "拉评论、激活账号",
            },
            "warning_review": {
                "label": "避雷/争议判断",
                "ratio": 0.1,
                "goal": "拉点击和讨论",
            },
            "booklist": {
                "label": "书单合集",
                "goal": "提高收藏和搜索长尾",
            },
        },
        "opening_templates": {
            "strong_recommend": [
                "这本适合想看「{genre_hook}」的姐妹。",
                "我最吃的是「{specific_hook}」，不是那种「{common_thunder}」。",
                "如果你最近书荒，可以先试前 10 章。",
            ],
            "warning_reversal": [
                "我一开始差点把这本划走，因为「{apparent_risk}」。",
                "但看下去发现「{reversal_hook}」还挺稳。",
                "介意「{real_threshold}」的先慎入，能吃这个点的可以试试。",
            ],
            "book_shortage_rescue": [
                "书荒的时候，这种「{genre}」真的很好用。",
                "不用动太多脑子，爽点就在「{specific_hook}」。",
                "想找「{search_keyword}」的，可以先把这本放进待看。",
            ],
            "audience_filter": [
                "想看「{preference_a}」但怕又是空壳设定的，可以先停一下。",
                "这本抓人的点是「{specific_hook}」。",
                "重点看规则、代价和破局目标，少一个都容易水。",
            ],
            "rant_entry": [
                "我真的受不了那种「{common_thunder}」的末世文。",
                "所以这本让我舒服的点很简单：「{anti_thunder_hook}」。",
                "女主「{specific_behavior}」，看着就很省心。",
            ],
        },
        "cover_templates": {
            "normal_recommendation": {
                "main_title_max_len": 8,
                "subtitle_max_len": 12,
                "examples": ["末世种田文\n这本能追", "女主清醒\n基建很安心"],
            },
            "warning_review": {
                "main_title_max_len": 8,
                "subtitle_max_len": 12,
                "examples": ["末世文避雷\n但这本能看", "女主不圣母\n靠本事吃饭"],
            },
            "comment_experiment": {
                "main_title_max_len": 8,
                "subtitle_max_len": 14,
                "examples": ["求投喂！\n女主不圣母的\n末世文"],
            },
        },
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
    note_types = strategy.get("note_types") or {}
    if isinstance(note_types, dict) and note_types:
        rendered = []
        for key, item in note_types.items():
            if isinstance(item, dict):
                rendered.append(f"{key}={item.get('label', '')}，目标：{item.get('goal', '')}")
        if rendered:
            lines.append(f"笔记类型：{'；'.join(rendered)}")
    opening_templates = strategy.get("opening_templates") or {}
    if isinstance(opening_templates, dict) and opening_templates:
        lines.append("前三行模板类型：" + "；".join(opening_templates.keys()))
    cover_templates = strategy.get("cover_templates") or {}
    if isinstance(cover_templates, dict) and cover_templates:
        rendered = []
        for key, item in cover_templates.items():
            if isinstance(item, dict):
                examples = " / ".join(item.get("examples") or [])
                rendered.append(f"{key}: 主≤{item.get('main_title_max_len', 8)}，副≤{item.get('subtitle_max_len', 12)}，例：{examples}")
        if rendered:
            lines.append(f"封面大字报模板：{'；'.join(rendered)}")
    return "\n".join(line for line in lines if line.strip())


def strategy_trace(strategy):
    return {
        "id": strategy.get("id", ""),
        "name": strategy.get("name", ""),
        "positioning": strategy.get("positioning", ""),
        "benchmark_accounts": strategy.get("benchmark_accounts", []),
        "quality_focus": strategy.get("quality_focus", []),
    }
