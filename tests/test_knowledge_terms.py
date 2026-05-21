import unittest

from knowledge_terms import format_knowledge_candidates, select_knowledge_candidates


class KnowledgeTermsTest(unittest.TestCase):
    def test_select_candidates_matches_context_and_skips_used_terms(self):
        candidates = select_knowledge_candidates(
            "Somaliland Berbera port recognition shipping",
            used_terms=[{"term": "轉運港"}],
            limit=5,
        )
        terms = [item["term"] for item in candidates]

        self.assertIn("事實國家", terms)
        self.assertNotIn("轉運港", terms)

    def test_format_candidates_for_prompt(self):
        text = format_knowledge_candidates([
            {
                "term": "咽喉點",
                "category": "geography_shipping",
                "description": "狹窄通道。",
            }
        ])

        self.assertIn("咽喉點", text)
        self.assertIn("geography_shipping", text)


if __name__ == "__main__":
    unittest.main()
