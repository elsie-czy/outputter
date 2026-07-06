import unittest

from scripts.search import _fallback_info
from scripts.source_cleaner import clean_source_synopsis


class SourceCleanerTest(unittest.TestCase):
    def test_splits_story_facts_from_notices(self):
        raw = (
            "【2023年6月24号18点第二册实体书出版开售，限时前两分钟有亲笔签名】"
            "【同名有声剧在喜马拉雅上线啦】"
            "卫三靠捡垃圾攒学费，误报单兵专业后用工程师思维破局。"
        )

        cleaned = clean_source_synopsis(raw)

        self.assertIn("卫三靠捡垃圾攒学费", cleaned["剧情简介"])
        self.assertTrue(any("实体书" in item for item in cleaned["非剧情信息"]))
        self.assertTrue(any("喜马拉雅" in item for item in cleaned["非剧情信息"]))
        self.assertNotIn("实体书", cleaned["剧情简介"])
        self.assertNotIn("喜马拉雅", cleaned["剧情简介"])

    def test_search_fallback_returns_clean_synopsis_fields(self):
        info = _fallback_info(
            {
                "作品名称": "测试作品",
                "作者": "测试作者",
                "平台": "local",
                "简介": "【实体书出版开售】女主重回命运转折点，先破局再反击。",
            }
        )

        self.assertIn("女主重回命运转折点", info["剧情简介"])
        self.assertIn("非剧情信息", info)
        self.assertNotIn("实体书", info["剧情简介"])


if __name__ == "__main__":
    unittest.main()
