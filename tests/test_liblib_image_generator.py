import os
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

from scripts import image_generator


class LiblibImageGeneratorTest(unittest.TestCase):
    def test_generate_images_posts_signed_text2img_and_polls_status(self):
        submit = Mock()
        submit.status_code = 200
        submit.json.return_value = {"code": 0, "data": {"generateUuid": "task-123"}}

        status = Mock()
        status.status_code = 200
        status.json.return_value = {
            "code": 0,
            "data": {
                "generateStatus": 5,
                "images": [{"imageUrl": "https://example.com/out.png"}],
            },
        }

        with patch.dict(os.environ, {
            "IMAGE_PROVIDER": "liblib",
            "LIBLIB_ACCESS_KEY": "ak-test",
            "LIBLIB_SECRET_KEY": "sk-test",
            "LIBLIB_BASE_URL": "https://openapi.liblibai.cloud",
            "LIBLIB_IMAGE_SIZE": "768x1024",
            "LIBLIB_STEPS": "30",
            "LIBLIB_POLL_TIMES": "1",
            "LIBLIB_POLL_INTERVAL_SEC": "0",
            "IMAGE_CACHE_ENABLED": "false",
        }, clear=False), \
                patch.object(image_generator.requests, "post", side_effect=[submit, status]) as post, \
                patch.object(image_generator, "_download_image", return_value="temp/generated_images/out.png") as dl:
            paths = image_generator.generate_images_from_prompt("测试提示词", n=1)

        self.assertEqual(paths, ["temp/generated_images/out.png"])
        self.assertEqual(post.call_count, 2)
        first_url = post.call_args_list[0].args[0]
        parsed = urlparse(first_url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.path, "/api/generate/webui/text2img/ultra")
        self.assertEqual(query["AccessKey"], ["ak-test"])
        self.assertIn("Signature", query)
        self.assertIn("Timestamp", query)
        self.assertIn("SignatureNonce", query)

        payload = post.call_args_list[0].kwargs["json"]
        self.assertEqual(payload["templateUuid"], "5d7e67009b344550bc1aa6ccbfa1d7f4")
        self.assertEqual(payload["generateParams"]["imageSize"], {"width": 768, "height": 1024})
        self.assertEqual(payload["generateParams"]["imgCount"], 1)
        self.assertEqual(payload["generateParams"]["steps"], 30)

        status_payload = post.call_args_list[1].kwargs["json"]
        self.assertEqual(status_payload, {"generateUuid": "task-123"})
        dl.assert_called_once_with("https://example.com/out.png")

    def test_missing_liblib_keys_raises_clear_error(self):
        with patch.dict(os.environ, {
            "IMAGE_PROVIDER": "liblib",
            "LIBLIB_ACCESS_KEY": "",
            "LIBLIB_SECRET_KEY": "",
        }, clear=False):
            with self.assertRaisesRegex(RuntimeError, "LIBLIB_ACCESS_KEY"):
                image_generator.generate_images_from_prompt("测试提示词", n=1)


if __name__ == "__main__":
    unittest.main()
