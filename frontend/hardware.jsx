/* Reusable hardware primitives */

const Screws = () => (
  <>
    <span className="screw tl" /><span className="screw tr" />
    <span className="screw bl" /><span className="screw br" />
  </>
);

const Led = ({ on, blink, title }) => (
  <span
    className={`led${on ? " on" : ""}${blink ? " blink" : ""}`}
    title={title}
  />
);

const Knob = ({ value = 0, onChange, min = 0, max = 100, label }) => {
  // value maps to angle from -135 to +135
  const angle = -135 + (value - min) / (max - min) * 270;
  const ref = React.useRef(null);
  const drag = React.useRef(null);

  const onDown = (e) => {
    e.preventDefault();
    drag.current = { y: e.clientY ?? e.touches?.[0]?.clientY, v: value };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  };
  const onMove = (e) => {
    if (!drag.current) return;
    const cy = e.clientY ?? e.touches?.[0]?.clientY;
    const dy = drag.current.y - cy;
    const next = Math.max(min, Math.min(max, drag.current.v + dy * 0.8));
    onChange && onChange(Math.round(next));
  };
  const onUp = () => {
    drag.current = null;
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
  };

  return (
    <div style={{ textAlign: "center" }}>
      <div
        ref={ref}
        className="knob"
        style={{ "--angle": angle + "deg" }}
        onMouseDown={onDown}
        title={`${label ?? ""}: ${value}`}
      />
      {label && <div className="btn-sublabel" style={{ marginTop: 4 }}>{label}</div>}
    </div>
  );
};

const DistillButton = ({ onClick, disabled, busy, label = "DISTILL" }) => (
  <div className="distill-well">
    <Led on={!disabled && !busy} />
    <div>
      <button
        className={`distill-btn${busy ? " pressed" : ""}`}
        onClick={onClick}
        disabled={disabled || busy}
      >
        {busy ? "WORKING…" : label}
      </button>
    </div>
    <Led on={!disabled && !busy} blink={busy} />
  </div>
);

const SearchField = ({ value, onChange, onSubmit, placeholder }) => (
  <div className="search-container">
    <span className="mono" style={{ fontSize: 11, color: "#8a8473", letterSpacing: ".12em", marginRight: 8 }}>URL</span>
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onKeyDown={(e) => e.key === "Enter" && onSubmit && onSubmit()}
      placeholder={placeholder}
    />
    <button className="search-btn" onClick={onSubmit} title="Paste from clipboard">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#3a362d" strokeWidth="2.2" strokeLinecap="round">
        <circle cx="11" cy="11" r="6" />
        <line x1="21" y1="21" x2="15.5" y2="15.5" />
      </svg>
    </button>
  </div>
);

/* progress / error / video / misc */

const ProgressCard = ({ stepIdx, pct, label }) => (
  <div className="inset-card" role="status">
    <div className="progress-head">
      <div className="progress-title">
        <Led on blink /> &nbsp; DISTILLATION IN PROGRESS
      </div>
      <div className="mono" style={{ fontSize: 11, color: "var(--muted)", letterSpacing: ".1em" }}>
        {String(Math.round(pct)).padStart(3, "0")}% · LIVE
      </div>
    </div>
    <div className="progress-steps">
      {PROGRESS_STEPS.map((s, i) => (
        <div
          key={s}
          className={`progress-step${i < stepIdx ? " done" : ""}${i === stepIdx ? " active" : ""}`}
        >
          {s}
        </div>
      ))}
    </div>
    <div className="vu-track"><div className="vu-fill" style={{ width: pct + "%" }} /></div>
    <div className="vu-readout">
      <span>▸ {label}</span>
      <span>CH-01 · SSE · {Math.round(pct * 2.4)} pkt/s</span>
    </div>
  </div>
);

const ErrorCard = ({ message, onDismiss }) => (
  <div className="inset-card error-card" role="alert">
    <div className="progress-head">
      <div className="error-title">◆ Signal dropped</div>
      <button className="demo-btn" onClick={onDismiss}>Dismiss</button>
    </div>
    <div className="mono" style={{ fontSize: 12, color: "var(--ink-soft)" }}>
      {message}
    </div>
  </div>
);

Object.assign(window, {
  Screws, Led, Knob, DistillButton, SearchField,
  ProgressCard, ErrorCard,
});
