import unittest
from unittest.mock import Mock, patch

from memory_layer import save_daily_report


class MemoryLayerNotionTest(unittest.TestCase):
    def test_save_daily_report_existing_page_patch_failure_raises(self):
        response = Mock()
        response.raise_for_status.side_effect = RuntimeError("patch failed")

        with patch("memory_layer._find_page_by_title", return_value="page-id"):
            with patch("memory_layer.httpx.patch", return_value=response):
                with self.assertRaises(RuntimeError):
                    save_daily_report("2026-05-21", "report")


if __name__ == "__main__":
    unittest.main()

