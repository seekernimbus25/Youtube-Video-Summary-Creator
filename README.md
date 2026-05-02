# YouTube Video Summariser

Portfolio summary: this project turns long YouTube videos into structured notes and visual mind maps. The full workflow is meant to be run locally with your own API key.

## Portfolio Demo Note

The public website version of this project is a portfolio demo, not the full product experience.

- The hosted site only shows curated demo video summarizations.
- Real YouTube URL summarization is disabled on the public deployment because it consumes API credits.
- If you want to test the actual workflow with your own links, download the repository and run it on `localhost` with your own API key.

An AI-powered tool that generates deep, structured summaries of YouTube videos using Claude. Paste a URL and get a full breakdown — key sections, insights, concepts, comparisons, and a visual mind map — without watching the video.

## Features

- **Structured summary** — video overview, key sections with timestamps, key insights, important concepts explained, practical recommendations, and conclusion
- **Comparison table** — auto-generated when the video compares multiple tools, methods, or options
- **Interactive mind map** — visual D3.js graph of the video's ideas and structure
- **Export** — copy or download the full summary as a Markdown file
- **Streaming UI** — results stream in progressively via SSE so you see progress in real time

## How It Works

### Summarization Pipeline

Long videos are handled through a **map-reduce pipeline** — the transcript is split into sequential chunks, each summarised independently, then synthesised into a single coherent output. This ensures the full video is covered regardless of length.

```
Transcript
  → Type detection (tutorial / lecture / opinion / general)
  → Semantic chunking (split at sentence boundaries)
  → Type-aware map — each chunk summarised with a prompt tuned to the video type
  → Reduce — chunk summaries merged into the final structured output
```

The map-reduce path activates automatically for transcripts over ~46,000 characters. Shorter videos go through a single-pass path.

## Tech Stack

- **Backend** — Python, FastAPI, Anthropic SDK (Claude), yt-dlp, youtube-transcript-api
- **Frontend** — Vanilla HTML/CSS/JS, D3.js (mind map)

## Prerequisites

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/)

## Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/seekernimbus25/youtube-video-summary-creator.git
   cd youtube-video-summary-creator
   ```

2. **Install Python dependencies**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

   For local testing and CI:
   ```bash
   pip install -r requirements-dev.txt
   ```

3. **Add your API key**

   Create a `.env` file inside the `backend/` folder:
   ```
   ANTHROPIC_API_KEY=your_api_key_here
   SUMMARIZER_API_KEY=optional_shared_api_key
   ALLOWED_ORIGINS=https://yourdomain.com
   RATE_LIMIT_MAX_REQUESTS=5
   RATE_LIMIT_WINDOW_SECONDS=900
   ```

   If YouTube starts returning "Sign in to confirm you're not a bot", add one of these too:
   ```
   YTDLP_COOKIES_FROM_BROWSER=chrome
   ```
   Or, if you want the backend to try common local browsers automatically:
   ```
   YTDLP_AUTO_BROWSER_COOKIES=true
   ```
   Or point directly to an exported cookie file:
   ```
   YTDLP_COOKIES_FILE=C:\path\to\cookies.txt
   ```

4. **Run the server**
   ```bash
   uvicorn main:app --reload
   ```

5. **Open the app**

   Go to [http://localhost:8000](http://localhost:8000) in your browser.

## Usage

1. Paste any YouTube URL into the input field
2. Click **Summarize Video**
3. Wait ~30–60 seconds while the transcript is fetched and Claude generates the analysis
4. Use **Copy as Markdown** or **Download .md** to export the summary

## Notes

- The hosted portfolio UI is intentionally demo-only and will not summarize arbitrary public URLs
- To test real end-to-end summarization, run the app locally with your own API credits

- The video must have captions/subtitles available on YouTube (auto-generated captions work)
- Claude model used defaults to `claude-haiku-4-5-20251001`. You can override this by setting `CLAUDE_MODEL` in your `.env` file
- `yt-dlp` now stays anonymous by default. Browser cookies are only used if you set `YTDLP_COOKIES_FROM_BROWSER`, `YTDLP_COOKIES_FILE`, or explicitly enable `YTDLP_AUTO_BROWSER_COOKIES=true`

- Production deployments should set `ALLOWED_ORIGINS` explicitly and use `SUMMARIZER_API_KEY` if the summarize API is not intended to be public

## Project Structure

```
yt-video-summariser/
├── backend/
│   ├── main.py                  # FastAPI app, SSE endpoint
│   ├── models.py                # Pydantic models
│   ├── requirements.txt
│   ├── services/
│   │   ├── claude_service.py    # Prompt + Claude API call
│   │   ├── transcript_service.py # YouTube transcript fetching
│   │   └── video_service.py     # Video metadata via yt-dlp
│   └── static/
└── frontend/
    └── index.html               # Single-page UI
```
