import unittest
from unittest.mock import Mock, patch

from preflight import PreflightError, run_preflight, validate_fred_key


class PreflightTest(unittest.TestCase):
    def test_missing_required_env_reports_names_without_values(self):
        env = {
            "GOOGLE_API_KEY": "google-secret",
            "FRED_API_KEY": "",
            "NOTION_TOKEN": "",
            "NOTION_DATABASE_ID": "database-secret",
        }

        with self.assertRaises(PreflightError) as ctx:
            run_preflight(env)

        message = str(ctx.exception)
        self.assertIn("FRED_API_KEY", message)
        self.assertIn("NOTION_TOKEN", message)
        self.assertNotIn("google-secret", message)
        self.assertNotIn("database-secret", message)

    def test_fred_invalid_key_raises_clear_error(self):
        response = Mock()
        response.raise_for_status.side_effect = RuntimeError("401")

        with patch("preflight.httpx.get", return_value=response):
            with self.assertRaises(PreflightError) as ctx:
                validate_fred_key("bad-key")

        self.assertIn("FRED_API_KEY validation failed", str(ctx.exception))
        self.assertNotIn("bad-key", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()

