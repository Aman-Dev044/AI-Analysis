# DocuMind AI — Flask document summariser

Upload PDF, Word (.doc / .docx), TXT, Markdown, CSV, images (JPG, JPEG, PNG, SVG, BMP, TIFF, WEBP) and get beautifully formatted
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
- **OCR** for photos, scans and scanned PDF pages — RapidOCR (pip-installed, works out of the box), with
  PaddleOCR, Tesseract or an Ollama vision model as alternatives (auto-fallback).
- **Legacy .doc** read in pure Python (Word piece table); falls back to `antiword` / LibreOffice if present.
  **SVG** text is read directly, or the drawing is rendered and OCR'd when it has no text layer.
- Auth (login / signup, hashed passwords), per-user isolation, light/dark theme, mobile layout.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env        # fill MONGO_URI, SECRET_KEY, OLLAMA_URL, OLLAMA_MODEL
python seed.py              # creates indexes + the seeded admin login
python app.py               # http://127.0.0.1:5000  (uses waitress)
```

Seeded login: `SEED_ADMIN_EMAIL` plus `SEED_ADMIN_PASSWORD_HASH` in `.env` — only the scrypt hash is stored,
never the plain password. Create a hash with `python seed.py --hash`, or change the admin password directly in the
database with `python seed.py --set-password` (users can also change it from **Settings**).

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
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | empty | Google OAuth web application credentials |
| `GOOGLE_REDIRECT_URI` | `http://localhost:5000/google-calendar/callback` | Must exactly match the OAuth client redirect URI |
| `GOOGLE_TOKEN_ENCRYPTION_KEY` | empty | Fernet key used to encrypt saved Google refresh tokens |
| `OCR_ENGINE`, `TESSERACT_CMD` | `auto` | `auto` (rapid → paddle → tesseract → ollama), or one of `rapid`, `paddle`, `tesseract`, `ollama`, `off` |
| `CHUNK_CHARS`, `MAX_CHUNKS` | `12000`, `40` | long-document chunking |
| `MAX_UPLOAD_MB`, `WORKERS` | `25`, `2` | upload limit, parallel background jobs |
| `SEED_ADMIN_*` | | seeded login |

### Google Calendar connection

Enable the Google Calendar API, configure the OAuth consent screen, and create a **Web application** OAuth client.
Set its authorized redirect URI to the exact value of `GOOGLE_REDIRECT_URI`, then add the client ID and secret to
`.env` and replace the Flask `SECRET_KEY` placeholder with a strong random value. Generate a Fernet key with
`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and set it as
`GOOGLE_TOKEN_ENCRYPTION_KEY`. Keep this key stable so saved tokens remain decryptable. Restart the app after editing
`.env`. The Settings connection requests only the `calendar.events` scope; OAuth tokens are encrypted before being
stored on the user's MongoDB record. After connection, document processing can add upcoming meetings, travel,
family get-togethers and explicitly high-priority scheduled tasks with a date. Other date mentions and
low/medium-priority tasks are not added. Events with a stated time use the primary calendar's time zone; when
no time is present, the event is all-day. Reprocessing uses deterministic event IDs to avoid duplicates. Do not
commit `.env` or share the client secret or encryption key.

## MongoDB collections

Kept minimal (shared Atlas clusters cap collection count): `users` (incl. preferences and recent activity),
`documents`, `summaries`, `chat_messages`, `files` (original bytes in 4 MB chunks).

## Project layout

```
app.py                 Flask routes: pages, auth, documents, summaries, chat, dashboard
config.py / db.py      settings, MongoDB access, file storage, seeding
seed.py                one-off DB init + admin login
services/
  extractor.py         PDF / DOC / DOCX / TXT / CSV / SVG / image text extraction + OCR engines
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
