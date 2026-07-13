import unittest

from scripts.conversion_scorer import default_comment_hook, review_note_conversion


class ConversionScorerTest(unittest.TestCase):
    def test_bad_comment_hook_gets_replaced(self):
        review = review_note_conversion(
            "【标题】测试\n\n这本末世文可以看。\n\n欢迎评论，大家怎么看？\n#末世文",
            note_type="normal_recommendation",
        )

        self.assertIn("书名丢我", review["comment_hook"])
        self.assertNotIn("欢迎评论", review["comment_hook"])
        self.assertEqual(review["comment_hook_type"], "报书名")
        self.assertTrue(review["first_comment"])
        self.assertGreaterEqual(len(review["reply_prompts"]), 3)

    def test_note_type_defaults_are_distinct(self):
        self.assertIn("最怕什么雷", default_comment_hook("warning_review"))
        self.assertIn("求投喂", default_comment_hook("comment_experiment"))
        self.assertIn("呼声最高", default_comment_hook("booklist"))

    def test_group_survival_context_avoids_female_lead_templates(self):
        review = review_note_conversion(
            "《末路危途》囚车堵在高速上，外面是丧尸，里面是一车死刑犯。\n#末世文 #丧尸文",
            note_type="normal_recommendation",
            work={
                "作品名称": "末路危途",
                "取向": "无CP",
                "简介": "押送死刑犯的囚车被困高速，囚犯在丧尸横行的世界里求生。",
            },
        )

        joined = " ".join([
            review["comment_hook"],
            review["first_comment"],
            review["follow_reason"],
            " ".join(review["reply_prompts"]),
        ])
        self.assertIn("活人", review["comment_hook"])
        self.assertIn("硬核丧尸", review["first_comment"])
        self.assertNotIn("女主", joined)


if __name__ == "__main__":
    unittest.main()
