import json
import unittest
from unittest.mock import Mock, patch

from scripts import model_adapter, quality_scorer


class DeepSeekProviderConfigTest(unittest.TestCase):
    @patch.dict(
        "os.environ",
        {
            "MODEL_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": "deepseek-key",
            "DEEPSEEK_MODEL": "deepseek-chat",
            "OPENAI_API_KEY": "bigmodel-key",
            "OPENAI_MODEL": "glm-4-plus",
            "OPENAI_BASE_URL": "https://open.bigmodel.cn/api/paas/v4",
            "OPENAI_MAX_RETRIES": "1",
        },
        clear=False,
    )
    @patch("scripts.model_adapter.requests.post")
    def test_model_adapter_uses_deepseek_endpoint_and_model(self, post):
        response = Mock()
        response.status_code = 200
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "开篇套路": ["开场", "冲突", "反转"],
                                "人物设定": {"女主": "主角", "男主": "搭档", "亮点配角": "配角"},
                                "冲突设计": {"第一层": "外部阻力", "第二层": "关系选择", "第三层": "价值冲突"},
                                "情绪触发": ["好奇", "爽感", "期待"],
                                "金句": ["一", "二", "三", "四", "五"],
                                "卖点分析": {"核心卖点": "作品卖点", "辅助卖点": []},
                                "小红书包装": {"小红书标题模板": "测试标题"},
                                "内容简报": {"标题候选": ["测试标题"]},
                                "配图提示词": ["图一", "图二", "图三", "图四"],
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        post.return_value = response

        model_adapter._openai_analyze({"作品名称": "测试作品", "简介": "测试简介"})

        url = post.call_args.args[0]
        payload = post.call_args.kwargs["json"]
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(payload["model"], "deepseek-chat")
        self.assertEqual(headers["Authorization"], "Bearer deepseek-key")

    @patch.dict(
        "os.environ",
        {
            "MODEL_PROVIDER": "deepseek",
            "DEEPSEEK_API_KEY": "deepseek-key",
            "DEEPSEEK_MODEL": "deepseek-chat",
            "OPENAI_API_KEY": "bigmodel-key",
            "OPENAI_MODEL": "glm-4-plus",
            "OPENAI_BASE_URL": "https://open.bigmodel.cn/api/paas/v4",
        },
        clear=False,
    )
    @patch("scripts.quality_scorer.requests.post")
    def test_quality_scorer_uses_deepseek_endpoint_and_model(self, post):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "title_appeal": 18,
                                "emotion_density": 18,
                                "collection_value": 18,
                                "interaction_guide": 12,
                                "xhs_style_match": 12,
                                "ai_trace": 8,
                                "total": 86,
                                "grade": "good",
                                "suggestion": "可发布",
                            },
                            ensure_ascii=False,
                        )
                    }
                }
            ]
        }
        post.return_value = response

        quality_scorer.score_note("测试笔记")

        url = post.call_args.args[0]
        payload = post.call_args.kwargs["json"]
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(payload["model"], "deepseek-chat")
        self.assertEqual(headers["Authorization"], "Bearer deepseek-key")


if __name__ == "__main__":
    unittest.main()
