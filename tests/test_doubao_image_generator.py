import os
import unittest
from unittest.mock import Mock, patch

from scripts import image_generator


class DoubaoImageGeneratorTest(unittest.TestCase):
    def test_seedream_provider_uses_ark_openai_compatible_endpoint(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = {"data": [{"url": "https://example.com/out.png"}]}

        with patch.dict(os.environ, {
            "IMAGE_PROVIDER": "doubao_seedream_4_5",
            "DOUBAO_API_KEY": "ark-test",
            "DOUBAO_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
            "DOUBAO_IMAGE_SIZE": "1440x2560",
            "IMAGE_API_KEY": "",
            "IMAGE_MODEL": "",
            "IMAGE_CACHE_ENABLED": "false",
        }, clear=False), \
                patch.object(image_generator.requests, "post", return_value=response) as post, \
                patch.object(image_generator, "_download_image", return_value="temp/generated_images/out.png") as dl:
            paths = image_generator.generate_images_from_prompt("测试提示词", n=1)

        self.assertEqual(paths, ["temp/generated_images/out.png"])
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], "https://ark.cn-beijing.volces.com/api/v3/images/generations")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer ark-test")

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], "doubao-seedream-4-5-251128")
        self.assertEqual(payload["prompt"], "测试提示词")
        self.assertEqual(payload["n"], 1)
        self.assertEqual(payload["size"], "1440x2560")
        dl.assert_called_once_with("https://example.com/out.png")

    def test_missing_doubao_key_raises_clear_error(self):
        with patch.dict(os.environ, {
            "IMAGE_PROVIDER": "doubao_seedream_5_lite",
            "DOUBAO_API_KEY": "",
            "ARK_API_KEY": "",
            "IMAGE_API_KEY": "",
        }, clear=False):
            with self.assertRaisesRegex(RuntimeError, "DOUBAO_API_KEY"):
                image_generator.generate_images_from_prompt("测试提示词", n=1)


if __name__ == "__main__":
    unittest.main()
