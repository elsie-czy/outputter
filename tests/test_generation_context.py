import unittest
from unittest.mock import patch

from scripts.generation_context import build_generation_context


class GenerationContextTest(unittest.TestCase):
    @patch("scripts.feishu_client.FeishuClient")
    def test_combines_task_feedback_before_feishu_feedback(self, client_cls):
        client = client_cls.return_value
        client.is_configured.return_value = True
        client.get_top_notes.return_value = [
            {"标题": "高赞标题", "正文": "高赞正文", "标签": "#写作", "点赞": 100, "收藏": 20}
        ]
        client.get_recent_modifications.return_value = [
            {"time": "20260616 10:00", "field": "字段: 正文", "reason": "说明: 缩短"}
        ]

        context = build_generation_context(
            {
                "modification_log": (
                    "20260615 09:00 | 字段: 标题 | 说明: 更强钩子 | 评分:82\n"
                    "20260616 09:30 | 字段: 标签 | 说明: 去掉泛标签 | 评分:86"
                )
            },
            reference_limit=3,
            feedback_limit=3,
        )

        self.assertEqual(context["reference_notes"][0]["标题"], "高赞标题")
        self.assertEqual(context["recent_feedback"][0]["field"], "字段: 标签")
        self.assertEqual(context["recent_feedback"][1]["field"], "字段: 标题")
        self.assertEqual(context["recent_feedback"][2]["field"], "字段: 正文")
        client.get_recent_modifications.assert_called_once_with(limit=1)

    @patch("scripts.feishu_client.FeishuClient", side_effect=RuntimeError("offline"))
    def test_feishu_failure_does_not_block_context(self, _client_cls):
        context = build_generation_context(
            {"modification_log": "20260616 09:30 | 字段: 标题 | 说明: 更口语 | 评分:80"}
        )

        self.assertEqual(context["reference_notes"], [])
        self.assertEqual(context["recent_feedback"][0]["reason"], "说明: 更口语")


if __name__ == "__main__":
    unittest.main()
