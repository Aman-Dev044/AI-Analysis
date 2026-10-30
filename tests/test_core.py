import os
import sys
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest import mock  # noqa: E402

from services import (brief, extractive, extractor, fields, google_calendar, insights, ollama_client, plan,  # noqa: E402
                      rulebased, summarizer, tabular)
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
            "A licence.\n\n### Key points\n\n- a\n\nBody",
        )
        self.assertEqual(summarizer.clean_markdown("Intro text.\n| A | B |\n|---|---|\n| 1 | 2 |\nAfter.\n• one\n• two"),
                         "Intro text.\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nAfter.\n\n- one\n- two")
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


LICENCE = """INDIAN UNION DRIVING LICENCE
Issued by Himachal Pradesh
Licence No. DEMO-HP-000001
Name : AARAV SHARMA
S/D/W of: RAJESH SHARMA
Date of Birth 15/08/1998  Blood Group B+
Address
Vill. Shogi, P.O. Shogi, Tehsil Shimla (Rural) Distt. Shimla - 171219
Date of Issue: 20/10/2021
Validity (NT) 20/10/2026
"""


class FieldTests(unittest.TestCase):
    def test_licence_fields(self):
        got = {f["key"]: f["value"] for f in fields.extract_fields(LICENCE, date(2026, 10, 28))}
        self.assertEqual(got["name"], "AARAV SHARMA")
        self.assertEqual(got["relation"], "RAJESH SHARMA")
        self.assertEqual(got["licence_no"], "DEMO-HP-000001")
        self.assertEqual(got["issue_date"], "20/10/2021")
        self.assertEqual(got["expiry_date"], "20/10/2026")
        self.assertEqual(got["dob"], "15/08/1998")
        self.assertTrue(got["address"].startswith("Vill. Shogi"))

    def test_invoice_fields_and_prose_is_ignored(self):
        text = ("TAX INVOICE\nInvoice No: INV-2026-0042\nInvoice Date: 05/10/2026\nDue Date: 04/11/2026\n"
                "Grand Total: Rs. 18,500\nThe name of the project was decided in the meeting last week by everyone.")
        got = {f["key"]: f["value"] for f in fields.extract_fields(text, date(2026, 10, 28))}
        self.assertEqual(got["invoice_no"], "INV-2026-0042")
        self.assertEqual(got["due_date"], "04/11/2026")
        self.assertEqual(got["total"], "Rs. 18,500")
        self.assertNotIn("name", got)


class BriefTests(unittest.TestCase):
    def test_verify_drops_invented_facts(self):
        out = brief.verify(
            "Issued to **AARAV SHARMA** on **20/10/2021**. The holder is **Hara Sharma**. Renewed on 01/01/2025.",
            LICENCE, "")
        self.assertIn("AARAV SHARMA", out)
        self.assertNotIn("Hara", out)
        self.assertNotIn("2025", out)

    def test_smart_summary_without_model(self):
        info = insights.analyze(LICENCE)
        with mock.patch.object(ollama_client, "chat", side_effect=ollama_client.OllamaError("down")):
            md = summarizer.summarize(LICENCE, mode="smart", insights=info)
        self.assertIn("### Key details", md)
        self.assertIn("**DEMO-HP-000001**", md)
        self.assertIn("### Important dates", md)
        self.assertIn("belongs to **AARAV SHARMA**", md)

    def test_key_sentences(self):
        text = ("The contract must be signed by 15 March 2027. " * 1 + "Weather was pleasant and everyone enjoyed lunch together. "
                + "The total fee payable is Rs. 50,000 and late payment attracts a penalty of 2% per month. "
                + "Some people talked about random hobbies during the long afternoon break today.")
        picked = extractive.key_sentences(text, limit=2)
        self.assertEqual(len(picked), 2)
        self.assertTrue(any("penalty" in p for p in picked))


MEETING = """MINUTES OF THE PROJECT REVIEW MEETING
Date: 12/10/2026

2. DECISIONS
The committee decided to postpone the public launch to 15 December 2026.

3. RISKS
If the payment issue is not fixed by 20/11/2026, the client may impose a penalty of Rs. 50,000.

4. ACTION ITEMS
Anil must submit the revised test plan by 30/10/2026. The team has completed most of the backend work.
"""


REPORT = """QUARTERLY OPERATIONS REPORT – Q3 2026
Prepared by: Operations Department
Date: 05/10/2026

1. SALES PERFORMANCE
The company recorded revenue of Rs. 4.2 crore in Q3 2026, an increase of 18% over the previous quarter.
- North region sales grew 24% and crossed Rs. 1.6 crore for the first time.
- South region remained flat at Rs. 1.1 crore due to delayed distributor onboarding.
The mobile app now contributes 32% of all new orders, and the mobile app team is growing.

2. RISKS AND CONCERNS
The delay in South region onboarding is a risk to the Q4 target of Rs. 5 crore.
Two key vendors have not yet renewed their contracts, which expire on 31/12/2026.

3. NEXT STEPS
The procurement team must complete vendor renewals by 15 December 2026.
Regional heads should submit revised Q4 forecasts by 20/10/2026.

4. CONCLUSION
Overall, Q3 was a strong quarter, but South region onboarding and vendor renewals need urgent attention.
"""


class ExtractiveTests(unittest.TestCase):
    def test_list_items_are_separate_sentences(self):
        sents = extractive.sentences("Results:\n- North grew 24% this quarter overall.\n- South stayed flat at Rs. 1.1 crore.")
        self.assertIn("North grew 24% this quarter overall.", sents)
        self.assertIn("South stayed flat at Rs. 1.1 crore.", sents)

    def test_title_topics_and_context(self):
        self.assertEqual(extractive.doc_title(REPORT), "Quarterly Operations Report – Q3 2026")
        topics = extractive.keyphrases(REPORT, 5)
        self.assertIn("mobile app", topics)
        self.assertEqual(extractive.context("Operating costs rose by 11% because of higher fuel charges.", "11%"),
                         "Operating costs rose because of higher fuel charges")
        self.assertEqual(extractive.bold_owner("Anil must submit the plan."), "**Anil** must submit the plan.")
        self.assertEqual(extractive.bold_owner("It must be signed."), "It must be signed.")


SCHEDULE = "\n".join(
    ["Date | Day | Start | End | Task | Category | Priority"]
    + [f"2026-11-{d:02d} | Day | {h}:00 | {h}:30 | {t} | {c} | {p}"
       for d in range(1, 11) for h, t, c, p in ((9, "Plan the day", "Work", "High"), (18, "Evening walk", "Health", "Low"))])


class TabularTests(unittest.TestCase):
    def test_schedule_summary_and_answer(self):
        table = tabular.parse(SCHEDULE)
        self.assertIsNotNone(table)
        md = tabular.summarize(table, title="November plan", today=date(2026, 11, 3))
        self.assertIn("*Schedule · 20 rows · 7 columns*", md)
        self.assertIn("**20** entries from **1 Nov 2026** to **10 Nov 2026**", md)
        self.assertIn("Work **10** (50%)", md)
        self.assertIn("| Plan the day | **10** |", md)
        self.assertIn("### Coming up", md)
        self.assertIn("**10** matching row(s).", tabular.answer(table, "how many evening walk"))
        self.assertIsNone(tabular.parse("Hello world.\nThis is prose | with a pipe.\nAnother line."))

    def test_tables_skip_prose_summaries(self):
        md = rulebased.summarize(SCHEDULE, {}, mode="executive", title="Plan")
        self.assertTrue(md.startswith("## Plan\n\n*Schedule"))


class JobTests(unittest.TestCase):
    def test_only_orphaned_stale_work_is_reaped(self):
        from datetime import datetime, timedelta, timezone
        from services import jobs
        old = datetime.now(timezone.utc) - timedelta(minutes=10)
        with mock.patch.object(jobs, "_set_doc") as save:
            fresh = jobs.reap_document({"_id": 1, "status": "summarizing", "updated_at": datetime.now(timezone.utc)})
            self.assertEqual(fresh["status"], "summarizing")  # still moving: another worker may own it
            jobs._own(2)
            owned = jobs.reap_document({"_id": 2, "status": "extracting", "updated_at": old})
            self.assertEqual(owned["status"], "extracting")  # this server is running it
            jobs._release(2)
            orphan = jobs.reap_document({"_id": 3, "status": "extracting", "updated_at": old})
            self.assertEqual(orphan["status"], "failed")
            save.assert_called_once()


class RuleBasedTests(unittest.TestCase):
    def test_every_style_without_model(self):
        info = insights.analyze(MEETING)
        for mode in summarizer.MODES:
            md = rulebased.summarize(MEETING, info, mode=mode, instructions="penalty")
            self.assertTrue(md.startswith("## Minutes of the Project Review Meeting\n\n*Meeting notes*"), mode)
        exe = rulebased.summarize(MEETING, info, mode="executive")
        self.assertIn("- [ ] **Anil** must submit the revised test plan by **30/10/2026**.", exe)
        self.assertNotIn("RISKS If", exe)

    def test_report_layout(self):
        info = insights.analyze(REPORT)
        info["fields"] = fields.extract_fields(REPORT)
        md = rulebased.summarize(REPORT, info, mode="smart")
        self.assertTrue(md.startswith("## Quarterly Operations Report – Q3 2026"))
        self.assertNotIn("Status:", md)  # a vendor contract expiring is not the report's own validity
        self.assertIn("prepared by **Operations Department**", md)
        self.assertIn("| **Rs. 1.1 crore** | South region remained flat due to delayed distributor onboarding |", md)
        self.assertIn("Deadline: Regional heads should submit revised Q4 forecasts", md)
        self.assertNotIn("- -", md)
        detailed = rulebased.summarize(REPORT, info, mode="detailed")
        self.assertEqual(detailed.count("Conclusion"), 1)
        self.assertIn("### Risks and Concerns", detailed)
        actions = rulebased.summarize(REPORT, info, mode="actions")
        self.assertIn("- [ ] **Regional heads** should submit revised Q4 forecasts by **20/10/2026**.", actions)
        self.assertNotIn("remained flat", actions)  # "due to" is not a deadline

    def test_rules_answer(self):
        info = insights.analyze(MEETING)
        self.assertIn("Rs. 50,000", rulebased.answer(MEETING, "penalty kitna hai?", info))
        self.assertIn("15 December 2026", rulebased.answer(MEETING, "launch kab hai", info))
        lic = insights.analyze(LICENCE)
        self.assertIn("**20/10/2026**", rulebased.answer(LICENCE, "expiry date kya hai", lic))

    def test_model_failure_falls_back_to_rules(self):
        with mock.patch.object(ollama_client, "chat", side_effect=ollama_client.OllamaError("down")):
            md = summarizer.summarize(MEETING, mode="executive", insights=insights.analyze(MEETING))
        self.assertIn("### Decisions / Recommendations", md)


class GoogleCalendarTests(unittest.TestCase):
    def test_calendar_events_include_all_upcoming_unambiguous_dates(self):
        events = google_calendar.build_calendar_events(
            "doc-1",
            "Trip notes",
            [
                {"iso": "2027-01-05", "context": "Team meeting on 5 January 2027 at 9:30 PM."},
                {"iso": "2027-01-06", "context": "Travel to Jaipur on 6 January 2027."},
                {"iso": "2027-01-07", "context": "Family get-together on 7 January 2027."},
                {"iso": "2027-01-08", "context": "Payment deadline on 8 January 2027."},
                {
                    "iso": "2027-01-10",
                    "context": "Review weekly goals and outstanding tasks",
                    "event_context": (
                        "2027-01-10 | Sunday | 09:00 | 09:30 | "
                        "Review weekly goals and outstanding tasks | Planning | High | Not Started"
                    ),
                },
                {
                    "iso": "2027-01-11",
                    "context": "Prepare routine notes",
                    "event_context": (
                        "2027-01-11 | Monday | 09:00 | 09:30 | Prepare routine notes | Planning | Low"
                    ),
                },
                {"iso": "2026-12-01", "context": "Meeting on 1 December 2026."},
                {"iso": "2027-01-09", "context": "Meeting on 9 January 2027.", "ambiguous": True},
            ],
            today=date(2027, 1, 1),
        )

        self.assertEqual(len(events), 6)
        self.assertEqual(events[0]["start_local"], "2027-01-05T21:30")
        self.assertNotIn("start", events[0])
        self.assertEqual(events[1]["start"], {"date": "2027-01-06"})
        self.assertEqual(events[1]["end"], {"date": "2027-01-07"})
        self.assertIn("family", events[2]["summary"].lower())
        self.assertIn("deadline", events[3]["summary"].lower())
        self.assertEqual(events[4]["summary"], "High priority - Review weekly goals and outstanding tasks")
        self.assertIn("routine notes", events[5]["summary"].lower())

    def test_calendar_event_created_for_validity_date_without_event_keyword(self):
        events = google_calendar.build_calendar_events(
            "doc-2",
            "Membership document",
            [{
                "iso": "2027-03-15",
                "label": "expiry",
                "context": "Membership validity until 15 March 2027",
                "event_context": "Membership validity until 15 March 2027",
            }],
            today=date(2027, 1, 1),
        )

        self.assertEqual(len(events), 1)
        self.assertIn("validity / expiry", events[0]["summary"].lower())
        self.assertEqual(events[0]["start"], {"date": "2027-03-15"})

    def test_calendar_date_extraction_can_keep_all_same_date_rows(self):
        source = "\n".join([
            "Team meeting on 15 March 2027 at 9:00 AM.",
            "Flight departure on 15 March 2027 at 2:30 PM.",
        ])

        dates = insights.extract_dates(
            source, today=date(2027, 1, 1), limit=None, deduplicate=False,
        )
        events = google_calendar.build_calendar_events(
            "doc-3", "Itinerary", dates, today=date(2027, 1, 1),
        )

        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["start_local"], "2027-03-15T09:00")
        self.assertEqual(events[1]["start_local"], "2027-03-15T14:30")

    def test_calendar_sync_reports_each_event_status_through_callback(self):
        events = []
        with mock.patch.object(google_calendar, "_calendar_access_token", return_value="token"), \
                mock.patch.object(google_calendar.requests, "post") as post:
            post.return_value.status_code = 200
            post.return_value.ok = True
            result = google_calendar.sync_document_events(
                {"google_calendar": {"token_encrypted": "encrypted"}},
                "doc-4",
                "Membership",
                [{
                    "iso": "2027-03-15",
                    "label": "expiry",
                    "context": "Membership expires on 15 March 2027",
                }],
                today=date(2027, 1, 1),
                on_event_update=events.append,
            )

        self.assertEqual(result["status"], "created")
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["status"], "created")
        self.assertEqual(events[0]["id"], result["events"][0]["id"])

    def test_calendar_event_context_preserves_full_schedule_row(self):
        source = (
            "2027-01-10 | Sunday | 09:00 | 09:30 | Review weekly goals and outstanding tasks"
            " | Planning | High | Not Started"
        )
        info = insights.extract_dates(source, today=date(2027, 1, 1))

        self.assertEqual(len(info), 1)
        self.assertIn("| High | Not Started", info[0]["event_context"])

    def test_calendar_schedule_scans_each_same_day_row_and_uses_time_range(self):
        source = "\n".join([
            "Date | Time | Scheduled Activity | Category | Priority",
            "2026-10-30 | 06:30–07:00 | Wake up and set priorities | Personal | Suggested plan",
            "2026-10-30 | 10:30–11:15 | Weekly kickoff / team planning meeting | Meeting | Medium",
        ])
        table = tabular.parse(source)
        events = google_calendar.build_calendar_events(
            "doc-1", "Monthly schedule", [], today=date(2026, 10, 30), schedule_table=table,
        )

        self.assertEqual(len(events), 2)
        meeting = next(event for event in events if "Weekly kickoff" in event["summary"])
        self.assertEqual(meeting["summary"], "Meeting - Weekly kickoff / team planning meeting")
        self.assertEqual(meeting["start_local"], "2026-10-30T10:30")
        self.assertEqual(meeting["end_local"], "2026-10-30T11:15")
        self.assertTrue(any("Wake up and set priorities" in event["summary"] for event in events))

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
