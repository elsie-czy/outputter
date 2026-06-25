import unittest
from unittest.mock import Mock, patch

from scripts import quality_scorer


class QualityScorerTest(unittest.TestCase):
    @patch.dict("os.environ", {"MODEL_PROVIDER": "local"}, clear=False)
    def test_score_note_skips_remote_when_provider_is_local(self):
        score = quality_scorer.score_note("测试笔记")

        self.assertTrue(score["_fallback"])
        self.assertIn("MODEL_PROVIDER=local", score["suggestion"])

    @patch.dict(
        "os.environ",
        {
            "MODEL_PROVIDER": "qwen",
            "QWEN_API_KEY": "test-key",
            "QWEN_BASE_URLS": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "QWEN_MODEL": "qwen-plus",
        },
        clear=False,
    )
    @patch("scripts.quality_scorer.time.sleep", return_value=None)
    @patch("scripts.quality_scorer.requests.post")
    def test_score_note_includes_dashscope_error_detail(self, post, _sleep):
        response = Mock()
        response.status_code = 400
        response.json.return_value = {
            "error": {
                "code": "Arrearage",
                "message": "Access denied",
            }
        }
        post.return_value = response

        score = quality_scorer.score_note("测试笔记")

        self.assertTrue(score["_fallback"])
        self.assertIn("Arrearage", score["suggestion"])
        self.assertIn("HTTP 400", score["suggestion"])


if __name__ == "__main__":
    unittest.main()
