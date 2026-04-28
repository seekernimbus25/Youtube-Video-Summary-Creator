/* Reel Distiller — main app */

const { useState, useEffect, useRef, useMemo } = React;

function isPortfolioDemoMode() {
  if (typeof window === "undefined" || !window.location) return false;
  const host = (window.location.hostname || "").toLowerCase();
  if (!host) return false;
  return host !== "localhost" && host !== "127.0.0.1";
}

const absUrl = (u) => (typeof window !== "undefined" && window.absMediaUrl ? window.absMediaUrl(u) : (u || ""));

/** Deduplicate shot list by media URL (exact + time-window can match the same frame twice). */
function uniqueShotsByUrl(rawList, cap) {
  const out = [];
  const seen = new Set();
  for (const sh of rawList) {
    const u = absUrl(sh.url || sh.src);
    if (!u || seen.has(u)) continue;
    seen.add(u);
    out.push({ src: u, caption: sh.caption || "" });
    if (cap != null && out.length >= cap) break;
  }
  return out;
}

/** Map SSE/API payload to the React `result` shape. Avoids duplicate screenshots: same frame in both section_index and time-window, and gallery vs. key sections. */
function mapApiResultToView(rawData) {
  const s = rawData.summary;
  const allScreens = rawData.screenshots || [];
  const keySections = s.key_sections || [];
  const usedInSections = new Set();
  const sections = keySections.map((sec, i) => {
    const start = sec.timestamp_seconds || 0;
    const end = (i + 1 < keySections.length) ? (keySections[i+1].timestamp_seconds || start + 120) : Infinity;
    const exactShots = allScreens.filter((sh) => Number(sh.section_index) === i);
    const fallbackShots = allScreens.filter((sh) => sh.seconds >= start && sh.seconds < end);
    const merged = uniqueShotsByUrl([...exactShots, ...fallbackShots], 2);
    merged.forEach((m) => usedInSections.add(m.src));
    return {
      id: "sec-" + i,
      title: sec.title,
      time: sec.timestamp,
      desc: sec.description,
      steps: sec.steps || [],
      notable: sec.notable_detail,
      shots: merged
    };
  });
  const screenshots = uniqueShotsByUrl(
    allScreens.filter((sh) => {
      const u = absUrl(sh.url);
      return u && !usedInSections.has(u);
    }),
    null
  );
  return {
    metadata: {
      title: rawData.metadata.title,
      channel: rawData.metadata.channel,
      duration: rawData.metadata.duration_formatted,
      thumbnail: rawData.metadata.thumbnail_url ? absUrl(rawData.metadata.thumbnail_url) : ""
    },
    pitch: s.video_overview ? s.video_overview.elevator_pitch : "No pitch available",
    insights: s.key_insights || s.main_points || [],
    mindmap: rawData.mindmap,
    screenshots,
    sections,
    concepts: (s.important_concepts || []).map((c) => ({
      name: c.concept,
      desc: c.explanation,
      sig: c.why_it_matters
    })),
    comparison: (s.comparison_table && s.comparison_table.applicable) ? {
      headers: s.comparison_table.headers,
      rows: s.comparison_table.rows
    } : null,
    recommendations: s.practical_recommendations || [],
    conclusion: s.conclusion
  };
}

/** Local demo JSON → same shape as API-mapped `res` (guarantees .map() targets, mindmap, metadata). */
function normalizeDemoForView(d) {
  if (!d) return null;
  const m = d.metadata || {};
  const thumb = m.thumbnail_url || m.thumbnail;
  const sections = Array.isArray(d.sections) ? d.sections.map((sec) => {
    const shotRows = (sec.shots || []).map((sh) => ({
      url: sh.src || sh.url,
      caption: sh.caption || ""
    }));
    return { ...sec, shots: uniqueShotsByUrl(shotRows, null) };
  }) : [];
  const used = new Set();
  sections.forEach((sec) => (sec.shots || []).forEach((sh) => { if (sh.src) used.add(sh.src); }));
  const topScreens = Array.isArray(d.screenshots) ? d.screenshots : [];
  const screenshots = uniqueShotsByUrl(
    topScreens
      .map((sh) => ({ url: sh.url || sh.src, caption: sh.caption || "" }))
      .filter((sh) => {
        const u = absUrl(sh.url);
        return u && !used.has(u);
      }),
    null
  );
  return {
    metadata: {
      title: m.title != null ? String(m.title) : "",
      channel: m.channel != null ? String(m.channel) : "",
      duration: m.duration != null ? String(m.duration) : (m.duration_formatted != null ? String(m.duration_formatted) : ""),
      published: m.published,
      views: m.views,
      thumbnail: thumb ? absUrl(thumb) : ""
    },
    pitch: d.pitch != null ? String(d.pitch) : "",
    insights: Array.isArray(d.insights) ? d.insights : [],
    mindmap: d.mindmap && typeof d.mindmap === "object" ? d.mindmap : { name: "Summary", children: [] },
    sections,
    concepts: Array.isArray(d.concepts) ? d.concepts : [],
    comparison: d.comparison && typeof d.comparison === "object" ? d.comparison : null,
    recommendations: Array.isArray(d.recommendations) ? d.recommendations : [],
    conclusion: d.conclusion != null ? d.conclusion : null,
    screenshots
  };
}

function useTweaks() {
  const [tweaks, setTweaks] = useState(() => window.__TWEAKS__ || {
    faceplateTone: "ivory", ledColor: "amber", grainOn: true, autoDemo: false
  });
  useEffect(() => {
    document.body.setAttribute("data-tone", tweaks.faceplateTone);
    document.body.setAttribute("data-led", tweaks.ledColor);
  }, [tweaks.faceplateTone, tweaks.ledColor]);
  return [tweaks, setTweaks];
}

function App() {
  const [tweaks, setTweaks] = useTweaks();
  const demoOnlyMode = isPortfolioDemoMode();

  const [url, setUrl] = useState("https://www.videohost.example/watch?v=demo-modular-synth");
  const [screenshotsOn, setScreenshotsOn] = useState(true);
  const [depthKnob, setDepthKnob] = useState(58);

  // pipeline state: idle | running | done | error
  const [state, setState] = useState("idle");
  const [stepIdx, setStepIdx] = useState(0);
  const [pct, setPct] = useState(0);
  const [label, setLabel] = useState("Waiting for input…");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [exportFmt, setExportFmt] = useState("md");

  const timerRef = useRef(null);
  const cancelRef = useRef(false);

  const run = async (demoPayload = null) => {
    clearInterval(timerRef.current);
    cancelRef.current = false;
    setState("running");
    setError(null);
    setResult(null);
    setStepIdx(0);
    setPct(0);

    if (demoPayload) {
      const stepLabels = [
      "Validating URL signature…",
      "Fetching video metadata…",
      "Transcribing audio track…",
      "Distilling to structured summary…",
      "Rendering mindmap & exports…"];

      setLabel(stepLabels[0]);

      let p = 0;
      timerRef.current = setInterval(() => {
        if (cancelRef.current) return;
        p += 1 + Math.random() * 2.5;
        const pcap = Math.min(100, p);
        setPct(pcap);
        const si = Math.min(4, Math.floor(pcap / 20));
        setStepIdx(si);
        setLabel(stepLabels[si]);
        if (pcap >= 100) {
          clearInterval(timerRef.current);
          const next = normalizeDemoForView(demoPayload);
          const apply = () => {
            setState("done");
            setResult(next);
          };
          /* One commit: setInterval is outside React; avoid done+result splitting across renders (R17 / edge cases). */
          if (typeof ReactDOM.flushSync === "function") {
            ReactDOM.flushSync(apply);
          } else {
            apply();
          }
        }
      }, 140);
      return;
    }

    setLabel("Connecting to Knowledge Engine...");
    
    try {
        const headers = { 'Content-Type': 'application/json' };
        const provider = sessionStorage.getItem('buddy_provider');
        const apiKey = sessionStorage.getItem('buddy_api_key');
        const model = sessionStorage.getItem('buddy_model');
        
        if (apiKey) headers['X-Buddy-Api-Key'] = apiKey;
        if (provider) headers['X-Buddy-Provider'] = provider;
        if (model) headers['X-Buddy-Model'] = model;

        const response = await fetch('/api/summarize', {
            method: 'POST',
            headers: headers,
            body: JSON.stringify({ url, include_screenshots: screenshotsOn })
        });

        if (!response.ok) throw new Error("Synthesis service temporarily unavailable.");

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            if (cancelRef.current) {
                reader.cancel();
                break;
            }
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split('\n\n');
            buffer = parts.pop();
            for (const p of parts) {
                if (p.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(p.slice(6));
                        if (data.type === 'progress') {
                            setLabel(data.message);
                            const percent = Math.round((data.step / data.total_steps) * 100);
                            setPct(percent);
                            const si = Math.min(4, Math.floor(percent / 20));
                            setStepIdx(si);
                        } else if (data.type === 'result') {
                            setPct(100);
                            setStepIdx(4);
                            setLabel("Done!");
                            
                            const res = mapApiResultToView(data.data);
                            setResult(res);
                            setState("done");
                        } else if (data.type === 'error') {
                            throw new Error(data.message);
                        }
                    } catch (e) {
                        if (e.message !== "Unexpected end of JSON input" && !e.message.startsWith("Unexpected token")) {
                            throw e;
                        }
                    }
                }
            }
        }
    } catch (err) {
        if (!cancelRef.current) {
            setError(err.message);
            setState("error");
        }
    }
  };

  const onDistill = () => {
    if (!url.trim()) {
      setError("Empty URL. Paste a video link or press RUN DEMO.");
      setState("error");
      return;
    }
    if (demoOnlyMode && !url.toLowerCase().includes("demo")) {
      setError("This public portfolio build only runs the sample demo video. Download the project from GitHub and run it on localhost to summarize real YouTube URLs with your own API credits.");
      setState("error");
      return;
    }
    // if URL contains "demo", we use demo data anyway — same as the spec
    if (url.toLowerCase().includes("demo")) {
      run(DEMO_DATA);
    } else {
      run(null);
    }
  };
  const onDemo = () => {
    setUrl("https://www.videohost.example/watch?v=demo-modular-synth");
    run(DEMO_DATA);
  };

  useEffect(() => {
    if (tweaks.autoDemo) {
      const t = setTimeout(onDemo, 500);
      return () => clearTimeout(t);
    }
  }, []); // on mount

  const safeExportBase = () => {
    const t = result?.metadata?.title || "youtube_buddy_summary";
    return String(t).replace(/[^\w\-\s]+/g, "").replace(/\s+/g, "_").slice(0, 72) || "summary";
  };

  const handleExportDownload = (fmt) => {
    if (!result || !window.buildMarkdown) return;
    setExportFmt(fmt);
    const base = safeExportBase();
    if (fmt === "md") {
      const md = window.buildMarkdown(result);
      window.downloadBlob(`${base}.md`, new Blob([md], { type: "text/markdown;charset=utf-8" }));
    } else if (fmt === "docx") {
      window.downloadWord(result);
    } else if (fmt === "pdf") {
      window.openPrintablePdf(result);
    }
  };

  const handleMindmapPng = () => {
    const el = document.getElementById("mindmap-export-root");
    if (window.downloadMindmapPng) window.downloadMindmapPng(el);
  };

  const exportSnippet = useMemo(() => {
    if (!result) return "";
    if (exportFmt === "md") {
      const t = result.metadata?.title ?? "";
      const p = result.pitch ?? "";
      return `# ${t}\n\n${p}`;
    }
    if (exportFmt === "docx") return "Word .doc (HTML) — use Download";
    return "PDF — print dialog → Save as PDF";
  }, [exportFmt, result]);

  return (
    <>
      <div
        className="faceplate"
        data-grain={tweaks.grainOn ? "on" : "off"}
        data-screen-label="01 Faceplate">
        
        <Screws />

        {/* NAV */}
        <div className="nav">
          <div className="brand">
            <span className="logo-mark">yb</span>
            <div>
              <div>
                <span className="brand-title">YOUTUBE
bUDDY
</span>
                <span className="brand-version">v1.2</span>
              </div>
              <div className="brand-tagline">Your AI Video Synthesis Companion</div>
            </div>
          </div>

          <div className="nav-right">
            <a className="nav-chip" href="#" title="Author">
              <span className="led on" style={{ width: 6, height: 6 }} /> BUILT BY SHATAKSHI
            </a>
            <a
              className="nav-chip nav-github"
              href="https://github.com/seekernimbus25/Youtube-Video-Summary-Creator"
              target="_blank"
              rel="noopener noreferrer"
              title="GitHub repository"
            >
              <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="currentColor">
                <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.35-.135-.345-.72-1.35-1.23-1.62-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
              </svg>
              GitHub
            </a>
            <Knob value={depthKnob} onChange={setDepthKnob} label="DEPTH" />
            <div className="grill" title="Output grill" />
          </div>
        </div>

        {/* HERO — row 1: URL + SHOTS; row 2: centered DISTILL */}
        <div className="hero">
          <div className="hero-row-1">
            <SearchField value={url} onChange={setUrl}
              onSubmit={onDistill}
              placeholder="Paste any video URL…" />
            <Switch
              on={screenshotsOn}
              onChange={setScreenshotsOn}
              label="SHOTS"
              sublabel="frame capture" />
          </div>
          <div className="hero-row-2">
            <DistillButton
              onClick={onDistill}
              busy={state === "running"}
              disabled={state === "running"} />
          </div>
        </div>

        <div className="portfolio-note" role="note" aria-live="polite">
          <div className="portfolio-note-title">PORTFOLIO DEMO ONLY</div>
          <p>
            This hosted version is a dummy showcase and only plays curated demo summarizations.
            Real YouTube URL processing is disabled here because it consumes API credits.
            To test the full product with your own videos, download the project from GitHub and run it locally.
          </p>
        </div>

        {/* DEMO LINE */}
        <div className="demo-line">
          <Led on />
          <span>Use the sample payload to preview extraction, screenshots, mindmaps, and summary formatting.</span>
          <button className="demo-btn" onClick={onDemo}>▸ RUN DEMO</button>
        </div>

        {/* PROGRESS / ERROR */}
        {state === "running" &&
        <ProgressCard stepIdx={stepIdx} pct={pct} label={label} />
        }
        {state === "error" &&
        <ErrorCard message={error} onDismiss={() => {setState("idle");setError(null);}} />
        }

        {/* RESULTS */}
        {state === "done" && result &&
        <div className="results">
            <VideoProfile meta={result.metadata} pitch={result.pitch} />
            <ScreenshotsGallery shots={result.screenshots} />
            <div className="results-split">
              <InsightsPanel
              insights={result.insights}
              format={exportFmt}
              onFormat={setExportFmt}
              onDownload={handleExportDownload} />
            
              <MindmapPanel data={result.mindmap} onPng={handleMindmapPng} />
            </div>
            <div className="mono" style={{ fontSize: 10, color: "var(--muted)", letterSpacing: ".1em", padding: "0 4px" }}>
              ▸ EXPORT PREVIEW ({exportFmt.toUpperCase()}): {exportSnippet}
            </div>
            <DetailSections data={result} />
          </div>
        }

        {/* BOTTOM GRILL + FOOTER */}
        <div className="grill-bottom">
          <span className="serial mono">SER-RD-1127-A · 2026</span>
          <div className="grill-strip" />
          <span className="serial mono">CH-01 ∿ CH-02</span>
        </div>
        <div className="footer-links">
          <a href="#">Docs</a>
          <a href="#">API</a>
          <a href="#">Privacy</a>
          <a href="#">Changelog</a>
          <a href="#">Status · Operational</a>
        </div>
      </div>

      <TweaksPanel tweaks={tweaks} onChange={setTweaks} />
    </>);

}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
