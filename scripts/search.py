from datetime import datetime


def search_work_info(work):
    # Search disabled. Use topic library fields only.
    return {
        "平台": work.get("平台", ""),
        "分类": work.get("分类", ""),
        "评分": work.get("评分", ""),
        "字数（万）": work.get("字数（万）", ""),
        "完结状态": work.get("完结状态", ""),
        "搜索时间": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "搜索模式": "off",
        "简介": work.get("简介", ""),
        "作者": work.get("作者", ""),
        "作品名称": work.get("作品名称", ""),
        "取向": work.get("取向", ""),
    }
