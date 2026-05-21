import unittest
from unittest.mock import patch

from logic_guardrail import run_logic_guardrail


class LogicGuardrailTest(unittest.TestCase):
    def test_guardrail_exception_does_not_pass(self):
        with patch("logic_guardrail._get_client", side_effect=RuntimeError("boom")):
            passed, message = run_logic_guardrail("draft", {})

        self.assertFalse(passed)
        self.assertIn("Guardrail degraded error", message)


if __name__ == "__main__":
    unittest.main()
