# YouTube Video Summariser

An AI-powered tool that generates deep, structured summaries of YouTube videos using Claude. Paste a URL and get a full breakdown — key sections, insights, concepts, comparisons, a visual mind map, and optional video frame snapshots — without watching the video.

## Features

- **Structured summary** — video overview, key sections with timestamps, key insights, important concepts explained, practical recommendations, and conclusion
- **Comparison table** — auto-generated when the video compares multiple tools, methods, or options
- **Interactive mind map** — visual D3.js graph of the video's ideas and structure
- **Inline screenshots** — extracts frames from the video at key moments and places them inside the relevant section (requires ffmpeg)
- **Export** — copy or download the full summary as a Markdown file
- **Streaming UI** — results stream in progressively via SSE so you see progress in real time

## Tech Stack

- **Backend** — Python, FastAPI, Anthropic SDK (Claude), yt-dlp, youtube-transcript-api, ffmpeg
- **Frontend** — Vanilla HTML/CSS/JS, D3.js (mind map)

## Prerequisites

- Python 3.10+
- An [Anthropic API key](https://console.anthropic.com/)
- ffmpeg installed and on your PATH (only required for screenshots)
  - Windows: [gyan.dev builds](https://www.gyan.dev/ffmpeg/builds/) or `winget install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`

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

4. **Run the server**
   ```bash
   uvicorn main:app --reload
   ```

5. **Open the app**

   Go to [http://localhost:8000](http://localhost:8000) in your browser.

## Usage

1. Paste any YouTube URL into the input field
2. Check or uncheck **Include Inline Screenshots** (requires ffmpeg)
3. Click **Summarize Video**
4. Wait ~30–60 seconds while the transcript is fetched and Claude generates the analysis
5. Use **Copy as Markdown** or **Download .md** to export the summary

## Notes

- The video must have captions/subtitles available on YouTube (auto-generated captions work)
- Screenshot extraction downloads a low-resolution copy of the video temporarily — it is deleted automatically after frames are extracted
- Claude model used defaults to `claude-haiku-4-5-20251001`. You can override this by setting `CLAUDE_MODEL` in your `.env` file

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
│   │   ├── screenshot_service.py # yt-dlp download + ffmpeg frame extraction
│   │   ├── transcript_service.py # YouTube transcript fetching
│   │   └── video_service.py     # Video metadata via yt-dlp
│   └── static/
│       └── screenshots/         # Extracted frames (auto-cleaned after 24h)
└── frontend/
    └── index.html               # Single-page UI
```
