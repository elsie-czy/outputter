import unittest

from scripts.deconstruct_daily import _build_image_prompts


class ImagePromptBuilderTest(unittest.TestCase):
    def test_bl_quick_transmigration_prompt_keeps_story_anchors_without_female_lead(self):
        work = {
            "作品名称": "BE狂魔求生系统[快穿]",
            "分类": "快穿、系统、纯爱",
            "简介": "许其琛进入求生系统，与技术大佬在不同小说世界里改写BE结局。",
            "取向": "纯爱",
        }
        analysis = {
            "人物设定": {
                "女主": "无（纯爱文，无女主）",
                "男主": "技术大佬·计划通·小太阳痴情攻，有虎牙，擅长投喂糖。",
                "亮点配角": "系统常给任务提示。",
            },
            "冲突设计": {
                "第一层": "许其琛必须进入自己的小说与主角恋爱，但他有情感障碍。",
                "第二层": "攻略对象常反客为主，让许其琛的攻略计划失败。",
                "第三层": "现实世界中两人错过十年，最终需回归现实。",
            },
            "小红书包装": {"封面图描述建议": "男主虎牙特写，背景是系统界面和糖果元素。"},
            "内容简报": {
                "封面钩子": {"主标题": "虎牙投喂糖", "副标题": "系统提示反被亲"},
                "图文页结构": ["封面：男主虎牙特写+系统界面", "甜宠互动场景"],
                "证据素材": ["虎牙投喂糖", "快穿系统设定"],
            },
        }

        prompts = _build_image_prompts(work, analysis)
        joined = "\n".join(prompts)

        self.assertEqual(len(prompts), 5)
        self.assertNotIn("[visual scene description]", joined)
        self.assertNotIn("Female lead", joined)
        self.assertNotIn("女主", joined)
        self.assertIn("two male leads", joined)
        self.assertIn("quick transmigration arcs", joined)
        self.assertIn("glowing mission interface", joined)
        self.assertIn("small fang smile", joined)
        self.assertIn("candy motif", joined)
        self.assertIn("NO text", joined)

    def test_prompt_has_no_cjk_characters(self):
        work = {"分类": "星际、机甲、女强", "简介": "女主误入机甲学院，用精神力破局。"}
        analysis = {
            "人物设定": {"女主": "清醒行动派", "男主": "冷静指挥官"},
            "冲突设计": {"第一层": "机甲训练危机", "第二层": "身份暴露", "第三层": "战场破局"},
        }

        prompts = _build_image_prompts(work, analysis)
        joined = "\n".join(prompts)

        self.assertFalse(any("\u4e00" <= ch <= "\u9fff" for ch in joined))
        self.assertIn("mecha cockpit", joined)


if __name__ == "__main__":
    unittest.main()
