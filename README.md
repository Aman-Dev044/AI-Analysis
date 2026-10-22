# DocuMind AI — Flask document summariser

Upload PDFs, Word files, text/CSV, scans and photos and get beautifully formatted
summaries from **your own Ollama server** (local or VPS). Every date, deadline,
amount and percentage is highlighted, critical items are underlined, and each
upload shows live, stage-by-stage progress while the summary is written.

## Features

- **Live processing pipeline** — Upload % → Extract (page by page) → Analyze → Summarize (streams word by word) → Ready.
- **9 summary styles** — Short, Detailed, Key points, Executive brief, Dates & deadlines timeline,
  Action items checklist, Explain simply, Study notes / quiz, and Custom prompt.
- **Length** (brief / standard / comprehensive), **14 languages** incl. Hindi & Hinglish, per-summary **model picker**.
- **Rich formatting** — Markdown with bold facts, `<u>` underlined warnings, tables, checklists, quotes;
  client-side highlight of dates (marker), money (green) and percentages; A-/A/A+ size, copy, `.md` download, print/PDF.
- **Summary history** — every generated version is kept per document.
- **Ask AI** — chat with a document (answers grounded only in its text, long docs use retrieval).
- **Insights (no AI needed)** — document type, words, reading time, all dates on a timeline with labels
  (expiry / deadline / review / issue / birth), expiry status with days remaining, amounts, emails, phones, links, sections.
- **Dashboard** — stats, expiry alerts, upcoming deadlines across documents, recent activity, and a
  **work-plan card** (today's focus, routine with the current slot highlighted, this week, month & quarter goals)
  for structured plans like `Period: … / YEAR n / QUARTER n / MONTH n` text files or date/activity CSV schedules.
- **Long documents** — automatic map-reduce chunking so large files fit the model context.
- **OCR** for images and scanned PDF pages: PaddleOCR, Tesseract, or an Ollama vision model (auto-fallback).
- Auth (login / signup, hashed passwords), per-user isolation, light/dark theme, mobile layout.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env        # fill MONGO_URI, SECRET_KEY, OLLAMA_URL, OLLAMA_MODEL
python seed.py              # creates indexes + the seeded admin login
python app.py               # http://127.0.0.1:5000  (uses waitress)
```

Seeded login (from `.env`): `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` — change the password from **Settings** after first login.

## Ollama on a VPS

- App on the **same VPS** as Ollama: keep `OLLAMA_URL=http://127.0.0.1:11434`.
- App **elsewhere**: set `OLLAMA_URL=http://<vps-ip>:11434` (start Ollama with `OLLAMA_HOST=0.0.0.0` and open the
  port only to your app's IP), or put Ollama behind an HTTPS reverse proxy and set `OLLAMA_API_KEY` — it is sent as
  `Authorization: Bearer <key>`.
- Pull the model on the VPS: `ollama pull qwen3:0.6b` (bigger models such as `qwen3:4b` / `llama3.1:8b` give much better summaries).
- Settings → *Ollama connection* shows reachability, version and installed models.

## Configuration (`.env`)

| Key | Default | Purpose |
|---|---|---|
| `MONGO_URI`, `DB_NAME` | – / `AI-Summary-Pro` | MongoDB connection and database |
| `SECRET_KEY` | – | Flask session signing key |
| `SESSION_COOKIE_SECURE` | `false` | set `true` behind HTTPS |
| `OLLAMA_URL`, `OLLAMA_MODEL` | `http://127.0.0.1:11434`, `qwen3:0.6b` | AI server and default model |
| `OLLAMA_API_KEY` | empty | optional Bearer token for a reverse proxy |
| `OLLAMA_NUM_CTX`, `OLLAMA_TIMEOUT_SECONDS` | `8192`, `600` | context window and request timeout |
| `OLLAMA_VISION_MODEL` | empty | e.g. `qwen2.5vl:3b` for OCR via Ollama |
| `OCR_ENGINE`, `TESSERACT_CMD` | `auto` | `auto`, `paddle`, `tesseract`, `ollama`, `off` |
| `CHUNK_CHARS`, `MAX_CHUNKS` | `12000`, `40` | long-document chunking |
| `MAX_UPLOAD_MB`, `WORKERS` | `25`, `2` | upload limit, parallel background jobs |
| `SEED_ADMIN_*` | | seeded login |

## MongoDB collections

Kept minimal (shared Atlas clusters cap collection count): `users` (incl. preferences and recent activity),
`documents`, `summaries`, `chat_messages`, `files` (original bytes in 4 MB chunks).

## Project layout

```
app.py                 Flask routes: pages, auth, documents, summaries, chat, dashboard
config.py / db.py      settings, MongoDB access, file storage, seeding
seed.py                one-off DB init + admin login
services/
  extractor.py         PDF / DOCX / TXT / CSV / image text extraction + OCR engines
  insights.py          deterministic dates, expiry, amounts, contacts, doc type
  plan.py              work-plan & schedule understanding for the dashboard
  summarizer.py        prompts, styles, map-reduce, document Q&A
  ollama_client.py     streaming client for local / VPS Ollama
  jobs.py              background pipeline with live progress
templates/             login.html, app.html
static/                css/app.css, js/app.js (vanilla SPA, no build step)
tests/                 unit tests for insights, plan and chunking
```

## Production

```bash
# Linux VPS
pip install gunicorn
gunicorn -w 1 --threads 16 -b 0.0.0.0:5000 "app:create_app()"
```

Use **one** worker process (threads are fine): background jobs run in-process. Put Nginx in front for HTTPS and set
`SESSION_COOKIE_SECURE=true`.

## Tests

```bash
python -m unittest discover -s tests
```
