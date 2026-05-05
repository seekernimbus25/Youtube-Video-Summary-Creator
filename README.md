# YouTube Video Summariser

Portfolio summary: this project turns long YouTube videos into structured notes and visual mind maps. The full workflow is meant to be run locally with your own API key.

## Portfolio Demo Note

The public website version of this project is a portfolio demo, not the full product experience.

- The hosted site only shows curated demo video summarizations.
- Real YouTube URL summarization is disabled on the public deployment because it consumes API credits.
- If you want to test the actual workflow with your own links, download the repository and run it on `localhost` with your own API key.

An AI-powered tool that generates deep, structured summaries of YouTube videos using Claude. Paste a URL and get a full breakdown: key sections, insights, concepts, comparisons, and a visual mind map without watching the full video.

## Features

- Structured summary: video overview, key sections with timestamps, key insights, important concepts explained, practical recommendations, and conclusion
- Comparison table: auto-generated when the video compares multiple tools, methods, or options
- Interactive mind map: visual D3.js graph of the video's ideas and structure
- Export: copy or download the full summary as a Markdown file
- Streaming UI: results stream in progressively via SSE so you see progress in real time
- Agentic RAG chat: transcript-grounded AI chat with indexing, retrieval, and timestamp chips

## How It Works

### Summarization Pipeline

Long videos are handled through a map-reduce pipeline. The transcript is split into sequential chunks, each is summarized independently, and the chunk summaries are merged into one coherent output.

```text
Transcript
  -> Type detection (tutorial / lecture / opinion / general)
  -> Semantic chunking
  -> Type-aware map pass
  -> Reduce pass
```

The map-reduce path activates automatically for long transcripts. Shorter videos go through a single-pass path.

## Tech Stack

- Backend: FastAPI, Anthropic SDK, OpenAI/OpenRouter client support, yt-dlp, youtube-transcript-api, Qdrant, Voyage AI, Upstash Redis
- Backend runtime: Python 3.12 virtualenv recommended in `backend\.venv312`
- Frontend: Vanilla HTML/CSS/JS, React 18 CDN, D3.js

## Prerequisites

- Python 3.12 for the backend workflow
- An [Anthropic API key](https://console.anthropic.com/) or another supported provider key

## Setup

1. Clone the repo

```bash
git clone https://github.com/seekernimbus25/youtube-video-summary-creator.git
cd youtube-video-summary-creator
```

2. Create a Python 3.12 backend environment

```powershell
cd backend
py -3.12 -m venv .venv312
.venv312\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

Or use the bundled bootstrap:

```powershell
cd backend
.\setup-py312.ps1
```

Notes:

- The backend RAG dependencies are intended to run under Python 3.12.
- Running them under Python 3.14 on Windows currently breaks dependency installation for the sparse-search stack.
- The bootstrap script also forces a backend-local temp directory, which avoids `ensurepip` permission failures on locked-down Windows temp folders.

3. Add your API key

Create a `.env` file inside `backend/`:

```env
ANTHROPIC_API_KEY=your_api_key_here
SUMMARIZER_API_KEY=optional_shared_api_key
ALLOWED_ORIGINS=http://localhost:8000
RATE_LIMIT_MAX_REQUESTS=5
RATE_LIMIT_WINDOW_SECONDS=900
VOYAGE_API_KEY=your_voyage_api_key_here
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key_here
UPSTASH_REDIS_URL=https://your-instance.upstash.io
UPSTASH_REDIS_TOKEN=your_upstash_token_here
```

If YouTube starts returning bot checks, add one of these too:

```env
YTDLP_COOKIES_FROM_BROWSER=chrome
```

or:

```env
YTDLP_AUTO_BROWSER_COOKIES=true
```

or:

```env
YTDLP_COOKIES_FILE=C:\path\to\cookies.txt
```

4. Run the server

```powershell
cd backend
.\run-dev-py312.ps1
```

Or, from an activated `backend\.venv312` shell:

```powershell
python -m uvicorn main:app --reload --port 8000
```

5. Open the app

Go to [http://localhost:8000](http://localhost:8000) in your browser.

## Usage

1. Paste any YouTube URL into the input field
2. Click the summarize action
3. Wait while the transcript is fetched and the backend generates the analysis
4. Open the AI Chat tab after summarization to trigger indexing and ask transcript-grounded questions
5. Use the export actions to copy or download the summary

## Notes

- The hosted portfolio UI is intentionally demo-only and will not summarize arbitrary public URLs.
- To test real end-to-end summarization, run the app locally with your own API credits.
- The video must have captions or subtitles available on YouTube.
- The default Anthropic model is `claude-haiku-4-5-20251001`. You can override this with `CLAUDE_MODEL`.
- `yt-dlp` stays anonymous by default. Browser cookies are only used if you opt into them with the relevant env vars.
- Production deployments should set `ALLOWED_ORIGINS` explicitly and use `SUMMARIZER_API_KEY` if the summarize API is not intended to be public.

## Project Structure

```text
yt-video-summariser/
|-- backend/
|   |-- .python-version
|   |-- setup-py312.ps1
|   |-- run-dev-py312.ps1
|   |-- main.py
|   |-- models.py
|   |-- requirements.txt
|   |-- requirements-dev.txt
|   |-- services/
|   `-- tests/
`-- frontend/
    |-- index.html
    |-- app.jsx
    |-- panels.jsx
    `-- chat.jsx
```
