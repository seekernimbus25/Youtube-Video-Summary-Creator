/* Result panels: video profile, insights, accordions */

const VideoProfile = ({ meta, pitch }) => (
  <div className="panel" data-screen-label="Video">
    <div className="video-profile">
      <div className="thumb">
        <span className="thumb-label">16:9 · SOURCE</span>
        <span className="thumb-play">▶</span>
        <span className="thumb-chip mono">{meta.duration}</span>
      </div>
      <div>
        <h2 className="video-title">{meta.title}</h2>
        <div className="video-meta">
          <span>◆ {meta.channel}</span>
          <span>◆ {meta.published}</span>
          <span>◆ {meta.views} views</span>
          <span>◆ EN · CC</span>
        </div>
        <p className="video-pitch">{pitch}</p>
      </div>
    </div>
  </div>
);

const InsightsPanel = ({ insights, format, onFormat }) => (
  <div className="panel" data-screen-label="Insights">
    <div className="panel-head">
      <div className="panel-title">◉ KEY INSIGHTS</div>
      <div className="export-menu" role="group" aria-label="Export">
        {["md", "docx", "pdf"].map(f => (
          <button
            key={f}
            className={`export-btn${format === f ? " active" : ""}`}
            onClick={() => onFormat(f)}
          >
            .{f}
          </button>
        ))}
      </div>
    </div>
    <div className="insight-list">
      {insights.map((ins, i) => (
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
      <button className="export-btn" onClick={onPng}>.PNG</button>
    </div>
    <Mindmap data={data} />
  </div>
);

const Accordion = ({ title, open, onToggle, children }) => (
  <details className="accordion" open={open} onToggle={onToggle}>
    <summary>
      <span className="acc-led" />
      {title}
      <span className="acc-caret">›</span>
    </summary>
    <div className="acc-body">{children}</div>
  </details>
);

const DetailSections = ({ data }) => {
  const [open, setOpen] = React.useState({ sections: true });
  const t = (k) => setOpen(o => ({ ...o, [k]: !o[k] }));
  return (
    <>
      <Accordion title="▸ KEY SECTIONS" open={open.sections !== false} onToggle={() => t("sections")}>
        {data.sections.map((s, i) => (
          <div key={i} className="section-item">
            <span className="section-time">{s.t}</span>
            <div>
              <div className="section-title">{s.title}</div>
              <div className="section-body">{s.body}</div>
            </div>
          </div>
        ))}
      </Accordion>

      <Accordion title="▸ IMPORTANT CONCEPTS" open={!!open.concepts} onToggle={() => t("concepts")}>
        <div className="concepts-grid">
          {data.concepts.map((c, i) => (
            <div key={i} className="concept">
              <div className="concept-term">{c.term}</div>
              <div className="concept-def">{c.def}</div>
            </div>
          ))}
        </div>
      </Accordion>

      <Accordion title="▸ COMPARISON TABLE" open={!!open.comparison} onToggle={() => t("comparison")}>
        <table className="cmp-table">
          <thead>
            <tr>{data.comparison.headers.map((h, i) => <th key={i}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {data.comparison.rows.map((r, i) => (
              <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </Accordion>

      <Accordion title="▸ PRACTICAL RECOMMENDATIONS" open={!!open.rec} onToggle={() => t("rec")}>
        <ol className="rec-list">
          {data.recommendations.map((r, i) => <li key={i}>{r}</li>)}
        </ol>
      </Accordion>

      <Accordion title="▸ CONCLUSION" open={!!open.conc} onToggle={() => t("conc")}>
        <p style={{ margin: 0, fontSize: 14.5, lineHeight: 1.6 }}>{data.conclusion}</p>
      </Accordion>
    </>
  );
};

Object.assign(window, { VideoProfile, InsightsPanel, MindmapPanel, DetailSections });
