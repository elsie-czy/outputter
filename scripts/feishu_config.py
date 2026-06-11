"""
飞书多维表格 API 配置
注意：请勿将此文件提交到公开仓库，建议加入 .gitignore
基于2026-02-19字段扫描结果更新
"""

import os


def get_feishu_config():
    prescreen_id = os.getenv("FEISHU_TOPIC_PRESCREEN_TABLE_ID", "") or os.getenv(
        "FEISHU_PRESCREEN_TABLE_ID", ""
    )
    note_metrics_id = os.getenv("FEISHU_NOTE_METRICS_TABLE_ID", "")
    hot_factors_id = os.getenv("FEISHU_HOT_FACTORS_TABLE_ID", "")
    exp_ledger_id = os.getenv("FEISHU_EXPERIMENT_LEDGER_TABLE_ID", "")
    account_7d_id = os.getenv("FEISHU_ACCOUNT_7D_TABLE_ID", "")
    return {
        # 应用凭证（从飞书开放平台「凭证与基础信息」获取）
        "app_id": os.getenv("FEISHU_APP_ID", ""),
        "app_secret": os.getenv("FEISHU_APP_SECRET", ""),
        
        # 表格标识（从飞书多维表格 URL 中提取 table= 参数）
        "app_token": os.getenv("FEISHU_APP_TOKEN", ""),  # Base ID，从多维表格 URL 中提取
        "table_id": os.getenv("FEISHU_MAIN_TABLE_ID", ""),   # 工作表 ID，从多维表格 URL 的 table= 参数提取
    
    # 关联表ID
        "related_table_ids": {
        "开篇套路库": "tblKzo6CH2rxrAb5",
        "人物设定库": "tblcp139agDLyV2z",
        "冲突设计库": "tblLbtvOH4YuHCsv",
        "情绪触发库": "tblUvPAS7fU9wxkR",
        "金句库": "tbl73ZJc0gk9MCfg",
        "选题库": "tbl7WRy4TOJng2pY",
        "选题库-初筛": prescreen_id,
        "小红书笔记库": "tblnKyitU6iQFCg0",
        "笔记结果库": note_metrics_id,
        "爆款因子库": hot_factors_id,
        "实验台账": exp_ledger_id,
        "账号7日快照": account_7d_id,
        },

    # 必填字段（用于写入前校验）
        "required_fields": {
        "主表": ["作品名称", "作者", "平台", "分类", "简介", "评分", "字数（万）", "取向"],
        "开篇套路库": ["套路名称", "拆解记录表（主表）"],
        "人物设定库": ["套路名称", "角色名称", "人物类型", "拆解记录表（主表）"],
        "冲突设计库": ["冲突层级", "冲突内容"],
        "情绪触发库": ["情绪类型"],
        "金句库": ["金句内容", "拆解记录表（主表）"],
        },
    
    # API 端点
        "base_url": "https://open.feishu.cn/open-apis",
    
    # 主表字段映射（基于2026-02-19实际字段结构更新）
        "field_mapping": {        "互动话术模板": "互动话术模板",        "人物反差": "人物反差",        "任务触发": "任务触发",        "作品名称": "作品名称",        "作者": "作者",        "内容扩展方向": "内容扩展方向",        "内容类型标签": "内容类型标签",        "分类": "分类",        "取向": "取向",        "受众画像关键词": "受众画像关键词",        "可复用模板": "可复用模板",        "备注": "备注",        "套路质量评分": "套路质量评分",        "女主设定": "女主设定",        "字数_万_": "字数（万）",        "封面图描述建议": "封面图描述建议",        "小红书标题模板": "小红书标题模板",        "平台": "平台",        "开篇套路类型": "开篇套路类型",        "情绪分析摘要": "情绪分析摘要",        "情绪基调": "情绪基调",        "情绪钩子": "情绪钩子",        "情节节点摘要": "情节节点摘要",        "拆解时间": "拆解时间",        "文本": "文本",        "是否发布笔记": "是否发布笔记",        "最佳发布时间建议": "最佳发布时间建议",        "核心冲突": "核心冲突",        "正文开头模板": "正文开头模板",        "正文结构建议": "正文结构建议",        "热门标签推荐": "热门标签推荐",        "男主设定": "男主设定",        "第一层冲突": "第一层冲突",        "第三层冲突": "第三层冲突",        "第二层冲突": "第二层冲突",        "简介": "简介",        "记录ID": "记录ID",        "金句_Top5_": "金句（Top5）",    },    
    # 关联表字段映射（用于维护关联表数据）
        "related_field_mappings": {
        "开篇套路库": {
            "套路名称": "trope_name",
            "套路ID": "trope_id",  # 类型1005：自动编号
            "套路类型": "trope_type",           # 类型3：单选
            "适用类型": "applicable_types",     # 类型4：多选
            "质量评分": "quality_score",        # 类型3：单选
            "使用效果": "usage_effect",         # 类型3：单选
            "核心原理": "core_principle",       # 类型1：文本
            "操作步骤": "operation_steps",      # 类型1：文本
            "示例原文": "example_text",         # 类型1：文本
            "应用场景": "application_scenario",
            "使用次数": "usage_count",          # 类型1：文本（实际为文本类型）
            "拆解记录表（主表）": "disassembly_records"  # 类型21：双向链接
        },
        "人物设定库": {
            "套路名称": "trope_name",
            "套路ID": "trope_id",  # 类型1005：自动编号
            "角色名称": "character_name",      # 类型1：文本（已确认存在）
            "人物类型": "character_type",       # 类型3：单选
            "性格反差": "personality_contrast", # 类型1：文本
            "身份反差": "identity_contrast",    # 类型1：文本
            "金手指类型": "goldfinger_types",   # 类型4：多选
            "成长弧光": "growth_arc",          # 类型1：文本
            "示例原文": "example_text",         # 类型1：文本
            "应用场景": "application_scenario",
            "质量评分": "quality_score",        # 类型3：单选
            "使用次数": "usage_count",          # 类型2：数字
            "使用效果": "usage_effect",         # 类型3：单选
            "来源书名": "source_book",          # 类型18：单向链接
            "拆解记录表（主表）": "disassembly_records"  # 类型21：双向链接
            # 注意："拆解记录表（主表） 2"为冗余字段，可以不映射
        },
        "冲突设计库": {
            "套路名称": "trope_name",
            "套路ID": "trope_id",  # 类型1005：自动编号
            "冲突类型": "conflict_type",        # 类型3：单选
            "冲突层级": "conflict_level",       # 类型3：单选
            "冲突内容": "conflict_content",     # 类型1：文本
            "矛盾双方": "conflicting_parties",  # 类型1：文本
            "情绪触发点": "emotional_trigger",  # 类型1：文本
            "升级逻辑": "escalation_logic",     # 类型1：文本
            "示例原文": "example_text",         # 类型1：文本
            "应用场景": "application_scenario",
            "质量评分": "quality_score",        # 类型3：单选
            "使用次数": "usage_count",          # 类型2：数字
            "使用效果": "usage_effect",         # 类型3：单选
            "来源书名": "source_book",          # 类型18：单向链接
            "提取日期": "extraction_date"  # 类型1001：CreatedTime
        },
        "情绪触发库": {
            "情绪类型": "emotion_type",         # 类型3：单选
            "套路ID": "trope_id",  # 类型1005：自动编号
            "触发词": "trigger_words",         # 类型1：文本
            "触发场景": "trigger_scenario",    # 类型1：文本
            "描写技巧": "description_skills",  # 类型1：文本
            "示例原文": "example_text",         # 类型1：文本
            "示例金句": "example_golden_sentence",  # 类型1：文本
            "应用场景": "application_scenario",
            "质量评分": "quality_score",        # 类型3：单选
            "使用次数": "usage_count",          # 类型2：数字
            "使用效果": "usage_effect",         # 类型3：单选
            "来源书名": "source_book",          # 类型18：单向链接
            "提取日期": "extraction_date"  # 类型1001：CreatedTime
        },
        "金句库": {
            "金句类型": "sentence_type",        # 类型3：单选
            "套路ID": "trope_id",  # 类型1005：自动编号
            "金句内容": "sentence_content",     # 类型1：文本
            "适用场景": "applicable_scenario",  # 类型1：文本
            "写作技巧": "writing_skills",       # 类型1：文本
            "改造模板": "transformation_template",  # 类型1：文本
            "应用示例": "application_example",  # 类型1：文本
            "质量评分": "quality_score",        # 类型3：单选
            "使用次数": "usage_count",          # 类型2：数字
            "使用效果": "usage_effect",         # 类型3：单选
            "来源书名": "source_book",          # 类型18：单向链接
            "提取日期": "extraction_date",  # 类型1001：CreatedTime
            "拆解记录表（主表）": "disassembly_records",  # 类型21：双向链接
            "示例原文": "example_text"  # 已确认存在
        },
            "选题库": {
            "作品名称": "作品名称",
            "是否拆解": "是否拆解",
            "搜索要素": "搜索要素",
            "字数": "字数",
            "字数（万字）": "字数（万字）",
            "简介": "简介",
            "平台": "平台",
            "分类": "分类",
            "取向": "取向"
        },
        "小红书笔记库": {
            "记录ID": "record_id",
            "作品名称": "work_name",
            "作者": "author",
            "小红书标题模板": "xhs_title_template",
            "封面图描述建议": "cover_image_suggestion",
            "热门标签推荐": "popular_tags",
            "正文开头模板": "content_start_template",
            "正文结构建议": "content_structure_suggestion",
            "互动话术模板": "interaction_template",
            "受众画像关键词": "audience_keywords",
            "内容类型标签": "content_type_tags",
            "更新时间": "update_time"
        },
        }
    }


FEISHU_CONFIG = get_feishu_config()

# 测试用：打印配置（不输出敏感信息）
def get_tenant_access_token():
    """
    获取飞书API的tenant_access_token
    返回: token字符串，失败时返回None
    """
    import requests
    import json
    
    config = FEISHU_CONFIG
    app_id = config["app_id"]
    app_secret = config["app_secret"]
    base_url = config["base_url"]
    
    url = f"{base_url}/auth/v3/tenant_access_token/internal"
    
    payload = {
        "app_id": app_id,
        "app_secret": app_secret
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code != 200:
            print(f"获取tenant_access_token失败，状态码: {response.status_code}")
            return None
            
        data = response.json()
        if data.get("code") != 0:
            print(f"获取tenant_access_token API错误: {data}")
            return None
            
        token = data.get("tenant_access_token")
        if not token:
            print("token为空")
            return None
            
        return token
        
    except Exception as e:
        print(f"获取tenant_access_token时发生异常: {e}")
        return None


def check_duplicate_by_composite_key(token, work_name, author):
    """
    检查飞书主表中是否存在相同作品名称和作者的记录
    返回: 记录ID (如果存在), 否则返回None
    """
    import requests
    import json
    
    config = FEISHU_CONFIG
    base_url = config["base_url"]
    app_token = config["app_token"]
    main_table_id = config["table_id"]
    
    url = f"{base_url}/bitable/v1/apps/{app_token}/tables/{main_table_id}/records"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"查询主表记录失败: {response.status_code}, {response.text}")
            return None
        
        data = response.json()
        if data.get("code") != 0:
            print(f"查询主表记录API错误: {data}")
            return None
        
        records = data.get("data", {}).get("items", [])
        matching_ids = []
        
        for record in records:
            fields = record.get("fields", {})
            record_work_name = fields.get("作品名称", "")
            record_author = fields.get("作者", "")
            
            if record_work_name == work_name and record_author == author:
                matching_ids.append(record.get("record_id"))
        
        if len(matching_ids) == 0:
            return None
        elif len(matching_ids) == 1:
            return matching_ids[0]
        else:
            print(f"⚠️  警告: 发现多个重复记录 (作品: {work_name}, 作者: {author})")
            print(f"   记录ID列表: {matching_ids}")
            # 返回第一个记录ID，并建议人工干预
            return matching_ids[0]
            
    except Exception as e:
        print(f"检查重复记录时发生异常: {e}")
        return None


if __name__ == "__main__":
    config = FEISHU_CONFIG.copy()
    config["app_secret"] = "***"
    print("飞书配置加载成功（部分信息已脱敏）：")
    for key, value in config.items():
        if key in ["app_id", "app_token", "table_id", "base_url"]:
            print(f"  {key}: {value}")
        elif key == "related_table_ids":
            print(f"  related_table_ids: {len(value)}个关联表")
        elif key == "field_mapping":
            print(f"  field_mapping: {len(value)}个主表字段")
        elif key == "related_field_mappings":
            print(f"  related_field_mappings: {len(value)}个关联表字段映射")
    
    # 验证字段数量匹配
    scan_data = {}
    try:
        import json
        with open('temp/feishu_field_scan_result.json', 'r', encoding='utf-8') as f:
            scan_data = json.load(f)
        
        actual_field_count = len(scan_data['main_table_fields'])
        config_field_count = len(config["field_mapping"])
        
        print(f"\n📊 字段数量验证：")
        print(f"  扫描结果字段数：{actual_field_count}")
        print(f"  配置映射字段数：{config_field_count}")
        
        if actual_field_count == config_field_count:
            print("  ✅ 字段数量匹配！")
        else:
            print(f"  ⚠️ 字段数量不匹配，差{abs(actual_field_count - config_field_count)}个")
            
    except:
        print("  ⚠️ 无法验证字段数量")
