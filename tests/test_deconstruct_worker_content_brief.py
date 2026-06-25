import unittest

from scripts.deconstruct_worker import _has_content_brief


class DeconstructWorkerContentBriefTest(unittest.TestCase):
    def test_has_content_brief_requires_useful_content(self):
        self.assertFalse(_has_content_brief({}))
        self.assertFalse(_has_content_brief({"内容简报": {}}))
        self.assertTrue(_has_content_brief({"内容简报": {"核心痛点": "怕踩雷"}}))
        self.assertTrue(_has_content_brief({"内容简报": {"图文页结构": ["痛点页"]}}))


if __name__ == "__main__":
    unittest.main()
