import unittest
from unittest.mock import Mock, patch

from scripts.search import _build_search_info, _extract_duckduckgo_results, _extract_jjwxc_chapters, _fallback_info, search_work_info
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

    def test_extracts_jjwxc_chapter_titles(self):
        html = """
        <a href="onebook.php?novelid=123&chapterid=1">第一章 安全屋醒来</a>
        <a href="onebook.php?novelid=123&chapterid=2">第二章 第一次死亡</a>
        <a href="onebook.php?novelid=123&chapterid=3">作者有话说</a>
        """

        chapters = _extract_jjwxc_chapters(html)

        self.assertEqual(chapters[:2], ["安全屋醒来", "第一次死亡"])
        self.assertNotIn("作者有话说", chapters)

    @patch("scripts.search.requests.get")
    def test_search_info_merges_rich_jjwxc_material(self, mock_get):
        response = Mock()
        response.text = """
        <a href="onebook.php?novelid=123&chapterid=1">第一章 安全屋醒来</a>
        <a href="onebook.php?novelid=123&chapterid=2">第二章 反复死亡</a>
        评论区都说女主反复死亡这段很好看。
        内容标签：末世 无限复活
        """
        mock_get.return_value = response

        info = _build_search_info(
            {"作品名称": "末世测试", "作者": "陆喵", "简介": ""},
            {
                "platform": "晋江",
                "title": "末世测试",
                "author": "陆喵",
                "link": "https://www.jjwxc.net/onebook.php?novelid=123",
                "desc": "女主会无限复活，每次死后回到安全屋。",
            },
            "jjwxc_exact",
        )

        self.assertIn("目录", info)
        self.assertIn("安全屋醒来", info["目录"])
        self.assertIn("正文片段", info)
        self.assertTrue(any("内容标签" in item for item in info["正文片段"]))

    def test_extract_duckduckgo_results(self):
        html = '''
        <a class="result__a" href="https://example.com/book">末路危途 那四儿 简介</a>
        <a class="result__snippet">末路危途讲押送死刑犯的囚车被困高速。</a>
        '''

        results = _extract_duckduckgo_results(html)

        self.assertEqual(results[0]["url"], "https://example.com/book")
        self.assertIn("囚车被困高速", results[0]["snippet"])

    @patch("scripts.search._search_fanqie", return_value={})
    @patch("scripts.search._search_jjwxc", return_value={})
    @patch("scripts.search.requests.get")
    def test_search_work_info_expands_when_platform_search_is_thin(self, mock_get, _jjwxc, _fanqie):
        response = Mock()
        response.text = '''
        <a class="result__a" href="https://example.com/book">末路危途 那四儿 简介</a>
        <a class="result__snippet">末路危途讲押送死刑犯的囚车被困高速。</a>
        '''
        mock_get.return_value = response

        info = search_work_info({
            "作品名称": "末路危途",
            "作者": "那四儿",
            "简介": "押送死刑犯的囚车被困高速。",
        })

        self.assertEqual(info["搜索模式"], "web_expanded")
        self.assertIn("网络搜索摘要", info)
        self.assertTrue(info["搜索来源链接"])


if __name__ == "__main__":
    unittest.main()
