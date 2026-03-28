from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from devlink_dashboard.messages import build_cmd_message
from devlink_dashboard.session import JsonlRecorder, iter_recorded_lines, iter_recorded_messages


class SessionTests(unittest.TestCase):
    def test_record_and_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "session.jsonl"
            with JsonlRecorder(path) as recorder:
                recorder.record_message(
                    build_cmd_message(device="leg", command_id=1, name="demo.stop", args={})
                )

            lines = list(iter_recorded_lines(path))
            messages = list(iter_recorded_messages(path))

            self.assertEqual(len(lines), 1)
            self.assertEqual(messages[0].type, "cmd")
            self.assertEqual(messages[0].name, "demo.stop")


if __name__ == "__main__":
    unittest.main()
