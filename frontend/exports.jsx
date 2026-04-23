/* Client-side export helpers — assigned to window for app.jsx */

function absMediaUrl(u) {
  if (u == null || u === "") return "";
  const s = String(u);
  if (/^https?:\/\//i.test(s)) return s;
  if (s.startsWith("//")) return window.location.protocol + s;
  if (s.startsWith("/")) return window.location.origin + s;
  return s;
}

function downloadBlob(filename, blob) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(a.href), 4000);
}

function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function buildMarkdown(result) {
  const m = result.metadata || {};
  const lines = [];
  lines.push(`# ${m.title || "Video summary"}`);
  lines.push("");
  lines.push(`**Channel:** ${m.channel || "—"}  `);
  lines.push(`**Duration:** ${m.duration || "—"}`);
  lines.push("");
  lines.push("## Overview");
  lines.push("");
  lines.push(result.pitch || "");
  lines.push("");
  const insights = Array.isArray(result.insights) ? result.insights : [];
  if (insights.length) {
    lines.push("## Key insights");
    lines.push("");
    insights.forEach((t, i) => lines.push(`${i + 1}. ${t}`));
    lines.push("");
  }
  const sections = Array.isArray(result.sections) ? result.sections : [];
  if (sections.length) {
    lines.push("## Key sections");
    lines.push("");
    sections.forEach((sec) => {
      const time = sec.t || sec.time || "";
      lines.push(`### ${time ? `[${time}] ` : ""}${sec.title || "Section"}`);
      lines.push("");
      lines.push(sec.body || sec.desc || "");
      lines.push("");
    });
  }
  const concepts = Array.isArray(result.concepts) ? result.concepts : [];
  if (concepts.length) {
    lines.push("## Important concepts");
    lines.push("");
    concepts.forEach((c) => {
      const term = c.term || c.name || "Concept";
      lines.push(`### ${term}`);
      lines.push("");
      lines.push(c.def || c.desc || "");
      lines.push("");
    });
  }
  const cmp = result.comparison;
  if (cmp && Array.isArray(cmp.headers) && cmp.headers.length && Array.isArray(cmp.rows)) {
    lines.push("## Comparison");
    lines.push("");
    lines.push("| " + cmp.headers.join(" | ") + " |");
    lines.push("| " + cmp.headers.map(() => "---").join(" | ") + " |");
    cmp.rows.forEach((row) => {
      if (Array.isArray(row)) {
        lines.push("| " + row.map((c) => String(c).replace(/\|/g, "\\|")).join(" | ") + " |");
      } else {
        lines.push("| " + String(row).replace(/\|/g, "\\|") + " |");
      }
    });
    lines.push("");
  }
  const rec = Array.isArray(result.recommendations) ? result.recommendations : [];
  if (rec.length) {
    lines.push("## Recommendations");
    lines.push("");
    rec.forEach((r) => lines.push(`- ${r}`));
    lines.push("");
  }
  if (result.conclusion) {
    lines.push("## Conclusion");
    lines.push("");
    lines.push(String(result.conclusion));
    lines.push("");
  }
  return lines.join("\n");
}

/** Word-friendly HTML (opens in Microsoft Word). */
function buildWordHtml(result) {
  const m = result.metadata || {};
  const body = [];
  body.push(`<h1>${escapeHtml(m.title)}</h1>`);
  body.push(`<p><strong>Channel:</strong> ${escapeHtml(m.channel)} &nbsp; <strong>Duration:</strong> ${escapeHtml(m.duration)}</p>`);
  body.push(`<h2>Overview</h2><p>${escapeHtml(result.pitch).replace(/\n/g, "<br/>")}</p>`);
  const insights = Array.isArray(result.insights) ? result.insights : [];
  if (insights.length) {
    body.push("<h2>Key insights</h2><ol>");
    insights.forEach((t) => body.push(`<li>${escapeHtml(t)}</li>`));
    body.push("</ol>");
  }
  const sections = Array.isArray(result.sections) ? result.sections : [];
  if (sections.length) {
    body.push("<h2>Key sections</h2>");
    sections.forEach((sec) => {
      const time = sec.t || sec.time || "";
      body.push(`<h3>${escapeHtml((time ? "[" + time + "] " : "") + (sec.title || ""))}</h3>`);
      body.push(`<p>${escapeHtml(sec.body || sec.desc || "").replace(/\n/g, "<br/>")}</p>`);
    });
  }
  if (result.conclusion) {
    body.push(`<h2>Conclusion</h2><p>${escapeHtml(result.conclusion).replace(/\n/g, "<br/>")}</p>`);
  }
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(m.title)}</title></head><body>${body.join("")}</body></html>`;
}

function downloadWord(result) {
  const html = buildWordHtml(result);
  const blob = new Blob(["\ufeff", html], { type: "application/msword;charset=utf-8" });
  const safe = String(result.metadata?.title || "summary").replace(/[^\w\-]+/g, "_").slice(0, 80);
  downloadBlob(`${safe}.doc`, blob);
}

function openPrintablePdf(result) {
  const m = result.metadata || {};
  const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(m.title)}</title>
  <style>
    @page { margin: 18mm; }
    body { font-family: system-ui, Segoe UI, sans-serif; color: #111; line-height: 1.45; max-width: 720px; margin: 0 auto; padding: 12px; }
    h1 { font-size: 22px; margin-bottom: 8px; }
    h2 { font-size: 15px; margin-top: 20px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }
    h3 { font-size: 13px; margin-top: 14px; }
    p, li { font-size: 11.5px; }
    .meta { font-size: 10px; color: #444; margin-bottom: 16px; }
  </style></head><body>
  <h1>${escapeHtml(m.title)}</h1>
  <div class="meta">${escapeHtml(m.channel || "")} · ${escapeHtml(m.duration || "")}</div>
  <h2>Overview</h2>
  <p>${escapeHtml(result.pitch).replace(/\n/g, "<br/>")}</p>
  ${(Array.isArray(result.insights) && result.insights.length) ? `<h2>Key insights</h2><ol>${result.insights.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ol>` : ""}
  ${(Array.isArray(result.sections) && result.sections.length) ? result.sections.map((sec) => {
    const time = sec.t || sec.time || "";
    return `<h3>${escapeHtml((time ? "[" + time + "] " : "") + (sec.title || ""))}</h3><p>${escapeHtml(sec.body || sec.desc || "").replace(/\n/g, "<br/>")}</p>`;
  }).join("") : ""}
  ${result.conclusion ? `<h2>Conclusion</h2><p>${escapeHtml(result.conclusion).replace(/\n/g, "<br/>")}</p>` : ""}
  <script>window.onload=function(){window.focus();window.print();};<\/script>
  </body></html>`;
  const w = window.open("", "_blank", "noopener,noreferrer");
  if (!w) {
    alert("Pop-up blocked — allow pop-ups to save as PDF.");
    return;
  }
  w.document.write(html);
  w.document.close();
}

/**
 * Export mindmap panel (SVG inside root) as PNG.
 */
function downloadMindmapPng(rootEl) {
  if (!rootEl) {
    alert("Mindmap not ready.");
    return;
  }
  const svg = rootEl.querySelector("svg");
  if (!svg) {
    alert("Nothing to export yet.");
    return;
  }
  const rect = svg.getBoundingClientRect();
  const w = Math.max(1, Math.floor(svg.viewBox?.baseVal?.width || rect.width || 900));
  const h = Math.max(1, Math.floor(svg.viewBox?.baseVal?.height || rect.height || 460));
  let source = new XMLSerializer().serializeToString(svg);
  if (!source.includes("xmlns=")) {
    source = source.replace("<svg", '<svg xmlns="http://www.w3.org/2000/svg"');
  }
  const img = new Image();
  const svgBlob = new Blob([source], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(svgBlob);
  img.onload = () => {
    try {
      const canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#0a0806";
      ctx.fillRect(0, 0, w, h);
      ctx.drawImage(img, 0, 0, w, h);
      canvas.toBlob((blob) => {
        URL.revokeObjectURL(url);
        if (blob) downloadBlob("mindmap.png", blob);
        else alert("Could not create PNG.");
      }, "image/png");
    } catch (e) {
      URL.revokeObjectURL(url);
      console.error(e);
      alert("Export failed (try a different browser).");
    }
  };
  img.onerror = () => {
    URL.revokeObjectURL(url);
    alert("Could not render mindmap image.");
  };
  img.src = url;
}

Object.assign(window, {
  absMediaUrl,
  downloadBlob,
  buildMarkdown,
  downloadWord,
  openPrintablePdf,
  downloadMindmapPng,
});
