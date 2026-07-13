import unittest

from scripts.material_evidence import build_material_fact_check, public_fact_texts
from scripts.material_quality import assess_material_quality


class MaterialEvidenceTest(unittest.TestCase):
    def test_fact_check_marks_intro_and_reader_reviews_separately(self):
        work = {
            "作品名称": "测试书",
            "简介": "女主被困雪山。她必须在三天内找到失踪的弟弟。",
            "读者评论": ["节奏很紧张，开头就有压迫感"],
        }
        search_info = {
            "搜索模式": "jjwxc_title",
            "搜索来源链接": "https://example.com/book",
        }

        fact_check = build_material_fact_check(work, search_info)

        self.assertEqual(fact_check["generation_mode"], "synopsis_grounded")
        self.assertTrue(fact_check["usable_facts"])
        self.assertTrue(fact_check["cautious_facts"])
        self.assertEqual(fact_check["usable_facts"][0]["status"], "可写")
        self.assertEqual(fact_check["cautious_facts"][0]["status"], "谨慎写")

    def test_public_fact_texts_only_uses_directly_writable_facts_by_default(self):
        fact_check = build_material_fact_check(
            {"简介": "囚车堵在高速公路上。押运警察遇难。", "读者评论": ["有人说像行尸走肉"]},
            {"搜索模式": "jjwxc_title", "搜索来源链接": "https://example.com/book"},
        )

        texts = public_fact_texts(fact_check)

        self.assertIn("囚车堵在高速公路上", " ".join(texts))
        self.assertNotIn("行尸走肉", " ".join(texts))

    def test_material_quality_embeds_fact_check(self):
        quality = assess_material_quality(
            {"简介": "囚车堵在高速上。押运警察遇难。囚犯被锁在车厢内侥幸存活。"},
            {"搜索模式": "jjwxc_title", "搜索来源链接": "https://example.com/book"},
        )

        self.assertIn("fact_check", quality)
        self.assertIn(quality["fact_check"]["generation_mode"], ["synopsis_grounded", "grounded_note"])


if __name__ == "__main__":
    unittest.main()
