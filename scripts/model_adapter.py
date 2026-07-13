import json
import os
import re
import time
from datetime import datetime

import requests

from scripts.account_strategy import get_account_strategy, render_strategy_prompt, strategy_trace


CONTENT_BRIEF_DEFAULT = {
    "目标人群": [],
    "核心痛点": "",
    "读者收益": "",
    "标题候选": [],
    "封面钩子": {
        "主标题": "",
        "副标题": "",
        "情绪": "",
        "点击理由": "",
    },
    "图文页结构": [],
    "证据素材": [],
    "禁用表达": [],
}

VISUAL_STORYBOARD_DEFAULT = [
    {
        "页码": 1,
        "作用": "封面",
        "剧情依据": "基于作品简介中的主角处境和核心冲突。",
        "画面主体": "主角半身像",
        "场景": "与作品题材匹配的关键场景",
        "动作": "直面冲突",
        "情绪": "强钩子/好奇",
        "避免": "不要出现文字、书名、平台名或未被简介支撑的人物关系。",
        "英文画面提示词": "vertical 3:4 anime illustration, expressive protagonist portrait in a story-specific key scene, cinematic lighting, strong emotional hook, no text, no words, no letters",
    },
    {
        "页码": 2,
        "作用": "世界观",
        "剧情依据": "基于作品简介中的题材、环境和开篇设定。",
        "画面主体": "故事环境",
        "场景": "作品核心世界观场景",
        "动作": "展示规则和压力",
        "情绪": "沉浸/期待",
        "避免": "不要出现文字、logo、水印或无依据的具体角色。",
        "英文画面提示词": "vertical 3:4 anime illustration, immersive story world environment based on the synopsis, layered depth, cinematic atmosphere, no text, no words, no letters",
    },
    {
        "页码": 3,
        "作用": "冲突",
        "剧情依据": "基于作品简介中的第一层核心矛盾。",
        "画面主体": "主角与阻力",
        "场景": "冲突爆发现场",
        "动作": "对峙或抉择",
        "情绪": "紧张/爽感",
        "避免": "不要编造简介未出现的CP或阵营。",
        "英文画面提示词": "vertical 3:4 anime illustration, protagonist facing a concrete obstacle from the synopsis, tense confrontation, dynamic composition, no text, no words, no letters",
    },
    {
        "页码": 4,
        "作用": "爽点",
        "剧情依据": "基于作品简介中的反差设定或高能看点。",
        "画面主体": "主角的关键能力或反差动作",
        "场景": "高能瞬间",
        "动作": "能力发动或局势反转",
        "情绪": "爽/惊喜",
        "避免": "不要画成通用写真。",
        "英文画面提示词": "vertical 3:4 anime illustration, high-energy turning point based on the synopsis, surprising power shift, vibrant lighting, no text, no words, no letters",
    },
    {
        "页码": 5,
        "作用": "收束",
        "剧情依据": "基于作品简介中的关系、目标或后续期待。",
        "画面主体": "主角与关键元素",
        "场景": "阶段性胜利或悬念场景",
        "动作": "向下一目标前进",
        "情绪": "期待/收藏",
        "避免": "不要出现任何可读文字。",
        "英文画面提示词": "vertical 3:4 anime illustration, hopeful ending shot with protagonist and story-specific symbols, cohesive carousel style, no text, no words, no letters",
    },
]


def _default_content_brief():
    return json.loads(json.dumps(CONTENT_BRIEF_DEFAULT, ensure_ascii=False))


def _default_visual_storyboard():
    return json.loads(json.dumps(VISUAL_STORYBOARD_DEFAULT, ensure_ascii=False))


def _local_analyze(work):
    name = work.get("作品名称", "")
    author = work.get("作者", "")
    platform = work.get("平台", "")
    category = work.get("分类", "")
    material_points = []
    for key in ["正文片段", "试读内容", "章节摘要", "目录", "书评摘录", "读者评论", "热评", "高赞评论"]:
        value = work.get(key)
        if isinstance(value, list):
            material_points.extend([str(x).strip() for x in value[:3] if str(x).strip()])
        elif value:
            material_points.append(str(value).strip())
    material_points = material_points[:5]

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
        "卖点分析": {
            "核心卖点": f"{name}的开篇套路和人物设定",
            "稀缺性评分": 4,
            "实用性评分": 4,
            "可感知评分": 5,
            "总分": 80,
            "优先级": "核心",
            "辅助卖点": ["冲突设计层层递进", "情绪触发稳定"],
        },
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
        "内容简报": {
            "目标人群": ["写作者", "内容创作者", "网文爱好者"],
            "核心痛点": f"想判断{name or '这本作品'}值不值得追，但简介信息太散，抓不到真正的爽点和雷点。",
            "读者收益": "快速看懂开篇钩子、人物关系和冲突递进，决定是否加入书单或借鉴写法。",
            "标题候选": [
                f"{name}值不值得追？先看这3个爆点",
                f"{category}党别错过！这本开篇很会抓人",
                f"拆完{name}，我懂它为什么容易上头了",
            ],
            "封面钩子": {
                "主标题": f"{name or category}开篇拆解",
                "副标题": "3个爆点看懂值不值得追",
                "情绪": "上头/好奇",
                "点击理由": "用痛点、收益和关键钩子帮读者快速判断作品吸引力。",
            },
            "图文页结构": ["痛点提问", "作品速览", "开篇钩子", "人物关系", "冲突递进", "收藏总结"],
            "证据素材": material_points or ["简介", "分类", "开篇套路", "冲突设计"],
            "禁用表达": ["私信", "加群", "站外链接"],
        },
        "配图提示词": [
            "小红书竖版封面，比例3:4，动漫风，女主修真者半身像，红黑高对比，标题留白，细节精致，高清插画",
            "小红书竖版配图，比例3:4，动漫风，宗门大殿夜色场景，群像构图，戏剧光影，电影感，高清插画",
            "小红书竖版配图，比例3:4，动漫风，女主与师侄对峙场面，动作张力，动态线条，高清插画",
            "小红书竖版配图，比例3:4，动漫风，掌门炖鹅的反差喜剧场景，明快配色，轻松氛围，高清插画",
            "小红书竖版配图，比例3:4，动漫风，最终团战群像，热血高能，火焰特效，高清插画",
        ],
        "视觉分镜": _default_visual_storyboard(),
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

    # 卖点分析字段（参考xhs-writer-skill：稀缺性×实用性×可感知）
    result.setdefault("卖点分析", {})
    sa = result["卖点分析"]
    sa.setdefault("核心卖点", "")
    sa.setdefault("稀缺性评分", 3)
    sa.setdefault("实用性评分", 3)
    sa.setdefault("可感知评分", 3)
    sa.setdefault("总分", 27)
    sa.setdefault("优先级", "辅助")
    sa.setdefault("辅助卖点", [])
    if not isinstance(sa["辅助卖点"], list):
        sa["辅助卖点"] = [str(sa["辅助卖点"])] if sa["辅助卖点"] else []

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

    result.setdefault("内容简报", _default_content_brief())
    cb = result["内容简报"]
    if not isinstance(cb, dict):
        cb = _default_content_brief()
    for k, v in _default_content_brief().items():
        cb.setdefault(k, v)
    for k in ["目标人群", "标题候选", "图文页结构", "证据素材", "禁用表达"]:
        if not isinstance(cb.get(k), list):
            cb[k] = [str(cb[k])] if cb.get(k) else []
    cb.setdefault("封面钩子", {})
    if not isinstance(cb["封面钩子"], dict):
        cb["封面钩子"] = {}
    for k in ["主标题", "副标题", "情绪", "点击理由"]:
        cb["封面钩子"].setdefault(k, "")
    result["内容简报"] = cb

    prompts = result.get("配图提示词", [])
    if not isinstance(prompts, list):
        prompts = [str(prompts)] if prompts else []
    prompts = [str(x).strip() for x in prompts if str(x).strip()]
    if len(prompts) < 4:
        prompts.extend(
            [
                "小红书竖版配图，比例3:4，动漫风，人物特写，高清插画，no text, no words, text-free image",
                "小红书竖版配图，比例3:4，动漫风，剧情冲突场面，高清插画，no text, no words, text-free image",
                "小红书竖版配图，比例3:4，动漫风，群像构图，高清插画，no text, no words, text-free image",
                "小红书竖版配图，比例3:4，动漫风，氛围场景，高清插画，no text, no words, text-free image",
            ]
        )
    result["配图提示词"] = prompts[:5]

    storyboard = result.get("视觉分镜", [])
    if not isinstance(storyboard, list):
        storyboard = []
    normalized_storyboard = []
    defaults = _default_visual_storyboard()
    for i in range(5):
        item = storyboard[i] if i < len(storyboard) else {}
        if isinstance(item, str):
            item = {"画面主体": item, "英文画面提示词": item}
        if not isinstance(item, dict):
            item = {}
        fallback = defaults[i]
        shot = {}
        for key in ["页码", "作用", "剧情依据", "画面主体", "场景", "动作", "情绪", "避免", "英文画面提示词"]:
            value = item.get(key)
            if value is None and key == "英文画面提示词":
                value = item.get("visual_prompt_en") or item.get("prompt_en") or item.get("prompt")
            shot[key] = value if str(value or "").strip() else fallback[key]
        shot["页码"] = i + 1
        normalized_storyboard.append(shot)
    result["视觉分镜"] = normalized_storyboard

    result.setdefault("元信息", {})
    result["元信息"].setdefault("来源", "openai")
    result["元信息"].setdefault("平台", work.get("平台", ""))
    result["元信息"].setdefault("分类", work.get("分类", ""))
    result["元信息"].setdefault("作者", work.get("作者", ""))
    return result


def analyze_work(work, reference_notes=None, recent_feedback=None, account_strategy=None):
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
        return _openai_analyze(work, reference_notes, recent_feedback, account_strategy=account_strategy)
    if provider == "ernie":
        raise RuntimeError("MODEL_PROVIDER=ernie 尚未接入。")
    raise RuntimeError(f"未知的 MODEL_PROVIDER: {provider}")


def _openai_analyze(work, reference_notes=None, recent_feedback=None, account_strategy=None):
    provider = os.getenv("MODEL_PROVIDER", "openai").strip().lower()
    is_qwen = provider in {"qwen", "dashscope"}
    is_deepseek = provider == "deepseek"
    if is_qwen:
        api_key = os.getenv("QWEN_API_KEY", "").strip()
    elif is_deepseek:
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
    else:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
    api_key_intl = os.getenv("QWEN_API_KEY_INTL", "").strip() if is_qwen else ""
    if not api_key and not api_key_intl:
        raise RuntimeError("模型 API_KEY 未设置")

    if is_qwen:
        model_default = "qwen-plus"
        model = os.getenv("QWEN_MODEL", "").strip() or os.getenv("OPENAI_MODEL", model_default).strip()
    elif is_deepseek:
        model_default = "deepseek-chat"
        model = os.getenv("DEEPSEEK_MODEL", "").strip() or os.getenv("OPENAI_MODEL", model_default).strip()
    else:
        model_default = "gpt-4o-mini"
        model = os.getenv("OPENAI_MODEL", model_default).strip()

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
    elif is_deepseek:
        base_urls = [
            os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
        ]
    else:
        base_default = "https://api.openai.com/v1"
        base_urls = [os.getenv("OPENAI_BASE_URL", base_default).strip().rstrip("/")]

    account_strategy = account_strategy or get_account_strategy()
    strategy_prompt = render_strategy_prompt(account_strategy)

    system_prompt = (
        "你是资深网文拆解专家。请严格输出 JSON，不要输出除 JSON 以外的任何内容。"
        "Return valid json only."
        "所有字符串必须用英文双引号 \" 包裹。字符串内容中如需引用，请用书名号《》或单引号，不要使用中文引号。确保输出是合法 JSON。"
        "风格要求：小红书可直接发布，语言自然有网感，避免空泛套话。"
        "准确性要求：【作品信息】中的简介是从小说网站搜索到的真实作品介绍，请基于此进行专业拆解分析。"
        "第零步事实校验要求：生成前必须先读取【事实校验】；所有具体情节、人物、设定、读者评价都必须能对应到 usable_facts 或 cautious_facts。"
        "usable_facts 可直接写；cautious_facts 只能写成'有读者说/据评论反馈'，不可冒充亲身阅读体验；blocked_rules 中禁止的内容绝对不要写。"
        "如果【扩展素材】包含目录、章节摘要、试读内容、书评摘录、读者评论或正文片段，必须优先用这些二级素材补足具体阅读判断；"
        "正文和内容简报要体现具体规则、阶段目标、人物处境、读者反馈或章节线索，避免只围绕一句简介反复改写。"
        "如果【事实校验】generation_mode 为 synopsis_grounded 或 insufficient，只能生成简介快筛/素材不足提示型拆解，不得写成已读全文后的深度推荐。"
        "如果简介仍不够详细（如仅有标签式描述而缺少情节细节），只能做保守快筛，不得结合题材特征脑补具体人物、能力、情节或雷点。"
        "不要凭空编造简介中不存在的具体人物对话或情节细节。"
        "人物设定应基于简介中的线索还原；金句应为针对该作品风格的写作方法论提炼，而非编造书中原文。"
        "内容简报必须锚定当前作品事实：核心痛点、读者收益、封面钩子、标题候选只能围绕作品设定、人物、冲突、爽点和阅读判断展开；"
        "不得把参考笔记中的泛化方法论、职场成长、认知脚手架、反套路写作技巧等表达迁移到不相关作品。"
        "小红书原生运营硬约束：标题要尖，必须给出具体题材/爽点/反差/读者收益，避免'绝了''宝藏'单独撑标题；"
        "首图要像大字报，封面钩子主标题优先控制在16个中文字符内，副标题优先控制在24个中文字符内，一眼能懂冲突或爽点；"
        "前三行必须先给结论，不要先铺剧情，结构为：适合谁/值不值得看、最强爽点或反差、读者看完能得到什么判断；"
        "评论钩子必须是低门槛二选一或投喂式问题，能让读者顺手回复书名/偏好/站队。"
        "文案去模板化要求：不同作品要选择不同叙述角度，可以是书荒安利、避雷判断、爽点拆解或情绪共鸣，不要每篇都输出'核心亮点-人物设定-冲突设计-阅读建议-我的结论'这种固定栏目感；"
        "避免机械套话：少用'这本真的绝了''刷到就是缘分''不是靠设定噱头''有阅读粘性'等高频句，必须写出当前作品自己的判断。"
        "以下账号策略优先影响标题公式、封面钩子、前三行、评论钩子和质量判断，但不能覆盖作品事实："
        f"{strategy_prompt}"
        "如果简介包含出版、签名、微博/围脖、有声剧、喜马拉雅、番外、作话、促销等公告信息，必须视为非剧情素材，不能写入剧情或笔记正文。"
        "内容合规要求：禁止出现导流私信、联系方式、平台外跳转、夸张医疗或违规承诺等违反小红书社区规范的内容。禁止在笔记内容中出现第三方平台名称（如'晋江'、'起点'、'番茄'、'耽美文学城'等），避免被判定为引流违规。"
        "输出字段必须包含以下结构："
        "{"
        "\"开篇套路\": [string,string,string],"
        "\"人物设定\": {\"女主\":string,\"男主\":string,\"亮点配角\":string},"
        "\"冲突设计\": {\"第一层\":string,\"第二层\":string,\"第三层\":string},"
        "\"情绪触发\": [string,string,string],"
        "\"金句\": [string,string,string,string,string],"
        "\"卖点分析\": {"
        "\"核心卖点\":string,"
        "\"稀缺性评分\":number,"
        "\"实用性评分\":number,"
        "\"可感知评分\":number,"
        "\"总分\":number,"
        "\"优先级\":string,"
        "\"辅助卖点\":[string,string]"
        "},"
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
        "\"内容简报\": {"
        "\"目标人群\":[string,string,string],"
        "\"核心痛点\":string,"
        "\"读者收益\":string,"
        "\"标题候选\":[string,string,string,string,string,string,string,string],"
        "\"封面钩子\":{\"主标题\":string,\"副标题\":string,\"情绪\":string,\"点击理由\":string},"
        "\"图文页结构\":[string,string,string,string],"
        "\"证据素材\":[string,string,string],"
        "\"禁用表达\":[string,string,string]"
        "},"
        "\"视觉分镜\":["
        "{\"页码\":number,\"作用\":string,\"剧情依据\":string,\"画面主体\":string,\"场景\":string,\"动作\":string,\"情绪\":string,\"避免\":string,\"英文画面提示词\":string},"
        "{\"页码\":number,\"作用\":string,\"剧情依据\":string,\"画面主体\":string,\"场景\":string,\"动作\":string,\"情绪\":string,\"避免\":string,\"英文画面提示词\":string},"
        "{\"页码\":number,\"作用\":string,\"剧情依据\":string,\"画面主体\":string,\"场景\":string,\"动作\":string,\"情绪\":string,\"避免\":string,\"英文画面提示词\":string},"
        "{\"页码\":number,\"作用\":string,\"剧情依据\":string,\"画面主体\":string,\"场景\":string,\"动作\":string,\"情绪\":string,\"避免\":string,\"英文画面提示词\":string},"
        "{\"页码\":number,\"作用\":string,\"剧情依据\":string,\"画面主体\":string,\"场景\":string,\"动作\":string,\"情绪\":string,\"避免\":string,\"英文画面提示词\":string}"
        "],"
        "\"配图提示词\":[string,string,string,string,string],"
        "\"元信息\": {\"来源\":string,\"平台\":string,\"分类\":string,\"作者\":string}"
        "}"
    )

    user_prompt = {
        "任务": "根据搜索到的作品信息进行网文拆解与爆款基因提取",
        "作品事实": {
            "作品名称": work.get("作品名称", ""),
            "作者": work.get("作者", ""),
            "平台": work.get("平台", ""),
            "分类": work.get("分类", ""),
            "评分": work.get("评分", ""),
            "字数（万）": work.get("字数（万）", ""),
            "完结状态": work.get("完结状态", ""),
            "取向": work.get("取向", ""),
            "剧情简介": work.get("剧情简介") or work.get("简介", ""),
        },
        "扩展素材": {
            "目录": work.get("目录", []),
            "章节摘要": work.get("章节摘要", []),
            "试读内容": work.get("试读内容", ""),
            "书评摘录": work.get("书评摘录", []),
            "热评": work.get("热评", []),
            "读者评论": work.get("读者评论", []),
            "正文片段": work.get("正文片段", []),
            "高赞评论": work.get("高赞评论", []),
            "素材厚度": work.get("素材厚度", {}),
        },
        "事实校验": work.get("素材证据卡") or (work.get("素材厚度", {}) or {}).get("fact_check", {}),
        "已排除的非剧情信息": work.get("非剧情信息", []),
        "账号策略": account_strategy,
        "要求": [
            "重要：只能基于【作品事实】中的剧情简介、分类和基础信息进行专业拆解",
            "必须执行第零步：逐条对照【事实校验】。具体事实只能来自 usable_facts；读者评价只能来自 cautious_facts 且必须标注为读者反馈；blocked_rules 禁止内容不可出现。",
            "如果【事实校验】generation_mode 不是 grounded_note，不得写'我看完''熬夜看完''看到第N章'等亲身阅读体验，也不得生成深度拆书口吻。",
            "如果【扩展素材】不为空，内容简报的证据素材必须至少引用2条扩展素材中的具体信息，例如章节名、评论反馈、正文片段或试读节点",
            "如果目录/章节标题能看出剧情推进，请用它判断作品节奏、阶段目标和追更钩子；如果评论素材能看出读者情绪，请用它判断爽点或雷点",
            "【已排除的非剧情信息】只供你理解哪些内容不能使用，绝对不要写入剧情、标题、内容简报或笔记文案",
            "简介中若出现出版开售、签名、微博/围脖、有声剧、喜马拉雅、番外、作话、活动促销等公告信息，请过滤掉，不得当成剧情摘要",
            "开篇套路至少3条，基于简介中的开篇信息或题材特征分析",
            "人物设定三类均必填，基于简介中的人物线索还原；若简介无线索，只写泛化身份和题材看点，不要出现'基于题材推测'、'可能'、'推测'等分析痕迹",
            "冲突设计三层均必填，从简介的情节描述中提取核心矛盾",
            "情绪触发至少3类，基于题材和情节判断",
            "金句至少5条，为该类型作品的写作方法论提炼，不要编造书中原文",
            "小红书包装字段全部必填，可发布",
            "内容简报字段全部必填：目标人群、核心痛点、读者收益、标题候选、封面钩子、图文页结构、证据素材、禁用表达。标题候选至少8条，需可直接作为小红书标题，封面钩子需给出主标题、副标题、情绪和点击理由。",
            "标题更尖：标题候选必须覆盖账号策略里的标题公式类型，并额外包含书荒判断、避雷判断、爽点反差、同款求投喂等不同角度，优先20字内，最多不超过24字；小红书标题模板选择其中点击欲最强的一条。",
            "首图更像大字报：封面钩子必须遵守账号策略里的封面规则；不要用空泛形容词堆叠。",
            "前三行更快给结论：正文开头模板必须是3行短句，并遵守账号策略里的前三行规则。",
            "评论钩子更强：互动话术模板只能写一个具体问题，并遵守账号策略里的评论钩子规则。",
            "内容简报必须贴合当前作品，不要写泛化成长建议、认知脚手架、反套路写作技巧、底层逻辑等与剧情无关的收益承诺",
            "小红书包装文案要有明显钩子、对比、结论，不要写成学术报告",
            "正文结构建议必须给出适合当前作品的叙述角度，不要固定为核心亮点/人物设定/冲突设计/阅读建议/结论。",
            "正文开头模板、正文结构建议、互动话术模板不得复用'这本真的绝了''刷到就是缘分''不是靠设定噱头''有阅读粘性'等通用套话。",
            "正文开头模板和互动话术模板要带平台语气，可包含少量emoji",
            "热门标签推荐要贴近题材，不要泛泛标签",
            "明确规避小红书违规表达：不能引导私信、不能留联系方式、不能导流站外平台。禁止在标题、正文、标签等任何笔记内容中出现第三方平台名称（如'晋江'、'起点'、'番茄'等），避免被判定为引流。",
            "【视觉分镜-最重要】必须输出5页视觉分镜，基于作品事实和剧情简介逐页设计，不得按题材套模板。每页都要写清楚剧情依据；如果简介没有给出具体人物关系、CP、男主或阵营，不要编造，只写泛化身份。每页的英文画面提示词必须是英文，包含vertical 3:4、anime illustration、具体人物/场景/动作/光影，不得出现中文、书名、标题、台词、平台名或任何可读文字。",
            "【配图提示词】从视觉分镜一一转译，输出4-5条即可。绝对禁止在提示词中引用任何原文句子、台词、书名片段或带引号的中文。图片画面中绝对不能出现任何中文文字、英文字母、字幕、台词、水印、logo、标题、手写体、书法。每条提示词末尾必须追加：'no text, no words, no letters, completely text-free image'。",
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
        user_prompt["风格参考笔记（只学习结构/语气/节奏，禁止复用观点、收益承诺、标题语义和具体内容）"] = ref_lines
        user_prompt["风格参考使用规则"] = [
            "只能学习开头节奏、段落组织、互动方式和语气强弱",
            "不得把参考笔记里的读者收益、方法论、标题概念、痛点表达迁移到当前作品",
            "当前作品的每个标题、痛点、收益和封面钩子都必须能被【作品事实】支撑",
        ]

    # 反馈闭环：注入运营历史修改偏好
    if recent_feedback:
        user_prompt["运营修改偏好（请避免类似问题，遵循以下风格）"] = [
            f"[{f.get('time','')}] {f.get('field','')}: {f.get('reason','')}"
            for f in recent_feedback[:5]
        ]

    user_prompt["生成依据"] = {
        "账号策略": strategy_trace(account_strategy),
        "平台通用规则": ["标题具体", "封面一眼可读", "前三行先给结论", "评论钩子低门槛"],
        "内容事实优先": True,
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_prompt, ensure_ascii=False)},
        ],
        "temperature": float(os.getenv("OPENAI_TEMPERATURE", "0.3")),
        "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS", "6000")),
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
        text = text.replace("‘", "'").replace("’", "'")
        text = text.replace("＂", "\"")
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
            fallback = _ensure_analysis_shape(fallback, work)
            fallback["生成依据"] = {
                "账号策略": strategy_trace(account_strategy),
                "平台通用规则": ["标题具体", "封面一眼可读", "前三行先给结论", "评论钩子低门槛"],
                "内容事实优先": True,
            }
            return fallback

    result = _ensure_analysis_shape(result, work)
    result["生成依据"] = {
        "账号策略": strategy_trace(account_strategy),
        "平台通用规则": ["标题具体", "封面一眼可读", "前三行先给结论", "评论钩子低门槛"],
        "内容事实优先": True,
    }
    return result
