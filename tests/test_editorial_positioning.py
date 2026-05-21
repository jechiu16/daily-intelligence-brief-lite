import unittest

from analyst import build_analyst_prompt
from narrator import build_narrator_prompt
from periphery import PERIPHERY_POOL, PERIPHERY_SELECTION_RULE


class EditorialPositioningTest(unittest.TestCase):
    def test_narrator_prompt_removes_retiree_and_investment_default(self):
        prompt = build_narrator_prompt(
            analyst_draft="## 1. 今天最重要的一件事\n測試",
            hard_truths={},
            periphery_label="索馬利蘭",
            today_date="2026-05-21",
        )

        self.assertNotIn("退休人士", prompt)
        self.assertNotIn("持有股票的人", prompt)
        self.assertIn("受過良好教育", prompt)
        self.assertIn("不要投資喊單", prompt)
        self.assertIn("今日邊陲", prompt)
        self.assertIn("真的是邊陲", prompt)

    def test_analyst_prompt_requires_true_periphery(self):
        prompt = build_analyst_prompt(
            level_a="LEVEL A",
            level_b="",
            relational_flags=[],
            regime="POLICY_TRANSITION",
            framework="test framework",
            l1={},
            l2="",
            l3=[],
            kh=[],
            periphery_label="索馬利蘭",
            periphery_keywords="Somaliland Berbera port",
            knowledge_candidates=[
                {
                    "term": "事實國家",
                    "category": "politics",
                    "description": "實際運作像國家，但未被多數國家正式承認。",
                }
            ],
        )

        self.assertIn("邊陲必須真的是邊陲", prompt)
        self.assertIn("不要硬湊", prompt)
        self.assertIn("文章追蹤線索", prompt)
        self.assertIn("今日一件事候選池", prompt)
        self.assertIn("事實國家", prompt)
        self.assertIn("優先從", prompt)
        self.assertNotIn("持有股票的人 / 持有債券或定存的人 / 持有外幣的人", prompt)

    def test_periphery_pool_avoids_mainstream_centers(self):
        mainstream_terms = ["G7", "華爾街", "矽谷", "Fed", "歐盟核心"]
        pool_text = "\n".join(label + " " + keywords for label, keywords in PERIPHERY_POOL)

        self.assertIn("主流資訊", PERIPHERY_SELECTION_RULE)
        for term in mainstream_terms:
            self.assertNotIn(term, pool_text)


if __name__ == "__main__":
    unittest.main()
