/* Client-side export helpers - assigned to window for app.jsx */

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

function renderSectionMarkdown(sec) {
  const lines = [];
  lines.push(sec.body || sec.desc || "");
  if (Array.isArray(sec.steps) && sec.steps.length) {
    lines.push("");
    lines.push("Steps:");
    sec.steps.forEach((step) => lines.push(`- ${step}`));
  }
  if (Array.isArray(sec.subPoints) && sec.subPoints.length) {
    lines.push("");
    lines.push("Key details:");
    sec.subPoints.forEach((point) => lines.push(`- ${point}`));
  }
  if (Array.isArray(sec.tradeOffs) && sec.tradeOffs.length) {
    lines.push("");
    lines.push("Trade-offs:");
    sec.tradeOffs.forEach((point) => lines.push(`- ${point}`));
  }
  if (sec.notable) {
    lines.push("");
    lines.push(`Notable: ${sec.notable}`);
  }
  return lines.join("\n");
}

function renderSectionHtml(sec) {
  const blocks = [`<p>${escapeHtml(sec.body || sec.desc || "").replace(/\n/g, "<br/>")}</p>`];
  if (Array.isArray(sec.steps) && sec.steps.length) {
    blocks.push(`<p><strong>Steps</strong></p><ul>${sec.steps.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}</ul>`);
  }
  if (Array.isArray(sec.subPoints) && sec.subPoints.length) {
    blocks.push(`<p><strong>Key details</strong></p><ul>${sec.subPoints.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>`);
  }
  if (Array.isArray(sec.tradeOffs) && sec.tradeOffs.length) {
    blocks.push(`<p><strong>Trade-offs</strong></p><ul>${sec.tradeOffs.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>`);
  }
  if (sec.notable) {
    blocks.push(`<p><strong>Notable:</strong> ${escapeHtml(sec.notable)}</p>`);
  }
  return blocks.join("");
}

function safeExportBase(title, fallback = "summary") {
  return String(title || fallback).replace(/[^\w\-\s]+/g, "").replace(/\s+/g, "_").slice(0, 72) || fallback;
}

function sectionExportDescriptor(scope) {
  switch (scope) {
    case "insights":
      return {
        title: "Insights",
        suffix: "insights",
      };
    case "sections":
      return {
        title: "Key Sections",
        suffix: "key_sections",
      };
    case "deep-dive":
      return {
        title: "Deep Dive",
        suffix: "deep_dive",
      };
    case "transcript":
      return {
        title: "Transcript",
        suffix: "transcript",
      };
    default:
      return {
        title: "Video Summary",
        suffix: "summary",
      };
  }
}

function transcriptLines(result) {
  const transcript = result?.transcript || {};
  const segments = Array.isArray(transcript.segments) ? transcript.segments : [];
  if (segments.length) {
    return segments.map((segment) => `[${segment.timestamp || "00:00"}] ${segment.text || ""}`);
  }
  const text = String(transcript.text || "").trim();
  return text ? [text] : [];
}

function deepDiveSections(result) {
  const deepDive = result?.deepDive || {};
  return Array.isArray(deepDive.sections) ? deepDive.sections : [];
}

function buildSectionMarkdown(result, scope = "full") {
  const m = result.metadata || {};
  const info = sectionExportDescriptor(scope);
  const lines = [];
  lines.push(`# ${m.title || "Video summary"} - ${info.title}`);
  lines.push("");
  lines.push(`**Channel:** ${m.channel || "-"}  `);
  lines.push(`**Duration:** ${m.duration || "-"}`);
  lines.push("");

  if (scope === "insights") {
    const insights = Array.isArray(result.insights) ? result.insights : [];
    lines.push("## Key insights");
    lines.push("");
    insights.forEach((t, i) => lines.push(`${i + 1}. ${t}`));
    lines.push("");
    return lines.join("\n");
  }

  if (scope === "sections") {
    const sections = Array.isArray(result.sections) ? result.sections : [];
    lines.push("## Key sections");
    lines.push("");
    sections.forEach((sec) => {
      const time = sec.t || sec.time || "";
      lines.push(`### ${time ? `[${time}] ` : ""}${sec.title || "Section"}`);
      lines.push("");
      lines.push(renderSectionMarkdown(sec));
      lines.push("");
    });
    return lines.join("\n");
  }

  if (scope === "deep-dive") {
    const sections = deepDiveSections(result);
    lines.push("## Deep dive");
    lines.push("");
    if (sections.length) {
      sections.forEach((section) => {
        lines.push(`### ${section.heading}`);
        lines.push("");
        section.paragraphs.forEach((part) => {
          lines.push(part);
          lines.push("");
        });
      });
    }
    return lines.join("\n");
  }

  if (scope === "transcript") {
    lines.push("## Transcript");
    lines.push("");
    transcriptLines(result).forEach((line) => lines.push(line));
    lines.push("");
    return lines.join("\n");
  }

  lines.push("## Video snapshot");
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
      lines.push(renderSectionMarkdown(sec));
      lines.push("");
    });
  }

  const deepDive = deepDiveSections(result);
  if (deepDive.length) {
    lines.push("## Deep dive");
    lines.push("");
    deepDive.forEach((section) => {
      lines.push(`### ${section.heading}`);
      lines.push("");
      section.paragraphs.forEach((part) => {
        lines.push(part);
        lines.push("");
      });
    });
  }

  return lines.join("\n");
}

function buildWordHtml(result, scope = "full") {
  const m = result.metadata || {};
  const info = sectionExportDescriptor(scope);
  const body = [];
  body.push(`<h1>${escapeHtml(m.title)} - ${escapeHtml(info.title)}</h1>`);
  body.push(`<p><strong>Channel:</strong> ${escapeHtml(m.channel)} &nbsp; <strong>Duration:</strong> ${escapeHtml(m.duration)}</p>`);

  if (scope === "insights") {
    const insights = Array.isArray(result.insights) ? result.insights : [];
    body.push("<h2>Key insights</h2><ol>");
    insights.forEach((t) => body.push(`<li>${escapeHtml(t)}</li>`));
    body.push("</ol>");
    return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(m.title)}</title></head><body>${body.join("")}</body></html>`;
  }

  if (scope === "sections") {
    const sections = Array.isArray(result.sections) ? result.sections : [];
    body.push("<h2>Key sections</h2>");
    sections.forEach((sec) => {
      const time = sec.t || sec.time || "";
      body.push(`<h3>${escapeHtml((time ? "[" + time + "] " : "") + (sec.title || ""))}</h3>`);
      body.push(renderSectionHtml(sec));
    });
    return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(m.title)}</title></head><body>${body.join("")}</body></html>`;
  }

  if (scope === "deep-dive") {
    const sections = deepDiveSections(result);
    body.push("<h2>Deep dive</h2>");
    sections.forEach((section) => {
      body.push(`<h3>${escapeHtml(section.heading)}</h3>`);
      section.paragraphs.forEach((part) => body.push(`<p>${escapeHtml(part).replace(/\n/g, "<br/>")}</p>`));
    });
    return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(m.title)}</title></head><body>${body.join("")}</body></html>`;
  }

  if (scope === "transcript") {
    body.push("<h2>Transcript</h2>");
    transcriptLines(result).forEach((line) => {
      body.push(`<p>${escapeHtml(line).replace(/\n/g, "<br/>")}</p>`);
    });
    return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(m.title)}</title></head><body>${body.join("")}</body></html>`;
  }

  body.push(`<h2>Video snapshot</h2><p>${escapeHtml(result.pitch).replace(/\n/g, "<br/>")}</p>`);
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
      body.push(renderSectionHtml(sec));
    });
  }
  const deepDive = deepDiveSections(result);
  if (deepDive.length) {
    body.push("<h2>Deep dive</h2>");
    deepDive.forEach((section) => {
      body.push(`<h3>${escapeHtml(section.heading)}</h3>`);
      section.paragraphs.forEach((part) => {
        body.push(`<p>${escapeHtml(part).replace(/\n/g, "<br/>")}</p>`);
      });
    });
  }
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${escapeHtml(m.title)}</title></head><body>${body.join("")}</body></html>`;
}

function downloadWord(result, scope = "full") {
  const html = buildWordHtml(result, scope);
  const info = sectionExportDescriptor(scope);
  const blob = new Blob(["\ufeff", html], { type: "application/msword;charset=utf-8" });
  const safe = safeExportBase(result.metadata?.title || "summary", info.suffix);
  downloadBlob(`${safe}_${info.suffix}.doc`, blob);
}

function openPrintablePdf(result, scope = "full") {
  const m = result.metadata || {};
  const info = sectionExportDescriptor(scope);
  const contentHtml = (() => {
    if (scope === "insights") {
      return (Array.isArray(result.insights) && result.insights.length)
        ? `<h2>Key insights</h2><ol>${result.insights.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ol>`
        : "<p>No key insights available.</p>";
    }
    if (scope === "sections") {
      return (Array.isArray(result.sections) && result.sections.length)
        ? `<h2>Key sections</h2>${result.sections.map((sec) => {
            const time = sec.t || sec.time || "";
            return `<h3>${escapeHtml((time ? "[" + time + "] " : "") + (sec.title || ""))}</h3>${renderSectionHtml(sec)}`;
          }).join("")}`
        : "<p>No key sections available.</p>";
    }
    if (scope === "deep-dive") {
      const sections = deepDiveSections(result);
      return sections.length
        ? `<h2>Deep dive</h2>${sections.map((section) => `<h3>${escapeHtml(section.heading)}</h3>${section.paragraphs.map((part) => `<p>${escapeHtml(part).replace(/\n/g, "<br/>")}</p>`).join("")}`).join("")}`
        : "<p>No deep dive available.</p>";
    }
    if (scope === "transcript") {
      const lines = transcriptLines(result);
      return lines.length
        ? `<h2>Transcript</h2>${lines.map((line) => `<p>${escapeHtml(line).replace(/\n/g, "<br/>")}</p>`).join("")}`
        : "<p>No transcript available.</p>";
    }
    return `
      <h2>Video snapshot</h2>
      <p>${escapeHtml(result.pitch).replace(/\n/g, "<br/>")}</p>
      ${(Array.isArray(result.insights) && result.insights.length) ? `<h2>Key insights</h2><ol>${result.insights.map((t) => `<li>${escapeHtml(t)}</li>`).join("")}</ol>` : ""}
      ${(Array.isArray(result.sections) && result.sections.length) ? result.sections.map((sec) => {
        const time = sec.t || sec.time || "";
        return `<h3>${escapeHtml((time ? "[" + time + "] " : "") + (sec.title || ""))}</h3>${renderSectionHtml(sec)}`;
      }).join("") : ""}
      ${deepDiveSections(result).length ? `<h2>Deep dive</h2>${deepDiveSections(result).map((section) => `<h3>${escapeHtml(section.heading)}</h3>${section.paragraphs.map((part) => `<p>${escapeHtml(part).replace(/\n/g, "<br/>")}</p>`).join("")}`).join("")}` : ""}
    `;
  })();

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
  <h1>${escapeHtml(m.title)} - ${escapeHtml(info.title)}</h1>
  <div class="meta">${escapeHtml(m.channel || "")} · ${escapeHtml(m.duration || "")}</div>
  ${contentHtml}
  <script>window.onload=function(){window.focus();window.print();};<\/script>
  </body></html>`;
  const w = window.open("", "_blank", "noopener,noreferrer");
  if (!w) {
    alert("Pop-up blocked - allow pop-ups to save as PDF.");
    return;
  }
  w.document.write(html);
  w.document.close();
}

function downloadSummarySection(result, scope, fmt) {
  const info = sectionExportDescriptor(scope);
  const safe = safeExportBase(result?.metadata?.title || "summary", info.suffix);
  if (fmt === "md") {
    const md = buildSectionMarkdown(result, scope);
    downloadBlob(`${safe}_${info.suffix}.md`, new Blob([md], { type: "text/markdown;charset=utf-8" }));
  } else if (fmt === "docx") {
    downloadWord(result, scope);
  } else if (fmt === "pdf") {
    openPrintablePdf(result, scope);
  }
}

async function copyTranscriptText(result) {
  const text = transcriptLines(result).join("\n");
  if (!text) {
    alert("No transcript available.");
    return false;
  }
  try {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (error) {
    console.error("Clipboard API failed", error);
  }

  try {
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "readonly");
    area.style.position = "absolute";
    area.style.left = "-9999px";
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand("copy");
    document.body.removeChild(area);
    return !!copied;
  } catch (error) {
    console.error("execCommand copy failed", error);
    return false;
  }
}

/**
 * Export mindmap panel (SVG inside root) as PNG.
 */
function downloadMindmapPng(rootEl) {
  if (!rootEl) {
    alert("Mindmap not ready.");
    return;
  }
  let stored = rootEl.__mindmapExport || null;
  if ((!stored || !stored.svgMarkup || !stored.width || !stored.height) && rootEl.__mindmapSource && typeof window.buildMindmapExportMarkup === "function") {
    try {
      stored = window.buildMindmapExportMarkup(rootEl.__mindmapSource.data, rootEl.__mindmapSource.context);
      rootEl.__mindmapExport = stored;
    } catch (error) {
      console.error("Mindmap export rebuild failed", error);
    }
  }

  const svgMarkup = stored?.svgMarkup || "";
  const exportWidth = Math.max(1, Math.ceil(stored?.width || 0));
  const exportHeight = Math.max(1, Math.ceil(stored?.height || 0));

  let finalMarkup = svgMarkup;
  let finalWidth = exportWidth;
  let finalHeight = exportHeight;

  if ((!finalMarkup || !finalWidth || !finalHeight) && rootEl.querySelector) {
    const liveSvg = rootEl.querySelector("svg");
    if (liveSvg) {
      try {
        const clone = liveSvg.cloneNode(true);
        const liveViewBox = (clone.getAttribute("viewBox") || "").split(/\s+/).map(Number).filter(Number.isFinite);
        clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
        if (liveViewBox.length === 4) {
          finalWidth = Math.max(1, Math.ceil(liveViewBox[2]));
          finalHeight = Math.max(1, Math.ceil(liveViewBox[3]));
          clone.setAttribute("width", String(finalWidth));
          clone.setAttribute("height", String(finalHeight));
        } else {
          const rect = liveSvg.getBoundingClientRect();
          finalWidth = Math.max(1, Math.ceil(rect.width || 1));
          finalHeight = Math.max(1, Math.ceil(rect.height || 1));
          clone.setAttribute("width", String(finalWidth));
          clone.setAttribute("height", String(finalHeight));
          clone.setAttribute("viewBox", `0 0 ${finalWidth} ${finalHeight}`);
        }
        finalMarkup = new XMLSerializer().serializeToString(clone);
      } catch (error) {
        console.error("Live SVG export fallback failed", error);
      }
    }
  }

  if (!finalMarkup || !finalWidth || !finalHeight) {
    alert("Mindmap export is not ready yet.");
    return;
  }
  const img = new Image();
  const svgBlob = new Blob([finalMarkup], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(svgBlob);
  img.onload = () => {
    try {
      const canvas = document.createElement("canvas");
      canvas.width = finalWidth;
      canvas.height = finalHeight;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#0a0806";
      ctx.fillRect(0, 0, finalWidth, finalHeight);
      ctx.drawImage(img, 0, 0, finalWidth, finalHeight);
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
  buildMarkdown: (result) => buildSectionMarkdown(result, "full"),
  downloadWord,
  openPrintablePdf,
  downloadSummarySection,
  copyTranscriptText,
  downloadMindmapPng,
});
