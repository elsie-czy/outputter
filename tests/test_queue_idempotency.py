import os
import tempfile
import unittest

from scripts import queue_manager
from scripts.utils import read_jsonl, write_jsonl


class QueueIdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.old_queue_file = queue_manager.QUEUE_FILE
        queue_manager.QUEUE_FILE = os.path.join(self.tmpdir.name, "queue.jsonl")

    def tearDown(self):
        queue_manager.QUEUE_FILE = self.old_queue_file
        self.tmpdir.cleanup()

    def test_enqueue_skips_existing_and_duplicate_record_ids(self):
        count = queue_manager.enqueue_works([
            {"record_id": "rid-1", "作品名称": "A"},
            {"record_id": "rid-1", "作品名称": "A again"},
            {"record_id": "", "作品名称": "missing id"},
        ])

        self.assertEqual(count, 1)
        items = read_jsonl(queue_manager.QUEUE_FILE)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["record_id"], "rid-1")

        count = queue_manager.enqueue_works([{"record_id": "rid-1", "作品名称": "A third"}])
        self.assertEqual(count, 0)
        self.assertEqual(len(read_jsonl(queue_manager.QUEUE_FILE)), 1)

    def test_status_update_updates_duplicate_records_and_stops_reconsume(self):
        write_jsonl(queue_manager.QUEUE_FILE, [
            {"record_id": "rid-1", "status": "pending"},
            {"record_id": "rid-1", "status": "pending"},
        ])

        self.assertTrue(queue_manager.update_status("rid-1", "done", note_content="ok"))
        items = read_jsonl(queue_manager.QUEUE_FILE)
        self.assertEqual([item["status"] for item in items], ["done", "done"])
        self.assertIsNone(queue_manager.get_next_pending())


if __name__ == "__main__":
    unittest.main()
