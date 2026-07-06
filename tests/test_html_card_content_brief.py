import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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

    def test_plan_cards_with_work_info_uses_fixed_xhs_note_rules(self):
        analysis = {
            "作品名称": "完美耦合",
            "作者": "九阶幻方",
            "分类": ["未来架空", "女强"],
            "简介": "女主隐藏身份进入机甲学院，在规则压迫下寻找自己的选择。",
            "金句": ["我的精神力不是工具，插谁的口，我说了算。"],
            "情绪钩子": "她第一次公开耦合失控，全场陷入沉默。",
            "核心冲突": "身份暴露与自由选择之间的冲突。",
            "小红书包装": {
                "小红书标题模板": "这本星际女强真的很上头",
                "热门标签推荐": ["星际女强", "书荒推荐"],
            },
        }

        plan = cards._plan_cards(
            self._note(),
            "warm",
            5,
            content_brief=self._brief(),
            work_info={"作品名称": "完美耦合", "作者": "九阶幻方", "平台": "晋江文学城"},
            analysis=analysis,
        )

        self.assertEqual(len(plan), 5)
        self.assertEqual(plan[0]["plan_source"], "work_note_rules")
        self.assertEqual(plan[0]["card_type"], "cover")
        self.assertIn("完美耦合", plan[0]["subtitle"])
        self.assertEqual(plan[1]["section_tag"], "作品速览")
        self.assertIn("书名：完美耦合", plan[1]["points"][0]["text"])
        self.assertEqual([card["page_role"] for card in plan[2:]], ["quote", "scene", "highlight"])
        self.assertEqual(cards._validate_cards(plan), [])

    def test_work_note_rules_renumbers_pages_when_some_sections_missing(self):
        plan = cards._plan_cards(
            self._note(),
            "warm",
            5,
            work_info={"作品名称": "无金句作品", "作者": "测试作者"},
            analysis={
                "作品名称": "无金句作品",
                "作者": "测试作者",
                "情绪钩子": "女主在雨夜做出关键选择。",
                "简介": "这是一本围绕选择和成长展开的作品。",
            },
        )

        self.assertEqual([card["page_num"] for card in plan], ["01", "02", "03", "04", "05"])
        self.assertEqual([card["total_pages"] for card in plan], ["05"] * 5)

    def test_plan_cards_skips_brief_cover_and_summary_pages(self):
        brief = self._brief()
        brief["图文页结构"] = ["封面钩子", "痛点提问", "核心洞察", "证据素材", "收藏总结"]

        plan = cards._plan_cards(self._note(), "warm", 5, content_brief=brief)

        self.assertEqual([card["section_title"] for card in plan[1:-1]], ["痛点提问", "核心洞察", "证据素材"])
        self.assertEqual([card["page_role"] for card in plan[1:-1]], ["problem", "insight", "proof"])

    def test_plan_cards_without_brief_uses_legacy_body_split(self):
        plan = cards._plan_cards(self._note(), "warm", 3, content_brief=None)

        self.assertEqual(plan[0]["card_type"], "cover")
        self.assertNotIn("plan_source", plan[0])
        self.assertTrue(any(card["card_type"] == "content" for card in plan))
        self.assertEqual(cards._validate_cards(plan), [])

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

    def test_generate_cards_on_images_returns_overlay_and_raw_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            bg = Path(tmp) / "bg.png"
            bg.write_bytes(b"fake")
            expected = [str(Path(tmp) / "xhs_ai_card_01.png"), str(Path(tmp) / "xhs_ai_card_02.png")]

            with patch.object(cards, "_PLAYWRIGHT_OK", True), \
                    patch.object(cards, "_screenshot_batch", return_value=expected):
                result = cards.generate_cards_on_images(
                    self._note(),
                    {"cover": str(bg), "scene1": str(bg)},
                    style="warm",
                    n=2,
                    output_dir=tmp,
                    work_info={"作品名称": "测试作品", "作者": "测试作者"},
                    analysis={"作品名称": "测试作品", "作者": "测试作者", "简介": "测试简介"},
                )

            self.assertEqual(result["cover"], expected[0])
            self.assertEqual(result["scene1"], expected[1])
            self.assertEqual(result["raw_cover"], str(bg))
            self.assertEqual(result["raw_scene1"], str(bg))
            html = (Path(tmp) / "xhs_ai_card_01.html").read_text(encoding="utf-8")
            self.assertIn("image-bg", html)

    def test_quote_overlay_uses_one_featured_sentence(self):
        quote_card = {
            "card_type": "content",
            "page_role": "quote",
            "section_tag": "经典金句",
            "section_title": "金句摘录",
            "points": [
                {"emoji": "💬", "text": "你先养活自己再说"},
                {"emoji": "💬", "text": "第二句不应该展示"},
            ],
        }

        cards._compact_card_for_image_overlay(quote_card)

        self.assertEqual(quote_card["quote_text"], "你先养活自己再说")
        self.assertEqual(len(quote_card["points"]), 1)
        self.assertNotIn("第二句", quote_card["message"])

    def test_work_note_rules_split_cover_meta_and_description(self):
        plan = cards._plan_cards(
            self._note(),
            "warm",
            5,
            work_info={"作品名称": "噩梦时代", "作者": "天下飘火"},
            analysis={"作品名称": "噩梦时代", "作者": "天下飘火", "简介": "这句描述应该单独展示，不能和作品作者挤在一起。"},
        )
        cover = plan[0]

        self.assertEqual(cover["work_name"], "噩梦时代")
        self.assertEqual(cover["author"], "天下飘火")
        self.assertIn("这句描述", cover["cover_desc"])
        self.assertNotIn("这句描述", cover["subtitle"])

    def test_multiple_quotes_expand_to_separate_pages(self):
        plan = cards._plan_cards(
            self._note(),
            "warm",
            5,
            work_info={"作品名称": "测试书", "作者": "作者"},
            analysis={
                "作品名称": "测试书",
                "作者": "作者",
                "金句": ["第一句金句", "第二句金句", "第三句金句"],
                "简介": "简介",
            },
        )
        quote_cards = [card for card in plan if card.get("page_role") == "quote"]

        self.assertEqual([card["points"][0]["text"] for card in quote_cards], ["第一句金句", "第二句金句", "第三句金句"])

    def test_screenshot_batch_falls_back_when_playwright_launch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            html_path = Path(tmp) / "xhs_card_01.html"
            html_path.write_text("<html><body>card</body></html>", encoding="utf-8")
            fake_playwright = Mock()
            fake_playwright.__enter__ = Mock(return_value=fake_playwright)
            fake_playwright.__exit__ = Mock(return_value=None)
            fake_playwright.chromium.launch.side_effect = RuntimeError("missing browser")

            with patch.object(cards, "_PLAYWRIGHT_OK", True), \
                    patch.object(cards, "sync_playwright", return_value=fake_playwright), \
                    patch.object(cards, "_screenshot_batch_with_chromium_cli", return_value=["fallback.png"]) as fallback:
                result = cards._screenshot_batch([str(html_path)], tmp)

            self.assertEqual(result, ["fallback.png"])
            fallback.assert_called_once_with([str(html_path)], tmp)

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
