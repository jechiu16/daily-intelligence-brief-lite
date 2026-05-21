import unittest

from hard_truths import build_hard_truths, classify_regime, compute_fiscal_dominance, compute_real_yield_direction


class HardTruthsMissingDataTest(unittest.TestCase):
    def test_classify_regime_tolerates_missing_fred_values(self):
        regime = classify_regime({
            "forward_5y5y": None,
            "SPX_direction": "up",
            "credit_stress": False,
        })

        self.assertEqual(regime, "RISK_ON_GROWTH")

    def test_build_hard_truths_tolerates_missing_liquidity_change(self):
        hard_truths = build_hard_truths({
            "forward_5y5y": None,
            "net_liquidity_change": None,
        })

        self.assertEqual(hard_truths["liquidity_direction"], "neutral")
        self.assertIn("current_regime", hard_truths)

    def test_non_numeric_values_do_not_raise(self):
        self.assertEqual(compute_real_yield_direction("bad", 1.0), "flat")
        self.assertFalse(compute_fiscal_dominance({
            "imf_us_debt_gdp": "bad",
            "imf_us_fiscal_balance": -4.0,
        }))
        self.assertEqual(classify_regime({"fed_cuts_priced_in": "bad"}), "POLICY_TRANSITION")


if __name__ == "__main__":
    unittest.main()
