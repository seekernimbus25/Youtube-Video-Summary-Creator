# YouTube Video Summariser

YouTube Video Summariser is a FastAPI + React app that turns long YouTube videos into structured learning material. Paste a video URL and the app can generate:

- a streamed summary
- key sections with timestamps
- a deeper written analysis
- an interactive mind map
- a readable transcript view
- transcript-grounded AI chat
- flashcards
- multiple-choice quiz questions

This repository contains both the backend and the frontend for the full local experience.

## What This Project Does

The app is designed for people who want to understand a long video without manually rewatching the entire thing.

For a real video, the workflow looks like this:

1. The backend fetches video metadata.
2. The backend fetches the transcript.
3. Summary generation starts.
4. Transcript indexing starts in parallel.
5. The frontend streams the summary into the UI.
6. `AI Chat`, `Flashcards`, and `Quiz Me` use the indexed transcript when it is ready.

That means the summary can appear first while the retrieval-backed study tools continue preparing in the background.

## Main Features

### Summary Workspace

The main results area includes:

- `Insights`: a fast high-level summary of the video
- `Key Sections`: the chronological structure of the video with timestamps
- `Deep Dive`: longer-form explanation, concepts, comparisons, and recommendations
- `Mind Map`: a visual map of the video’s ideas
- `Transcript`: a browsable transcript view

### AI Study Features

- `AI Chat`: ask questions against the transcript
- `Flashcards`: generate transcript-backed study cards
- `Quiz Me`: generate transcript-backed multiple-choice questions

These features are retrieval-backed for real videos, so they do not just answer from generic model memory. They answer from the indexed transcript.

### Demo Mode

The public portfolio deployment is intentionally limited.

- The hosted version only supports a curated demo video.
- Demo `AI Chat` returns a fixed portfolio message.
- Demo `Flashcards` and `Quiz Me` are hardcoded.
- Real YouTube summarization and real transcript-backed study features are meant to be run locally with your own credentials.

If you are visiting this repository for the first time and want the full product behavior, run it locally.

## Tech Stack

### Backend

- FastAPI
- Pydantic
- `youtube-transcript-api`
- `yt-dlp`
- Anthropic SDK or OpenRouter-compatible models
- Qdrant for transcript retrieval
- Voyage AI for dense embeddings
- FastEmbed
- Upstash Redis for job state and transcript cache

### Frontend

- React 18 via CDN
- vanilla HTML/CSS/JS
- D3.js for the mind map

## How The System Works

### 1. Summarization

The app fetches the transcript and builds a structured summary. For longer transcripts it uses a chunked map-reduce style pipeline so the result stays reliable on large videos.

```text
Transcript
  -> Video type detection
  -> Transcript shaping / trimming
  -> Chunked map pass for long inputs
  -> Reduce pass
  -> Mind map generation
```

### 2. Transcript Indexing

At the same time, the backend prepares the retrieval layer for transcript-grounded features.

```text
Transcript
  -> Chunk transcript with timestamps
  -> Generate embeddings
  -> Store chunks in Qdrant
  -> Write manifest
  -> Reuse index for chat / flashcards / quiz
```

### 3. Frontend Behavior

- Summary results stream into the UI over SSE.
- `AI Chat` can continue streaming across tab switches for the same video.
- `Flashcards` and `Quiz Me` can keep loading in the background after you first open them.
- If you switch to a different video, stale in-flight chat/study requests are aborted.

## Requirements

For local development:

- Python 3.12
- Windows PowerShell is the intended setup path in this repository

For real summarization:

- one model provider key:
  - `OPENROUTER_API_KEY`, or
  - `ANTHROPIC_API_KEY`

For real transcript-backed `AI Chat`, `Flashcards`, and `Quiz Me`:

- `VOYAGE_API_KEY`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `UPSTASH_REDIS_URL`
- `UPSTASH_REDIS_TOKEN`

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/seekernimbus25/Youtube-Video-Summary-Creator.git
cd Youtube-Video-Summary-Creator
```

### 2. Create the backend virtual environment

Recommended:

```powershell
cd backend
py -3.12 -m venv .venv312
.venv312\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

You can also use the included helper:

```powershell
cd backend
.\setup-py312.ps1
```

### 3. Create the env file

Copy the example file:

```powershell
Copy-Item .env.example .env
```

Then fill in the values you need.

The example file is here:

[backend/.env.example](/C:/Users/shata/Downloads/YT%20Video%20Summariser/backend/.env.example)

### 4. Run the app

```powershell
cd backend
.\run-dev-py312.ps1
```

Or, from an activated virtual environment:

```powershell
python -m uvicorn main:app --reload --port 8000
```

### 5. Open it in the browser

```text
http://localhost:8000
```

The FastAPI app serves the frontend too, so you only need to run the backend server.

## Minimal Env Setup

If you only want to experiment with the demo portfolio mode locally, you do not need the full retrieval stack.

If you want real summarization for your own videos, the minimum useful setup is:

```env
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=openai/gpt-4o-mini
```

If you also want real `AI Chat`, `Flashcards`, and `Quiz Me`, add:

```env
VOYAGE_API_KEY=your_key_here
QDRANT_URL=https://your-cluster.qdrant.io
QDRANT_API_KEY=your_key_here
UPSTASH_REDIS_URL=https://your-instance.upstash.io
UPSTASH_REDIS_TOKEN=your_token_here
```

## Environment Variables

### Model Provider

- `LLM_PROVIDER`
  - `openrouter` or `anthropic`
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`
- `OPENROUTER_FALLBACK_MODELS`
- `OPENROUTER_USE_LOW_COST_FALLBACK`
- `OPENROUTER_LOW_COST_MODEL`
- `ANTHROPIC_API_KEY`
- `CLAUDE_MODEL`

These control how summaries and study content are generated.

### Retrieval Stack

- `VOYAGE_API_KEY`
- `QDRANT_URL`
- `QDRANT_API_KEY`
- `QDRANT_TIMEOUT_SECONDS`
- `UPSTASH_REDIS_URL`
- `UPSTASH_REDIS_TOKEN`

These are required for real transcript-backed:

- `AI Chat`
- `Flashcards`
- `Quiz Me`

### API and Safety Settings

- `SUMMARIZER_API_KEY`
- `ALLOWED_ORIGINS`
- `RATE_LIMIT_MAX_REQUESTS`
- `RATE_LIMIT_WINDOW_SECONDS`

### Long Transcript Tuning

- `TRANSCRIPT_MAX_INPUT_CHARS`
- `TRANSCRIPT_HEAD_RATIO`
- `TRANSCRIPT_TAIL_RATIO`
- `TRANSCRIPT_MID_WINDOWS`
- `MAP_REDUCE_ENABLED`
- `MAP_REDUCE_MIN_TRANSCRIPT_CHARS`
- `MAP_CHUNK_TARGET_CHARS`
- `MAP_REDUCE_MAX_CHUNKS`
- `MAP_REDUCE_CONCURRENCY`

### Optional YouTube Auth Controls

- `YTDLP_COOKIES_FROM_BROWSER`
- `YTDLP_AUTO_BROWSER_COOKIES`
- `YTDLP_BROWSER_CANDIDATES`
- `YTDLP_COOKIES_FILE`

These are only needed if YouTube starts blocking anonymous access for your environment.

### Optional Proxy Control

- `USE_SYSTEM_PROXY`

## How To Use It

### Real Video Flow

1. Start the app locally.
2. Paste a YouTube URL into the input.
3. Click the distill action.
4. Wait for the summary to stream in.
5. Open `AI Chat`, `Flashcards`, or `Quiz Me` after the result appears.
6. Use timestamp chips to jump back into the transcript when available.

### Demo Flow

1. Open the hosted portfolio version or run the app locally.
2. Use the demo video.
3. Browse the summary surfaces and study tabs.

The demo exists to show the interface and product shape even when live infrastructure keys are not available.

## Project Structure

```text
Youtube-Video-Summary-Creator/
|-- api/
|   `-- index.py
|-- backend/
|   |-- .env.example
|   |-- .python-version
|   |-- main.py
|   |-- models.py
|   |-- requirements.txt
|   |-- requirements-dev.txt
|   |-- run-dev-py312.ps1
|   |-- setup-py312.ps1
|   |-- services/
|   |   |-- chat_service.py
|   |   |-- claude_service.py
|   |   |-- job_state_service.py
|   |   |-- rag_service.py
|   |   |-- study_service.py
|   |   |-- transcript_cache_service.py
|   |   |-- transcript_service.py
|   |   `-- video_service.py
|   |-- tests/
|   `-- utils/
|-- frontend/
|   |-- app.jsx
|   |-- chat.jsx
|   |-- data.jsx
|   |-- exports.jsx
|   |-- flashcards.jsx
|   |-- hardware.jsx
|   |-- index.html
|   |-- mindmap.jsx
|   |-- panels.jsx
|   |-- quiz.jsx
|   |-- styles.css
|   `-- tweaks.jsx
|-- requirements.txt
|-- vercel.json
`-- README.md
```

## Notes

- The hosted deployment is demo-only by design.
- Real summarization depends on the source video having an accessible transcript/captions path.
- Real transcript-backed study features depend on the retrieval stack being configured correctly.
- If Qdrant is slow in your environment, increase `QDRANT_TIMEOUT_SECONDS`.
- If YouTube starts returning bot checks, use one of the optional `yt-dlp` cookie env settings from `.env.example`.

## License

Add the license you want this repository to use.
