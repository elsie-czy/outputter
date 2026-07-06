import unittest
from unittest.mock import patch

from scripts.deconstruct_worker import _has_content_brief, _with_image_provider


class DeconstructWorkerContentBriefTest(unittest.TestCase):
    def test_has_content_brief_requires_useful_content(self):
        self.assertFalse(_has_content_brief({}))
        self.assertFalse(_has_content_brief({"内容简报": {}}))
        self.assertTrue(_has_content_brief({"内容简报": {"核心痛点": "怕踩雷"}}))
        self.assertTrue(_has_content_brief({"内容简报": {"图文页结构": ["痛点页"]}}))

    def test_with_image_provider_can_force_generation_enabled_temporarily(self):
        with patch.dict("os.environ", {
            "IMAGE_PROVIDER": "jimeng",
            "IMAGE_GEN_ENABLED": "false",
        }, clear=False):
            seen = _with_image_provider(
                "liblib",
                lambda: ("liblib", __import__("os").environ.get("IMAGE_PROVIDER"),
                         __import__("os").environ.get("IMAGE_GEN_ENABLED")),
                force_enabled=True,
            )

            self.assertEqual(seen, ("liblib", "liblib", "true"))
            self.assertEqual(__import__("os").environ.get("IMAGE_PROVIDER"), "jimeng")
            self.assertEqual(__import__("os").environ.get("IMAGE_GEN_ENABLED"), "false")


if __name__ == "__main__":
    unittest.main()
