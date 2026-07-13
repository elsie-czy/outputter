import unittest
import re

from scripts.deconstruct_daily import build_xhs_note, generate_title_options, _mobile_lines
from scripts.model_adapter import _ensure_analysis_shape, _local_analyze
from scripts.xhs_note_humanizer import apply_xhs_humanize_note_skill, diagnose_xhs_ai_traces


class ContentBriefTest(unittest.TestCase):
    def _work(self):
        return {
            "作品名称": "测试作品",
            "作者": "测试作者",
            "平台": "测试平台",
            "分类": "古言",
            "简介": "女主重回命运转折点，先破局再反击。",
        }

    def _old_analysis(self):
        return {
            "开篇套路": ["重生节点开局", "先给危机", "再给反转"],
            "人物设定": {"女主": "清醒行动派", "男主": "资源位", "亮点配角": "推动冲突"},
            "冲突设计": {"第一层": "旧局压迫", "第二层": "身份选择", "第三层": "命运改写"},
            "情绪触发": ["爽感", "期待", "心疼"],
            "金句": ["先破局，再谈赢。", "真正的爽点，是选择权回到自己手里。", "反转要落在人身上。"],
            "卖点分析": {"核心卖点": "开篇冲突清晰", "辅助卖点": ["人设反差"]},
            "小红书包装": {
                "小红书标题模板": "测试作品真的很会写开篇",
                "热门标签推荐": ["#古言", "#网文拆解"],
                "正文开头模板": "这本开篇直接把压迫感拉满。",
                "正文结构建议": "开篇-人物-冲突",
                "受众画像关键词": ["写作者", "古言读者"],
                "互动话术模板": "你吃这种开篇吗？",
            },
        }

    def test_build_xhs_note_allows_old_analysis_without_content_brief(self):
        analysis = _ensure_analysis_shape(self._old_analysis(), self._work())

        note = build_xhs_note(self._work(), analysis)

        self.assertIn("【标题】", note)
        self.assertIn("测试作品", note)

    def test_generate_title_options_prefers_content_brief_titles(self):
        analysis = _ensure_analysis_shape(self._old_analysis(), self._work())
        analysis["内容简报"]["标题候选"] = ["简报标题A", "简报标题B"]

        titles = generate_title_options(self._work(), analysis)

        self.assertEqual(titles[:2], ["简报标题A", "简报标题B"])

    def test_ensure_analysis_shape_fills_content_brief_default(self):
        analysis = _ensure_analysis_shape(self._old_analysis(), self._work())

        self.assertIn("内容简报", analysis)
        self.assertEqual(analysis["内容简报"]["标题候选"], [])
        self.assertEqual(analysis["内容简报"]["封面钩子"]["主标题"], "")

    def test_local_analyze_returns_content_brief(self):
        analysis = _local_analyze(self._work())

        self.assertIn("内容简报", analysis)
        self.assertTrue(analysis["内容简报"]["标题候选"])
        self.assertTrue(analysis["内容简报"]["核心痛点"])

    def test_mobile_lines_filters_non_story_announcements(self):
        intro = (
            "【2023年6月24号18点第二册实体书出版开售，限时前两分钟有亲笔签名。"
            "详情关注围脖：天天赤脚】同名有声剧在喜马拉雅上线啦。"
            "卫三靠捡垃圾攒学费，误报单兵专业后用工程师思维破局。"
        )

        lines = _mobile_lines(intro, max_len=36, max_lines=3)

        joined = "\n".join(lines)
        self.assertIn("卫三靠捡垃圾攒学费", joined)
        self.assertNotIn("实体书", joined)
        self.assertNotIn("喜马拉雅", joined)

    def test_build_xhs_note_replaces_ungrounded_content_brief_claims(self):
        analysis = _ensure_analysis_shape(self._old_analysis(), self._work())
        analysis["内容简报"]["核心痛点"] = "努力方向感缺失：明明很拼，却总像跑在错误赛道上"
        analysis["内容简报"]["读者收益"] = "获得一套‘用原有优势破局新领域’的认知脚手架+5个可复用的反套路写作技巧"
        analysis["内容简报"]["封面钩子"] = {
            "主标题": "报错专业后，我靠看书成了全校最强单兵",
            "副标题": "不是躺平，是换引擎重启",
            "点击理由": "揭露‘安静努力’比‘大声内卷’更难复制的底层逻辑",
        }

        note = build_xhs_note(self._work(), analysis)

        self.assertNotIn("认知脚手架", note)
        self.assertNotIn("反套路写作技巧", note)
        self.assertNotIn("底层逻辑", note)
        self.assertNotIn("努力方向感", note)
        self.assertIn("测试作品", note)

    def test_build_xhs_note_avoids_backstage_review_phrases(self):
        work = {
            "作品名称": "穿成末世圣母女配",
            "作者": "九阶幻方",
            "平台": "晋江文学城",
            "分类": "原创-言情-幻想未来-爱情小说",
            "评分": "1720910976",
            "完结状态": "完结",
            "简介": (
                "贝暖穿进一本无CP末世小说，变成圣母女配。她被圣母系统绑定，"
                "必须在重生男主陆行迟面前刷满圣母值；男主却想把她丢进丧尸群。"
            ),
        }
        analysis = _ensure_analysis_shape(self._old_analysis(), work)
        analysis["卖点分析"]["核心卖点"] = "穿书+系统任务+重生男主"
        analysis["小红书包装"]["热门标签推荐"] = ["#末世文", "#穿书文"]

        note = build_xhs_note(work, analysis)

        blocked = [
            "先把剧情底子说清楚",
            "我会先看",
            "我比较在意这几件事",
            "我会重点看",
            "情绪口味",
            "我的结论",
            "判断它合不合口味",
            "评分：1720910976",
            "这 3 个点判断",
            "这3个点判断",
            "原创-言情-幻想未来-爱情小说里你最想",
        ]
        for phrase in blocked:
            self.assertNotIn(phrase, note)
        self.assertIn("女主", note)

    def test_infinite_resurrection_note_has_dense_value(self):
        work = {
            "作品名称": "末世：今天我又被迫复活",
            "作者": "陆喵",
            "平台": "番茄小说",
            "分类": "科幻末世",
            "简介": (
                "在丧尸病毒爆发的末世，沈秋觉醒了无限复活的异能。每次死亡，"
                "她都会在安全屋的床上醒来，时间倒退回死亡前的24小时。"
                "这看似无敌的能力，却成了她最大的噩梦——她被迫不断重复经历各种惨烈的死亡，"
                "只为在循环中寻找一线生机，拯救自己和她在乎的人。"
            ),
            "素材厚度": {
                "level": "thin",
                "gaps": ["缺少章节/试读/书评/评论等二级素材"],
            },
        }
        analysis = _ensure_analysis_shape(self._old_analysis(), work)
        analysis["卖点分析"]["核心卖点"] = "无限复活循环设定，女主在死亡中寻找破局"
        analysis["内容简报"]["证据素材"] = ["判断这本末世文是否值得追，了解无限复活设定的独特爽点"]
        analysis["小红书包装"]["热门标签推荐"] = ["#末世文", "#无限复活"]

        note = build_xhs_note(work, analysis)

        self.assertIn("24小时前", note)
        self.assertIn("安全屋", note)
        self.assertIn("反复", note)
        self.assertIn("破局", note)
        self.assertIn("我一开始也这么想", note)
        self.assertIn("脑子里一直冒三个问题", note)
        emoji_count = len(re.findall(r"[\U0001F300-\U0001FAFF]", note))
        self.assertGreaterEqual(emoji_count, 4)
        self.assertLessEqual(emoji_count, 8)
        self.assertNotIn("收藏时可以直接按这几条筛", note)
        self.assertNotIn("简介快筛", note)
        self.assertNotIn("资料边界", note)
        self.assertNotIn("判断这本末世文是否值得追", note)
        self.assertNotIn("了解无限复活设定的独特爽点", note)

    def test_xhs_humanize_skill_postprocesses_ai_note_shape(self):
        note = """【标题】测试标题

🏚️ 想看末世文但怕空壳设定的可以先停一下

这篇只按简介里写明的信息说。

💬 你更吃越死越强还是越死越惨？

🏷️ 标签
#末世文 #书荒推荐
"""
        analysis = {}

        result = apply_xhs_humanize_note_skill(
            note,
            work={"作品名称": "测试作品"},
            analysis=analysis,
            tags=["末世文", "书荒推荐"],
        )

        self.assertNotIn("🏷️ 标签", result)
        self.assertNotIn("这篇只按简介", result)
        self.assertNotIn("🏚️", result)
        self.assertIn("你们更喜欢", result)
        self.assertIn("关注我", result)
        self.assertIn("下期", result)
        self.assertIn("#末世文 #书荒推荐", result)
        self.assertTrue(analysis["xhs_humanize_note"]["applied"])
        self.assertTrue(diagnose_xhs_ai_traces(note))


if __name__ == "__main__":
    unittest.main()
