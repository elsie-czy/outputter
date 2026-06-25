import unittest
from unittest.mock import patch

from flask import Flask

from scripts.web.routes import note_api, task_detail_page


class GenerationContextInjectionTest(unittest.TestCase):
    def test_task_detail_regenerate_passes_context_to_model(self):
        app = Flask(__name__)
        app.register_blueprint(task_detail_page.bp)
        context = {
            "reference_notes": [{"标题": "样本标题"}],
            "recent_feedback": [{"time": "20260616", "field": "字段: 标题", "reason": "说明: 更短"}],
        }
        task = {
            "record_id": "task-1",
            "work_name": "作品A",
            "author": "作者A",
            "platform": "平台A",
            "category": "分类A",
        }

        with patch.object(task_detail_page, "_find_task", return_value=task), \
                patch.object(task_detail_page, "build_generation_context", return_value=context), \
                patch.object(task_detail_page, "analyze_work", return_value={"小红书包装": {}}) as analyze, \
                patch.object(task_detail_page, "build_xhs_note", return_value="note"), \
                patch.object(task_detail_page, "score_note", return_value={"total": 88}), \
                patch.object(task_detail_page, "update_task_fields", return_value=True):
            response = app.test_client().post("/api/task/task-1/regenerate-note")

        self.assertEqual(response.status_code, 200)
        analyze.assert_called_once_with(
            {
                "作品名称": "作品A",
                "作者": "作者A",
                "平台": "平台A",
                "分类": "分类A",
            },
            reference_notes=context["reference_notes"],
            recent_feedback=context["recent_feedback"],
        )
        self.assertEqual(response.get_json()["data"]["generation_context"]["reference_notes"], 1)

    def test_note_api_regenerate_passes_context_to_model(self):
        app = Flask(__name__)
        app.register_blueprint(note_api.bp)
        context = {
            "reference_notes": [{"标题": "样本标题"}],
            "recent_feedback": [{"time": "20260616", "field": "字段: 正文", "reason": "说明: 更具体"}],
        }
        queue = {
            "items": [{
                "record_id": "task-2",
                "work_name": "作品B",
                "author": "作者B",
                "platform": "平台B",
                "category": "分类B",
            }]
        }

        with patch("scripts.queue_manager.get_queue", return_value=queue), \
                patch("scripts.queue_manager.update_task_fields", return_value=True), \
                patch.object(note_api, "build_generation_context", return_value=context), \
                patch.object(note_api, "analyze_work", return_value={"小红书包装": {}}) as analyze, \
                patch.object(note_api, "build_xhs_note", return_value="note"), \
                patch.object(note_api, "score_note", return_value={"total": 90}):
            response = app.test_client().post("/api/note/task-2/regenerate", json={})

        self.assertEqual(response.status_code, 200)
        analyze.assert_called_once_with(
            {
                "作品名称": "作品B",
                "作者": "作者B",
                "平台": "平台B",
                "分类": "分类B",
            },
            reference_notes=context["reference_notes"],
            recent_feedback=context["recent_feedback"],
        )
        self.assertEqual(response.get_json()["data"]["generation_context"]["recent_feedback"], 1)


if __name__ == "__main__":
    unittest.main()
