/* Reel Distiller — main app */

const { useState, useEffect, useRef, useMemo } = React;

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

  // Simulated SSE progression
  const run = (payload) => {
    clearInterval(timerRef.current);
    cancelRef.current = false;
    setState("running");
    setError(null);
    setResult(null);
    setStepIdx(0);
    setPct(0);
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
        setState("done");
        setResult(payload);
      }
    }, 140);
  };

  const onDistill = () => {
    if (!url.trim()) {
      setError("Empty URL. Paste a video link or press RUN DEMO.");
      setState("error");
      return;
    }
    // if URL contains "demo", we use demo data anyway — same as the spec
    run(DEMO_DATA);
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

  const exportSnippet = useMemo(() => {
    if (!result) return "";
    if (exportFmt === "md") return `# ${result.metadata.title}\n\n${result.pitch}`;
    if (exportFmt === "docx") return "[DOCX binary prepared — 214 KB]";
    return "[PDF rendered — 3 pages, 412 KB]";
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
            <a className="nav-chip" href="#" title="Source">
              ◎ SOURCE ↗
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

        {/* DEMO LINE */}
        <div className="demo-line">
          <Led on />
          <span>NO CREDITS? Run a zero-API distillation from a sample payload.</span>
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
            <div className="results-split">
              <InsightsPanel
              insights={result.insights}
              format={exportFmt}
              onFormat={setExportFmt} />
            
              <MindmapPanel data={result.mindmap} onPng={() => alert("Rendered mindmap.png (216 KB)")} />
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