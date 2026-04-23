/* Tweaks panel — persists tone, LED color, grain, auto-demo */

const TONE_SWATCHES = [
  { id: "ivory",   bg: "linear-gradient(180deg,#f7f1e1,#e2d8c2)" },
  { id: "graphite", bg: "linear-gradient(180deg,#3a3a3a,#121212)" },
  { id: "olive",   bg: "linear-gradient(180deg,#cfc795,#8d8550)" },
  { id: "oxblood", bg: "linear-gradient(180deg,#8a3831,#3b110c)" },
];

const LED_SWATCHES = [
  { id: "amber",  color: "#ff7a1a" },
  { id: "red",    color: "#e53824" },
  { id: "green",  color: "#3fbf5b" },
  { id: "blue",   color: "#2a86ff" },
  { id: "violet", color: "#8b54e8" },
];

const TweaksPanel = ({ tweaks, onChange }) => {
  const [visible, setVisible] = React.useState(false);

  React.useEffect(() => {
    const handler = (e) => {
      if (e?.data?.type === "__activate_edit_mode") setVisible(true);
      if (e?.data?.type === "__deactivate_edit_mode") setVisible(false);
    };
    window.addEventListener("message", handler);
    // Tell host we support edit mode
    window.parent?.postMessage({ type: "__edit_mode_available" }, "*");
    return () => window.removeEventListener("message", handler);
  }, []);

  const set = (key, value) => {
    const next = { ...tweaks, [key]: value };
    onChange(next);
    window.parent?.postMessage({ type: "__edit_mode_set_keys", edits: { [key]: value } }, "*");
  };

  if (!visible) return null;

  return (
    <div className="tweaks-panel">
      <div className="tweaks-head">
        <span className="led on" style={{ width: 8, height: 8 }} />
        TWEAKS · REEL DISTILLER
      </div>
      <div className="tweaks-body">
        <div className="tweak-row">
          <div className="tweak-label">Faceplate</div>
          <div className="tweak-options">
            {TONE_SWATCHES.map(s => (
              <span
                key={s.id}
                className={`tweak-swatch${tweaks.faceplateTone === s.id ? " on" : ""}`}
                style={{ background: s.bg }}
                onClick={() => set("faceplateTone", s.id)}
                title={s.id}
              />
            ))}
          </div>
        </div>

        <div className="tweak-row">
          <div className="tweak-label">LED color</div>
          <div className="tweak-options">
            {LED_SWATCHES.map(s => (
              <span
                key={s.id}
                className={`tweak-swatch${tweaks.ledColor === s.id ? " on" : ""}`}
                style={{ background: s.color, boxShadow: `0 0 8px ${s.color}` }}
                onClick={() => set("ledColor", s.id)}
                title={s.id}
              />
            ))}
          </div>
        </div>

        <div className="tweak-row">
          <div className="tweak-label">Surface grain</div>
          <div className="tweak-options">
            {[true, false].map(v => (
              <button
                key={String(v)}
                className={`tweak-opt${tweaks.grainOn === v ? " on" : ""}`}
                onClick={() => set("grainOn", v)}
              >
                {v ? "ON" : "OFF"}
              </button>
            ))}
          </div>
        </div>

        <div className="tweak-row">
          <div className="tweak-label">Auto-run demo on load</div>
          <div className="tweak-options">
            {[true, false].map(v => (
              <button
                key={String(v)}
                className={`tweak-opt${tweaks.autoDemo === v ? " on" : ""}`}
                onClick={() => set("autoDemo", v)}
              >
                {v ? "YES" : "NO"}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { TweaksPanel });
