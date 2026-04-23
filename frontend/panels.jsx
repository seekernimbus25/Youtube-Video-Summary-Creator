/* Result panels: video profile, insights, accordions */

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

const InsightsPanel = ({ insights, format, onFormat, onDownload }) => (
  <div className="panel" data-screen-label="Insights">
    <div className="panel-head">
      <div className="panel-title">◉ KEY INSIGHTS</div>
      <div className="export-menu" role="group" aria-label="Export">
        {["md", "docx", "pdf"].map(f => (
          <button
            key={f}
            type="button"
            className={`export-btn${format === f ? " active" : ""}`}
            title={f === "docx" ? "Download Word-compatible .doc" : f === "pdf" ? "Opens print — save as PDF" : "Download Markdown"}
            onClick={() => {
              onFormat && onFormat(f);
              onDownload && onDownload(f);
            }}
          >
            .{f}
          </button>
        ))}
      </div>
    </div>
    <div className="insight-list">
      {(Array.isArray(insights) ? insights : []).map((ins, i) => (
        <div key={i} className="insight">
          <span className="insight-num">{String(i + 1).padStart(2, "0")}</span>
          <span>{ins}</span>
        </div>
      ))}
    </div>
  </div>
);

const MindmapPanel = ({ data, onPng }) => (
  <div className="panel" data-screen-label="Mindmap">
    <div className="panel-head">
      <div className="panel-title">
        ◉ MINDMAP
        <span className="tag tag-interactive">INTERACTIVE</span>
      </div>
      <button type="button" className="export-btn" onClick={onPng} title="Download PNG">.PNG</button>
    </div>
    <Mindmap data={data} />
  </div>
);

const ScreenshotsGallery = ({ shots }) => {
  const list = Array.isArray(shots) ? shots.filter((s) => s && s.src) : [];
  if (!list.length) return null;
  return (
    <div className="panel screenshots-panel" data-screen-label="Screenshots">
      <div className="panel-head">
        <div className="panel-title">◉ FRAME CAPTURES</div>
        <span className="tag tag-interactive">{list.length} SHOT{list.length === 1 ? "" : "S"}</span>
      </div>
      <div className="screenshots-strip">
        {list.map((sh, i) => (
          <figure key={i} className="shot-card">
            <img src={sh.src} alt={sh.caption || ""} loading="lazy" />
            {sh.caption ? <figcaption className="shot-cap mono">{sh.caption}</figcaption> : null}
          </figure>
        ))}
      </div>
    </div>
  );
};

/* Uncontrolled <details> — do not mix controlled `open` + onToggle; it can fight the
   browser and loop/crash React (blank page). Styling still uses details[open] in CSS. */
const Accordion = ({ title, defaultOpen, children }) => (
  <details className="accordion" defaultOpen={defaultOpen}>
    <summary>
      <span className="acc-led" />
      {title}
      <span className="acc-caret">›</span>
    </summary>
    <div className="acc-body">{children}</div>
  </details>
);

const DetailSections = ({ data }) => {
  const d = data || {};
  const sections = Array.isArray(d.sections) ? d.sections : [];
  const concepts = Array.isArray(d.concepts) ? d.concepts : [];
  return (
    <>
      <Accordion title="▸ KEY SECTIONS" defaultOpen>
        {sections.map((s, i) => (
          <div key={i} className="section-item">
            <span className="section-time">{s.t || s.time}</span>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div className="section-title">{s.title}</div>
              <div className="section-body">{s.body || s.desc}</div>
              
              {s.steps && s.steps.length > 0 && (
                <ul style={{ paddingLeft: '20px', marginTop: '10px', marginBottom: '10px', fontSize: '13px', color: 'var(--ink-soft)' }}>
                  {s.steps.map((step, si) => <li key={si}>{step}</li>)}
                </ul>
              )}
              
              {s.notable && (
                <div style={{ marginTop: '10px', padding: '10px', background: 'rgba(255,255,255,0.4)', borderRadius: '6px', borderLeft: '3px solid var(--led-amber)', fontSize: '12px' }}>
                  <strong style={{ color: 'var(--led-amber)' }}>NOTABLE:</strong> {s.notable}
                </div>
              )}
              
              {s.shots && s.shots.length > 0 && (
                <div style={{ display: 'flex', gap: '12px', marginTop: '12px', flexWrap: 'wrap' }}>
                  {s.shots.map((sh, si) => (
                    <div key={si} style={{ flex: '1 1 200px', background: '#000', borderRadius: '6px', overflow: 'hidden', border: '1px solid rgba(0,0,0,0.15)', boxShadow: '0 4px 6px rgba(0,0,0,0.1)' }}>
                      <img src={sh.src} alt="Context" style={{ width: '100%', display: 'block', objectFit: 'cover', aspectRatio: '16/9' }} />
                      <div style={{ padding: '6px 8px', fontSize: '11px', color: '#ddd', background: '#111', borderTop: '1px solid #333' }}>{sh.caption}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </Accordion>

      <Accordion title="▸ IMPORTANT CONCEPTS" defaultOpen={false}>
        <div className="concepts-grid">
          {concepts.map((c, i) => (
            <div key={i} className="concept">
              <div className="concept-term">{c.term || c.name}</div>
              <div className="concept-def">{c.def || c.desc}</div>
              {c.sig && <div style={{ marginTop: '6px', fontSize: '11.5px', color: 'var(--muted)', fontStyle: 'italic' }}>{c.sig}</div>}
            </div>
          ))}
        </div>
      </Accordion>

      {d.comparison && d.comparison.headers && (
        <Accordion title="▸ COMPARISON TABLE" defaultOpen={false}>
          <div style={{ overflowX: 'auto' }}>
            <table className="cmp-table">
              <thead>
                <tr>{d.comparison.headers.map((h, i) => <th key={i}>{h}</th>)}</tr>
              </thead>
              <tbody>
                {(d.comparison.rows || []).map((r, i) => (
                  <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </Accordion>
      )}

      {Array.isArray(d.recommendations) && d.recommendations.length > 0 && (
        <Accordion title="▸ PRACTICAL RECOMMENDATIONS" defaultOpen={false}>
          <ol className="rec-list">
            {d.recommendations.map((r, i) => <li key={i}>{r}</li>)}
          </ol>
        </Accordion>
      )}

      {d.conclusion && (
        <Accordion title="▸ CONCLUSION" defaultOpen={false}>
          <p style={{ margin: 0, fontSize: 14.5, lineHeight: 1.6 }}>{d.conclusion}</p>
        </Accordion>
      )}
    </>
  );
};

Object.assign(window, { VideoProfile, InsightsPanel, MindmapPanel, ScreenshotsGallery, DetailSections });
