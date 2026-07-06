import unittest

from scripts.deconstruct_daily import build_xhs_note, generate_title_options, _mobile_lines
from scripts.model_adapter import _ensure_analysis_shape, _local_analyze


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


if __name__ == "__main__":
    unittest.main()
