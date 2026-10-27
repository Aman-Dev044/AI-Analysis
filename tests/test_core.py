import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import extractor, google_calendar, insights, plan, summarizer  # noqa: E402
from services.ollama_client import strip_thinking  # noqa: E402

PLAN = """THREE-YEAR WORK SCHEDULE
Period: 12 October 2026 to 11 October 2029
Daily routine: 09:00-09:30 planning the day. 09:30-11:30 focused work session one.
Weekday theme: Monday is for planning weekly deliverables. Tuesday and Wednesday are for focused development. Thursday is for testing results. Friday is for reviewing progress.

--- YEAR 1 / QUARTER 1: FOUNDATION & BASELINE (12 October 2026 to 11 January 2027) ---

Quarter 1 runs for a while. I will organize projects and establish baselines. The quarterly review will take place on 11 January 2027, covering progress.

YEAR 1 / MONTH 1 (12 October 2026 to 11 November 2026), Quarter 1 month 1:
In the first month, I will organize all projects. This plan month has 23 days. The monthly review is on 11 November 2026, when I check.
"""


class InsightTests(unittest.TestCase):
    def test_dates_labels_and_expiry(self):
        text = "Policy No: AB123\nIssued on 01/02/2025\nValid until 15 March 2027\nPremium: Rs. 12,450"
        info = insights.analyze(text, today=date(2027, 3, 1))
        labels = {d["label"] for d in info["dates"]}
        self.assertIn("expiry", labels)
        self.assertEqual(info["expiry"]["status"], "expiring_soon")
        self.assertEqual(info["expiry"]["days_remaining"], 14)
        self.assertIn("Rs. 12,450", info["amounts"])
        self.assertEqual(info["doc_type"], "Insurance policy")

    def test_ambiguous_numeric_date_needs_verification(self):
        parsed, ambiguous = insights.parse_date("03/04/2027")
        self.assertEqual(parsed, date(2027, 4, 3))
        self.assertTrue(ambiguous)
        self.assertEqual(insights.parse_date("25/12/2026"), (date(2026, 12, 25), False))

    def test_no_expiry_without_label(self):
        self.assertIsNone(insights.analyze("Meeting on 12 October 2026.")["expiry"])


class PlanTests(unittest.TestCase):
    def test_structured_plan_today(self):
        p = plan.detect_plan(PLAN, today=date(2026, 10, 22))
        self.assertTrue(p["active"])
        self.assertEqual(p["today"]["weekday"], "Thursday")
        self.assertEqual(p["today"]["focus"], "testing results")
        self.assertEqual(p["month"]["review_date"], "2026-11-11")
        self.assertEqual(p["quarter"]["review_date"], "2027-01-11")
        self.assertEqual(p["week"][1]["focus"], "focused development")
        self.assertEqual(p["routine"][0]["from"], "09:00")

    def test_tabular_schedule(self):
        text = "date | activity | start\n2026-10-22 | Client meeting | 10:00 AM\n2026-10-23 | Report | 09:00 AM"
        p = plan.detect_plan(text, today=date(2026, 10, 22))
        self.assertEqual(p["kind"], "tabular")
        self.assertEqual(p["today"]["focus"], "Client meeting")

    def test_non_plan(self):
        self.assertIsNone(plan.detect_plan("Just a letter."))


class SummarizerTests(unittest.TestCase):
    def test_split_chunks_respects_size(self):
        text = "\n\n".join(("Paragraph %d. " % i) * 40 for i in range(30))
        chunks = summarizer.split_chunks(text, 2000)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(c) <= 2600 for c in chunks))
        self.assertEqual("".join(chunks).count("Paragraph 29."), 40)

    def test_clean_markdown_and_thinking(self):
        self.assertEqual(summarizer.clean_markdown("```markdown\n# Hi\n```"), "# Hi")
        self.assertEqual(
            summarizer.clean_markdown("**TL;DR:** A licence.\n\n###Key points\n- a\n##\n### TL;DR\nBody"),
            "A licence.\n\n### Key points\n- a\n\nBody",
        )
        self.assertEqual(strip_thinking("<think>x</think>Answer"), "Answer")
        self.assertEqual(strip_thinking("Partial <think>still thinking"), "Partial ")


class ExtractorTests(unittest.TestCase):
    def test_word_binary_text_cleanup(self):
        raw = "Title\rName\x07Aman\x07\x07Fee\x07₹500\x07\x07\x13 HYPERLINK \"x\" \x14site\x15 end"
        self.assertEqual(extractor._clean_word_text(raw), "Title\nName | Aman\nFee | ₹500\nsite end")

    def test_svg_text_fallback(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><text x="1" y="9">Due 30 November 2026</text></svg>'
        result = extractor.extract(svg, ".svg", lambda *_: None)
        self.assertIn("30 November 2026", result.text)


class GoogleCalendarTests(unittest.TestCase):
    def test_oauth_flow_restores_pkce_code_verifier(self):
        from unittest.mock import patch

        with patch.object(google_calendar.Config, "GOOGLE_CLIENT_ID", "test-client-id"), \
                patch.object(google_calendar.Config, "GOOGLE_CLIENT_SECRET", "test-client-secret"), \
                patch.object(google_calendar.Config, "GOOGLE_REDIRECT_URI",
                             "http://localhost:5000/google-calendar/callback"):
            initial_flow = google_calendar._flow()
            _, state = initial_flow.authorization_url()
            callback_flow = google_calendar._flow(
                state=state, code_verifier=initial_flow.code_verifier
            )

        self.assertTrue(initial_flow.code_verifier)
        self.assertEqual(callback_flow.code_verifier, initial_flow.code_verifier)

    def test_oauth_token_encryption_round_trip(self):
        from cryptography.fernet import Fernet

        key = Fernet.generate_key()
        token_json = '{"refresh_token":"test-token"}'
        encrypted = google_calendar._encrypt_token(token_json, key)
        self.assertNotIn("test-token", encrypted)
        self.assertEqual(google_calendar._decrypt_token(encrypted, key), token_json)


if __name__ == "__main__":
    unittest.main()
