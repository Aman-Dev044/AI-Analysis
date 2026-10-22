"""Prompt design, long-document map-reduce and document chat on top of Ollama."""

import re
from typing import Callable, Optional

from config import Config
from services import ollama_client
from services.insights import facts_for_prompt

ProgressFn = Callable[[int, str, Optional[str]], None]  # (percent, message, partial_markdown)

MODES = {
    "short": {
        "label": "Short summary",
        "icon": "zap",
        "desc": "TL;DR in a few lines",
        "prompt": "Write a SHORT summary: start with a one-line **TL;DR**, then one paragraph "
                  "(3-5 sentences), then a `### Key points` list of the 3-5 most important points.",
    },
    "detailed": {
        "label": "Detailed summary",
        "icon": "book",
        "desc": "Section-by-section breakdown",
        "prompt": "Write a DETAILED, well-structured summary. Start with `## Overview` (2-3 sentences). "
                  "Then add one `###` section per major topic/section of the document with paragraphs and "
                  "bullet points that keep every important fact, number, name and date. "
                  "End with `### Conclusion`.",
    },
    "bullets": {
        "label": "Key points",
        "icon": "list",
        "desc": "Scannable bullet list",
        "prompt": "Summarise as grouped bullet points. Use `###` group headings (e.g. Purpose, Key facts, "
                  "Numbers, Dates, People/Organisations, Next steps). Each bullet is one crisp line.",
    },
    "executive": {
        "label": "Executive brief",
        "icon": "briefcase",
        "desc": "Decisions, risks, actions",
        "prompt": "Write an EXECUTIVE BRIEF with these sections: `## Bottom line` (2 sentences), "
                  "`### Key findings`, `### Decisions / Recommendations`, `### Risks & concerns`, "
                  "`### Action items` (as a checklist `- [ ]` with owner and **due date** where stated), "
                  "`### Important dates` (as a Markdown table: Date | What).",
    },
    "dates": {
        "label": "Dates & deadlines",
        "icon": "calendar",
        "desc": "Timeline of every date",
        "prompt": "Produce a TIMELINE of every date, deadline, expiry, review and time period in the document. "
                  "Use a Markdown table with columns: **Date** | **Event / What happens** | **Type** "
                  "(Deadline, Expiry, Review, Meeting, Period, Other), sorted chronologically. "
                  "After the table add `### Critical deadlines` listing the ones that need action, and "
                  "<u>underline</u> any that are already past or very close.",
    },
    "actions": {
        "label": "Action items",
        "icon": "check",
        "desc": "Tasks & to-dos checklist",
        "prompt": "Extract every task, obligation, requirement and next step as a checklist (`- [ ] ...`). "
                  "Group under `###` headings by priority (High / Medium / Low) or by theme. Include **who**, "
                  "**what** and **by when** whenever the document states it. Finish with `### Notes`.",
    },
    "simple": {
        "label": "Explain simply",
        "icon": "smile",
        "desc": "Plain language, no jargon",
        "prompt": "Explain this document in very simple, friendly language as if to someone with no background. "
                  "Use short sentences, an `## In one line` heading, a `### What it means for you` section and a "
                  "`### Things to remember` list. Explain any jargon in brackets.",
    },
    "study": {
        "label": "Study notes / Q&A",
        "icon": "graduation",
        "desc": "Notes + quiz questions",
        "prompt": "Create STUDY NOTES: `## Core concepts` (bullets with bold terms and short definitions), "
                  "`### Important facts & figures`, then `### Quick quiz` with 5 questions and their answers "
                  "(question in bold, answer below).",
    },
    "custom": {
        "label": "Custom prompt",
        "icon": "sparkles",
        "desc": "Your own instructions",
        "prompt": "Follow the user's custom instructions below exactly.",
    },
}

LENGTHS = {
    "brief": "Keep it brief — roughly 80-150 words.",
    "standard": "Aim for a medium length — roughly 200-400 words.",
    "comprehensive": "Be comprehensive — up to 800-1200 words if the document has enough content.",
}

LANGUAGES = ["English", "Hindi", "Hinglish", "Spanish", "French", "German", "Arabic",
             "Bengali", "Marathi", "Tamil", "Telugu", "Gujarati", "Punjabi", "Urdu"]

FORMAT_RULES = """FORMATTING RULES (very important):
- Output GitHub-flavoured Markdown only. No preamble like "Here is the summary" and no closing remarks.
- Make EVERY date, deadline, time period, amount of money, percentage, quantity and key name **bold**.
- Use <u>underline</u> (HTML u tag) for critical warnings, legal obligations, penalties, and must-do items.
- Use > blockquotes for a single crucial takeaway or a direct important quote.
- Use tables when comparing items or listing dates.
- Use only facts from the document. If something is not stated, do not invent it."""

SYSTEM_PROMPT = ("You are DocuMind, an expert analyst who writes accurate, beautifully formatted document summaries. "
                 "You never invent facts and you preserve exact numbers, names and dates from the source.")


def language_rule(language: str) -> str:
    if language == "Hinglish":
        return "Write in Hinglish (Hindi written in Roman/Latin script mixed naturally with English; keep technical terms in English)."
    if language == "Hindi":
        return "Write in Hindi (Devanagari script). Keep dates, numbers and proper nouns exactly as in the source."
    return f"Write in {language}."


def split_chunks(text: str, size: int) -> list[str]:
    """Split on paragraph boundaries into pieces of roughly `size` characters."""
    paragraphs = re.split(r"\n\s*\n", text)
    chunks, current = [], ""
    for para in paragraphs:
        if len(para) > size:  # very long paragraph: hard-wrap on sentences
            for sentence in re.split(r"(?<=[.!?])\s+", para):
                if len(current) + len(sentence) > size and current:
                    chunks.append(current.strip())
                    current = ""
                current += sentence + " "
            continue
        if len(current) + len(para) + 2 > size and current:
            chunks.append(current.strip())
            current = ""
        current += para + "\n\n"
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _expected_chars(length: str) -> int:
    return {"brief": 900, "standard": 2200, "comprehensive": 5500}.get(length, 2200)


def _notes_for_chunk(chunk: str, index: int, total: int, model: Optional[str]) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"This is part {index} of {total} of a long document. Write dense factual notes of this part as "
            "bullet points. Keep ALL names, numbers, dates, deadlines, amounts, decisions and obligations exactly. "
            "No introduction.\n\n<part>\n" + chunk + "\n</part>")},
    ]
    return ollama_client.chat(messages, model=model, temperature=0.1)


def summarize(
    text: str,
    *,
    mode: str = "short",
    length: str = "standard",
    language: str = "English",
    instructions: str = "",
    insights: Optional[dict] = None,
    title: str = "",
    model: Optional[str] = None,
    progress: Optional[ProgressFn] = None,
) -> str:
    progress = progress or (lambda *_: None)
    mode_cfg = MODES.get(mode, MODES["short"])
    source = text.strip()
    if not source:
        raise ValueError("The document has no readable text to summarise.")

    # --- map phase for long documents
    chunks = split_chunks(source, Config.CHUNK_CHARS)
    if len(chunks) > Config.MAX_CHUNKS:
        chunks = chunks[:Config.MAX_CHUNKS]
    if len(chunks) > 1:
        notes = []
        for i, chunk in enumerate(chunks, start=1):
            progress(int((i - 1) / len(chunks) * 55), f"Reading part {i} of {len(chunks)}", None)
            notes.append(f"### Part {i}\n" + _notes_for_chunk(chunk, i, len(chunks), model))
        material = "\n\n".join(notes)
        # A second reduce pass if the notes are still too big for one call.
        if len(material) > Config.CHUNK_CHARS * 1.5:
            progress(57, "Condensing notes", None)
            parts = split_chunks(material, Config.CHUNK_CHARS)
            material = "\n\n".join(_notes_for_chunk(c, i, len(parts), model) for i, c in enumerate(parts, 1))
        material_label = "NOTES EXTRACTED FROM THE FULL DOCUMENT"
        base = 60
    else:
        material = source
        material_label = "DOCUMENT TEXT"
        base = 5

    facts = facts_for_prompt(insights or {})
    user_prompt = "\n\n".join(filter(None, [
        f"TASK: {mode_cfg['prompt']}",
        f"Custom instructions from the user: {instructions.strip()}" if instructions.strip() else "",
        LENGTHS.get(length, LENGTHS["standard"]),
        language_rule(language),
        FORMAT_RULES,
        f"Document title: {title}" if title else "",
        f"VERIFIED FACTS (detected in the document; use them and keep them bold):\n{facts}" if facts else "",
        f"<{material_label}>\n{material}\n</{material_label}>",
    ]))

    expected = _expected_chars(length)
    progress(base, "Writing summary", "")

    def on_token(partial: str):
        pct = base + min(38, int(len(partial) / expected * (98 - base)))
        progress(min(pct, 98), "Writing summary", partial)

    result = ollama_client.chat(
        [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
        model=model, temperature=0.25, on_token=on_token,
    )
    return clean_markdown(result)


def clean_markdown(text: str) -> str:
    text = re.sub(r"^```(?:markdown|md)?\s*\n", "", text.strip())
    text = re.sub(r"\n```\s*$", "", text)
    return text.strip()


# ------------------------------------------------------------------ chat
def _score(chunk: str, terms: set[str]) -> int:
    lower = chunk.lower()
    return sum(lower.count(t) for t in terms)


def answer_question(
    text: str,
    question: str,
    history: list[dict],
    *,
    language: str = "English",
    model: Optional[str] = None,
    on_token: Optional[Callable[[str], None]] = None,
) -> str:
    if len(text) <= Config.CHUNK_CHARS:
        context = text
    else:
        pieces = split_chunks(text, 1800)
        terms = {w for w in re.findall(r"\w{3,}", question.lower())}
        ranked = sorted(range(len(pieces)), key=lambda i: -_score(pieces[i], terms))
        keep = sorted(ranked[: max(1, Config.CHUNK_CHARS // 1800)])
        context = "\n…\n".join(pieces[i] for i in keep)

    messages = [{"role": "system", "content": (
        SYSTEM_PROMPT + " Answer questions ONLY from the document context. If the answer is not in it, say so "
        "clearly. Use Markdown, make dates, numbers and names **bold**, and quote the relevant line when helpful. "
        + language_rule(language)
    )}]
    messages.append({"role": "user", "content": f"<document_context>\n{context}\n</document_context>"})
    messages.append({"role": "assistant", "content": "I have read the document. Ask me anything about it."})
    for item in history[-6:]:
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": question})
    return clean_markdown(ollama_client.chat(messages, model=model, temperature=0.2, on_token=on_token))
