/* Result panels: video profile, tabbed summary workspace */

const VideoProfile = ({ meta, pitch }) => {
  const m = meta || {};
  const thumb = m.thumbnail || m.thumbnail_url;
  return (
    <div className="panel" data-screen-label="Video">
      <div className="video-profile">
        <div className="thumb">
          {thumb ? (
            <img className="thumb-img" src={thumb} alt="" loading="lazy" />
          ) : null}
          <span className="thumb-label">16:9 · SOURCE</span>
          <span className="thumb-play">▶</span>
          <span className="thumb-chip mono">{m.duration}</span>
        </div>
        <div className="video-profile-copy">
          <h2 className="video-title">{m.title}</h2>
          <div className="video-meta">
            <span>◆ {m.channel}</span>
            <span>◆ {m.published}</span>
            <span>◆ {m.views} views</span>
            <span>◆ EN · CC</span>
          </div>
          <p className="video-pitch">{pitch}</p>
        </div>
      </div>
    </div>
  );
};

const ExportMenu = ({ format, onFormat, onDownload, buttonLabel }) => {
  const [menuOpen, setMenuOpen] = React.useState(false);

  React.useEffect(() => {
    const close = () => setMenuOpen(false);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, []);

  const handleSelect = (nextFormat) => {
    onFormat && onFormat(nextFormat);
    onDownload && onDownload(nextFormat);
    setMenuOpen(false);
  };

  return (
    <div className="export-menu export-menu-dropdown" role="group" aria-label="Export summary">
      <button
        type="button"
        className="export-btn export-menu-trigger"
        aria-expanded={menuOpen ? "true" : "false"}
        onClick={(e) => {
          e.stopPropagation();
          setMenuOpen((v) => !v);
        }}
      >
        {buttonLabel || "Download summary"}
      </button>
      {menuOpen && (
        <div className="export-menu-popover" onClick={(e) => e.stopPropagation()}>
          {[
            { key: "md", label: "Markdown", hint: "Plain text summary" },
            { key: "docx", label: "Document", hint: "Word-compatible file" },
            { key: "pdf", label: "PDF", hint: "Print-friendly export" },
          ].map((item) => (
            <button
              key={item.key}
              type="button"
              className={`export-menu-item${format === item.key ? " active" : ""}`}
              onClick={() => handleSelect(item.key)}
            >
              <span className="export-menu-item-label">{item.label}</span>
              <span className="export-menu-item-hint">{item.hint}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

const KeyInsightsPanel = ({ insights, format, onFormat, onDownload }) => (
  <div className="panel" data-screen-label="Insights">
    <div className="panel-head">
      <div className="panel-title">◉ INSIGHTS</div>
      <ExportMenu format={format} onFormat={onFormat} onDownload={onDownload} buttonLabel="Download insights" />
    </div>
    <div className="insight-caption">
      A compact summary of the entire video, optimized for fast understanding before you drill into sections.
    </div>
    <div className="insight-list">
      {(Array.isArray(insights) ? insights : []).length === 0 ? (
        <div className="section-empty">No key insights were returned for this video yet.</div>
      ) : (Array.isArray(insights) ? insights : []).map((ins, i) => (
        <div key={i} className="insight">
          <span className="insight-num">{String(i + 1).padStart(2, "0")}</span>
          <span>{ins}</span>
        </div>
      ))}
    </div>
  </div>
);

const MindmapPanel = ({ data, context, onPng, loading }) => (
  <div className="panel" data-screen-label="Mindmap">
    <div className="panel-head">
      <div className="panel-title">
        ◉ MIND MAP
        <span className="tag tag-interactive">INTERACTIVE</span>
      </div>
      <button type="button" className="export-btn" onClick={onPng} title="Download image" disabled={loading}>Download image</button>
    </div>
    {loading ? (
      <div className="mindmap-loading" role="status" aria-live="polite">
        <div className="mindmap-loading-grid" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
          <span />
          <span />
        </div>
        <div className="mindmap-loading-copy mono">MINDMAP IS RENDERING...</div>
      </div>
    ) : (
      <Mindmap data={data} context={context} />
    )}
  </div>
);

const TranscriptPanel = ({ data, format, onFormat, onDownload, onCopy }) => {
  const transcript = data?.transcript || { segments: [], text: "" };
  const segments = Array.isArray(transcript.segments) ? transcript.segments : [];

  return (
    <div className="panel" data-screen-label="Transcript">
      <div className="panel-head">
        <div className="panel-title">
          ◉ TRANSCRIPT
          <span className="tag transcript-tag">{segments.length || "FULL"}</span>
        </div>
        <div className="transcript-actions">
          <button type="button" className="export-btn" onClick={onCopy}>Copy transcript</button>
          <ExportMenu format={format} onFormat={onFormat} onDownload={onDownload} buttonLabel="Download transcript" />
        </div>
      </div>
      {segments.length === 0 ? (
        <div className="section-empty">No transcript was returned for this video yet.</div>
      ) : (
        <div className="transcript-list">
          {segments.map((segment) => (
            <div key={segment.id} className="transcript-row">
              <div className="transcript-time mono">[{segment.timestamp}]</div>
              <div className="transcript-text">{segment.text}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

/* Uncontrolled <details> - do not mix controlled `open` + onToggle; it can fight the
   browser and loop/crash React (blank page). Styling still uses details[open] in CSS. */
const Accordion = ({ title, defaultOpen, children }) => (
  <details className="accordion" open={defaultOpen ? true : undefined}>
    <summary>
      <span className="acc-led" />
      {title}
      <span className="acc-caret">›</span>
    </summary>
    <div className="acc-body">{children}</div>
  </details>
);

function getRenderableSections(data) {
  const d = data || {};
  if (Array.isArray(d.summary?.key_sections) && d.summary.key_sections.length) return d.summary.key_sections;
  if (Array.isArray(d.sections) && d.sections.length) return d.sections;
  if (Array.isArray(d.key_sections) && d.key_sections.length) return d.key_sections;
  return [];
}

const KeySectionsBody = ({ sections }) => (
  <>
    {sections.length === 0 ? (
      <div className="section-empty">No key sections were returned for this video yet.</div>
    ) : sections.map((s, i) => (
      <div key={i} className="section-item">
        <div className="section-copy">
          <div className="section-title">
            <span>{s.title}</span>
            {(s.t || s.time || s.timestamp) ? (
              <span className="section-time">{s.t || s.time || s.timestamp}</span>
            ) : null}
          </div>
          <div className="section-body">{s.body || s.desc || s.description}</div>

          {Array.isArray(s.steps) && s.steps.length > 0 && (
            <ul style={{ paddingLeft: "20px", marginTop: "10px", marginBottom: "10px", fontSize: "13px", color: "var(--ink-soft)" }}>
              {s.steps.map((step, si) => <li key={si}>{step}</li>)}
            </ul>
          )}

          {Array.isArray(s.subPoints || s.sub_points) && (s.subPoints || s.sub_points).length > 0 && (
            <div style={{ marginTop: "10px" }}>
              <div style={{ fontSize: "11px", letterSpacing: ".08em", color: "var(--muted)", marginBottom: "6px" }}>KEY DETAILS</div>
              <ul style={{ paddingLeft: "20px", marginTop: 0, marginBottom: "10px", fontSize: "13px", color: "var(--ink-soft)" }}>
                {(s.subPoints || s.sub_points).map((point, si) => <li key={si}>{point}</li>)}
              </ul>
            </div>
          )}

          {Array.isArray(s.tradeOffs || s.trade_offs) && (s.tradeOffs || s.trade_offs).length > 0 && (
            <div style={{ marginTop: "10px" }}>
              <div style={{ fontSize: "11px", letterSpacing: ".08em", color: "var(--muted)", marginBottom: "6px" }}>TRADE-OFFS / LIMITS</div>
              <ul style={{ paddingLeft: "20px", marginTop: 0, marginBottom: "10px", fontSize: "13px", color: "var(--ink-soft)" }}>
                {(s.tradeOffs || s.trade_offs).map((point, si) => <li key={si}>{point}</li>)}
              </ul>
            </div>
          )}

          {(s.notable || s.notable_detail) && (
            <div style={{ marginTop: "10px", padding: "10px", background: "rgba(255,255,255,0.4)", borderRadius: "6px", borderLeft: "3px solid var(--led-amber)", fontSize: "12px" }}>
              <strong style={{ color: "var(--led-amber)" }}>NOTABLE:</strong> {s.notable || s.notable_detail}
            </div>
          )}
        </div>
      </div>
    ))}
  </>
);

const KeySectionsPanel = ({ data, format, onFormat, onDownload }) => {
  const sections = Array.isArray(data?.sections) && data.sections.length
    ? data.sections
    : getRenderableSections(data);
  return (
    <div className="panel" data-screen-label="Key Sections">
      <div className="panel-head">
        <div className="panel-title">
          ◉ KEY SECTIONS
          <span className="tag tag-interactive">{sections.length}</span>
        </div>
        <ExportMenu format={format} onFormat={onFormat} onDownload={onDownload} buttonLabel="Download sections" />
      </div>
      <KeySectionsBody sections={sections} />
    </div>
  );
};

const DeepDivePanel = ({ data, format, onFormat, onDownload }) => {
  const d = data || {};
  const deepDiveSections = Array.isArray(d.deepDive?.sections) ? d.deepDive.sections : [];
  const comparison = d.comparison && Array.isArray(d.comparison.rows) && d.comparison.rows.length ? d.comparison : null;
  const recommendations = Array.isArray(d.recommendations) ? d.recommendations.filter(Boolean) : [];
  const concepts = Array.isArray(d.concepts) ? d.concepts.filter((item) => item && item.name) : [];
  const hasContent = deepDiveSections.length > 0;

  return (
    <div className="panel" data-screen-label="Deep Dive">
      <div className="panel-head">
        <div className="panel-title">
          ◉ DEEP DIVE
          {d.videoType ? <span className="tag deep-dive-tag">{String(d.videoType).toUpperCase()}</span> : null}
        </div>
        <ExportMenu format={format} onFormat={onFormat} onDownload={onDownload} buttonLabel="Download deep dive" />
      </div>

      {!hasContent ? (
        <div className="section-empty">No deep-dive material was returned for this video yet.</div>
      ) : (
        <div className="deep-dive-copy">
          <div className="deep-dive-eyebrow">FULLER ANALYSIS</div>
          {deepDiveSections.map((section) => (
            <section key={section.id} className="deep-dive-section">
              <h3 className="deep-dive-heading">{section.heading}</h3>
              {section.paragraphs.map((paragraph, i) => <p key={`${section.id}-${i}`}>{paragraph}</p>)}
            </section>
          ))}

          {comparison ? (
            <section className="deep-dive-section">
              <h3 className="deep-dive-heading">Comparison Snapshot</h3>
              <div className="deep-dive-table-wrap">
                <table className="cmp-table">
                  <thead>
                    <tr>
                      {comparison.headers.map((header, i) => <th key={i}>{header}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {comparison.rows.map((row, rowIndex) => (
                      <tr key={rowIndex}>
                        {row.map((cell, cellIndex) => <td key={cellIndex}>{cell}</td>)}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          {recommendations.length ? (
            <section className="deep-dive-section">
              <h3 className="deep-dive-heading">What To Do With This</h3>
              <div className="deep-dive-chip-grid">
                {recommendations.map((item, i) => (
                  <div key={i} className="deep-dive-chip-card">
                    <span className="deep-dive-chip-index mono">{String(i + 1).padStart(2, "0")}</span>
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </section>
          ) : null}

          {concepts.length ? (
            <section className="deep-dive-section">
              <h3 className="deep-dive-heading">Core Concepts</h3>
              <div className="concepts-grid">
                {concepts.map((concept, i) => (
                  <div key={concept.name || i} className="concept">
                    <div className="concept-term">{concept.name}</div>
                    <div className="concept-def">{concept.desc}</div>
                    {concept.sig ? <div className="concept-sig">{concept.sig}</div> : null}
                  </div>
                ))}
              </div>
            </section>
          ) : null}
        </div>
      )}
    </div>
  );
};

const SUMMARY_TABS = [
  { id: "insights", label: "Insights" },
  { id: "sections", label: "Key Sections" },
  { id: "deep-dive", label: "Deep Dive" },
  { id: "mindmap", label: "Mind Map" },
  { id: "transcript", label: "Transcript" },
];

const SummaryWorkspace = ({
  data,
  activeTab,
  onTabChange,
  format,
  onFormat,
  onSectionDownload,
  onTranscriptCopy,
  onMindmapPng,
  mindmapLoading,
}) => {
  const currentTab = SUMMARY_TABS.some((tab) => tab.id === activeTab) ? activeTab : "insights";

  return (
    <div className="summary-workspace">
      <div className="summary-tabs" role="tablist" aria-label="Summary views">
        {SUMMARY_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            className={`summary-tab${currentTab === tab.id ? " active" : ""}`}
            aria-selected={currentTab === tab.id ? "true" : "false"}
            onClick={() => onTabChange && onTabChange(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {currentTab === "insights" ? (
        <KeyInsightsPanel
          insights={data?.insights || []}
          format={format}
          onFormat={onFormat}
          onDownload={(nextFormat) => onSectionDownload && onSectionDownload("insights", nextFormat)}
        />
      ) : null}

      {currentTab === "sections" ? (
        <KeySectionsPanel
          data={data}
          format={format}
          onFormat={onFormat}
          onDownload={(nextFormat) => onSectionDownload && onSectionDownload("sections", nextFormat)}
        />
      ) : null}
      {currentTab === "deep-dive" ? (
        <DeepDivePanel
          data={data}
          format={format}
          onFormat={onFormat}
          onDownload={(nextFormat) => onSectionDownload && onSectionDownload("deep-dive", nextFormat)}
        />
      ) : null}
      {currentTab === "mindmap" ? <MindmapPanel data={data?.mindmap} context={data} onPng={onMindmapPng} loading={mindmapLoading} /> : null}
      {currentTab === "transcript" ? (
        <TranscriptPanel
          data={data}
          format={format}
          onFormat={onFormat}
          onDownload={(nextFormat) => onSectionDownload && onSectionDownload("transcript", nextFormat)}
          onCopy={onTranscriptCopy}
        />
      ) : null}
    </div>
  );
};

Object.assign(window, {
  VideoProfile,
  MindmapPanel,
  SummaryWorkspace,
});
