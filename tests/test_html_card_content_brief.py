import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import html_card_generator as cards


class HtmlCardContentBriefTest(unittest.TestCase):
    def _note(self):
        return {
            "title": "测试标题",
            "body": "第一点：开篇先抛痛点\n第二点：人物关系有拉扯\n第三点：冲突递进很清楚",
            "tags": ["书评", "网文拆解"],
            "lead": "先看这套图文结构",
        }

    def _brief(self):
        return {
            "核心痛点": "读者不知道这本书值不值得追。",
            "读者收益": "三页看懂钩子、冲突和爽点。",
            "封面钩子": {
                "主标题": "值不值得追",
                "副标题": "先看这3个爆点",
                "情绪": "好奇",
                "点击理由": "快速判断作品吸引力。",
            },
            "图文页结构": ["痛点提问", "核心洞察", "证据素材"],
            "证据素材": ["简介中的重生节点", "人物关系反差", "三层冲突"],
        }

    def test_plan_cards_prefers_content_brief_structure(self):
        plan = cards._plan_cards(self._note(), "warm", 5, content_brief=self._brief())

        self.assertEqual(plan[0]["card_type"], "cover")
        self.assertEqual(plan[0]["plan_source"], "content_brief")
        self.assertEqual([card["card_type"] for card in plan], ["cover", "content", "content", "content", "summary"])
        self.assertEqual([card["page_role"] for card in plan[1:-1]], ["problem", "insight", "proof"])
        self.assertEqual(plan[1]["section_title"], "痛点提问")

    def test_plan_cards_without_brief_uses_legacy_body_split(self):
        plan = cards._plan_cards(self._note(), "warm", 3, content_brief=None)

        self.assertEqual(plan[0]["card_type"], "cover")
        self.assertNotIn("plan_source", plan[0])
        self.assertTrue(any(card["card_type"] == "content" for card in plan))

    def test_generate_cards_writes_card_plan_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(cards, "_PLAYWRIGHT_OK", True), \
                    patch.object(cards, "_screenshot_batch", return_value=[str(Path(tmp) / "xhs_card_01.png")]):
                paths = cards.generate_cards_from_note(
                    self._note(),
                    style="warm",
                    n=4,
                    output_dir=tmp,
                    content_brief=self._brief(),
                )

            plan_path = Path(tmp) / "card_plan.json"
            self.assertEqual(paths, [str(Path(tmp) / "xhs_card_01.png")])
            self.assertTrue(plan_path.exists())
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["cards"][0]["plan_source"], "content_brief")

    def test_validate_cards_finds_empty_title_and_message(self):
        errors = cards._validate_cards([
            {
                "card_type": "cover",
                "title": "",
                "subtitle": "",
                "points": [{"text": "1"}, {"text": "2"}, {"text": "3"}, {"text": "4"}],
            }
        ])

        self.assertTrue(any("标题为空" in error for error in errors))
        self.assertTrue(any("message 为空" in error for error in errors))
        self.assertTrue(any("要点超过3个" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
