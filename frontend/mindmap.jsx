/* Indented tree mindmap renderer with dedicated export markup. */

function mmTrim(value) {
  return String(value == null ? "" : value).replace(/\s+/g, " ").trim();
}

function mmLimitWords(value, maxWords, suffix = "...") {
  const text = mmTrim(value);
  if (!text) return "";
  const words = text.split(/\s+/);
  if (words.length <= maxWords) return text;
  return `${words.slice(0, maxWords).join(" ")}${suffix}`;
}

function mmSplitSentences(value) {
  const text = mmTrim(value);
  if (!text) return [];
  return text
    .split(/(?<=[.!?])\s+/)
    .map((part) => mmTrim(part))
    .filter(Boolean);
}

function mmWrapLines(value, maxChars, maxLines) {
  const words = mmTrim(value).split(/\s+/).filter(Boolean);
  if (!words.length) return [];
  const lines = [];
  let current = "";
  words.forEach((word) => {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length > maxChars && current) {
      lines.push(current);
      current = word;
    } else {
      current = candidate;
    }
  });
  if (current) lines.push(current);
  if (lines.length <= maxLines) return lines;
  const trimmed = lines.slice(0, maxLines);
  trimmed[maxLines - 1] = mmLimitWords(trimmed[maxLines - 1], Math.max(3, Math.floor(maxChars / 2)));
  return trimmed;
}

function mmCompactBranchTitle(value) {
  const cleaned = mmTrim(value).replace(/^[\-\u2022\d.\s:]+/, "");
  return mmLimitWords(cleaned || "Untitled", 7, "");
}

function mmCompactLeaf(value) {
  return mmLimitWords(value, 18);
}

function mmCollectSectionLeaves(section) {
  if (!section || typeof section !== "object") return [];
  const leaves = [];

  const description = mmCompactLeaf(section.desc || section.body || "");
  if (description) leaves.push(description);

  [section.steps, section.subPoints, section.tradeOffs].forEach((items) => {
    if (!Array.isArray(items)) return;
    items.forEach((item) => {
      const text = mmCompactLeaf(item);
      if (text) leaves.push(text);
    });
  });

  if (section.notable) {
    leaves.push(mmCompactLeaf(`Notable: ${section.notable}`));
  }

  return leaves.filter(Boolean).slice(0, 3);
}

function mmCollectNodeLeaves(node) {
  if (node == null) return [];
  if (typeof node === "string") {
    return mmSplitSentences(node).map(mmCompactLeaf).slice(0, 3);
  }
  if (typeof node !== "object") return [];

  if (Array.isArray(node.children) && node.children.length) {
    return node.children
      .map((child) => (typeof child === "object" ? (child.name ?? child.label ?? "") : child))
      .map(mmCompactLeaf)
      .filter(Boolean)
      .slice(0, 3);
  }

  const raw = mmTrim(node.name ?? node.label ?? "");
  return mmSplitSentences(raw).map(mmCompactLeaf).slice(0, 3);
}

function buildRenderableMindmap(data, context) {
  const rootLabel = mmLimitWords(
    data?.name || data?.label || context?.metadata?.title || "Video Summary",
    10,
    ""
  );

  const sections = Array.isArray(context?.sections) ? context.sections : [];
  if (sections.length) {
    return {
      label: rootLabel,
      branches: sections.slice(0, 6).map((section) => ({
        label: mmCompactBranchTitle(section.title || section.time || "Section"),
        leaves: mmCollectSectionLeaves(section),
      })),
    };
  }

  const rawChildren = Array.isArray(data?.children)
    ? data.children
    : Array.isArray(data?.nodes)
      ? data.nodes
      : [];

  return {
    label: rootLabel,
    branches: rawChildren.slice(0, 6).map((node) => ({
      label: mmCompactBranchTitle(node?.name ?? node?.label ?? node),
      leaves: mmCollectNodeLeaves(node),
    })),
  };
}

function measureTextBlock(text, maxChars, maxLines, lineHeight, padY) {
  const lines = mmWrapLines(text, maxChars, maxLines);
  return {
    lines,
    height: Math.max(lineHeight + padY * 2, padY * 2 + lines.length * lineHeight),
  };
}

function buildMindmapScene(input) {
  const layout = {
    padX: 56,
    padY: 56,
    rootW: 360,
    rootH: 86,
    branchW: 288,
    branchH: 52,
    leafW: 320,
    leafIndent: 74,
    leafPadX: 18,
    leafPadY: 12,
    leafLineH: 18,
    branchPadX: 18,
    branchPadY: 12,
    branchLineH: 19,
    branchToLeafGap: 12,
    rowGap: 10,
    branchGap: 20,
    rootGap: 52,
  };

  const root = measureTextBlock(input?.label || "Video Summary", 28, 3, 26, 14);
  const left = [];
  const right = [];
  (Array.isArray(input?.branches) ? input.branches : []).forEach((branch, index) => {
    ((index % 2 === 0) ? right : left).push(branch);
  });

  const makeBlock = (branch) => {
    const branchText = measureTextBlock(branch.label || "Section", 28, 2, layout.branchLineH, layout.branchPadY);
    const leafNodes = (Array.isArray(branch.leaves) ? branch.leaves : [])
      .filter(Boolean)
      .slice(0, 2)
      .map((leaf) => {
        const measured = measureTextBlock(leaf, 38, 3, layout.leafLineH, layout.leafPadY);
        return {
          text: leaf,
          lines: measured.lines,
          width: layout.leafW,
          height: measured.height,
        };
      });

    const leafHeight = leafNodes.reduce((sum, leaf) => sum + leaf.height, 0) + Math.max(0, leafNodes.length - 1) * layout.rowGap;
    return {
      label: branch.label,
      lines: branchText.lines,
      width: layout.branchW,
      height: Math.max(layout.branchH, branchText.height),
      leaves: leafNodes,
      leafHeight,
    };
  };

  const leftBlocks = left.map(makeBlock);
  const rightBlocks = right.map(makeBlock);
  const sideTotalHeight = (blocks) => blocks.reduce((sum, block) => sum + block.height + (block.leaves.length ? layout.branchToLeafGap + block.leafHeight : 0), 0) + Math.max(0, (blocks.length - 1) * layout.branchGap);
  const contentHeight = Math.max(sideTotalHeight(leftBlocks), sideTotalHeight(rightBlocks), root.height);
  const sceneHeight = contentHeight + layout.padY * 2;
  const rootY = sceneHeight / 2 - root.height / 2;
  const rootX = layout.padX + layout.leafW + layout.leafIndent + layout.branchW + layout.rootGap;
  const sceneWidth = rootX + layout.rootW + layout.rootGap + layout.branchW + layout.leafIndent + layout.leafW + layout.padX;
  const rootNode = {
    x: rootX,
    y: rootY,
    width: layout.rootW,
    height: root.height,
    lines: root.lines,
  };

  return {
    width: sceneWidth,
    height: Math.max(sceneHeight, 540),
    root: rootNode,
    left: leftBlocks,
    right: rightBlocks,
    layout,
  };
}

function mindmapPalette() {
  const root = typeof document !== "undefined" ? getComputedStyle(document.body) : null;
  const accent = (root?.getPropertyValue("--led-amber") || "#ff7a1a").trim();
  return {
    bg: "#0f0b08",
    bg2: "#1a140f",
    grid: "rgba(255,255,255,0.03)",
    accent,
    accentSoft: "rgba(255,122,26,0.38)",
    accentGlow: "rgba(255,122,26,0.22)",
    rootFillA: "#3c160e",
    rootFillB: "#24100a",
    rootStroke: "rgba(255,155,100,0.92)",
    branchFill: "#201610",
    branchStroke: "rgba(255,122,26,0.72)",
    leafFill: "#2a1f17",
    leafStroke: "rgba(255,255,255,0.08)",
    text: "#f7efe7",
    muted: "#e0cfc0",
    connector: "rgba(255,122,26,0.82)",
  };
}

function renderSceneIntoSvg(svgNode, scene, options = {}) {
  const palette = mindmapPalette();
  const layout = scene.layout || {};
  const svg = d3.select(svgNode);
  svg.selectAll("*").remove();

  const viewportWidth = options.viewportWidth || scene.width;
  const viewportHeight = options.viewportHeight || scene.height;
  const interactive = options.interactive !== false;

  svg
    .attr("viewBox", `0 0 ${viewportWidth} ${viewportHeight}`)
    .attr("width", options.width || "100%")
    .attr("height", options.height || "100%")
    .attr("preserveAspectRatio", "xMidYMid meet");

  const defs = svg.append("defs");
  const bg = defs.append("linearGradient").attr("id", options.bgId || "mm-bg").attr("x1", "0%").attr("y1", "0%").attr("x2", "100%").attr("y2", "100%");
  bg.append("stop").attr("offset", "0%").attr("stop-color", palette.bg);
  bg.append("stop").attr("offset", "100%").attr("stop-color", palette.bg2);

  const rootGrad = defs.append("linearGradient").attr("id", options.rootId || "mm-root").attr("x1", "0%").attr("y1", "0%").attr("x2", "100%").attr("y2", "0%");
  rootGrad.append("stop").attr("offset", "0%").attr("stop-color", palette.rootFillA);
  rootGrad.append("stop").attr("offset", "100%").attr("stop-color", palette.rootFillB);

  svg.append("rect")
    .attr("width", viewportWidth)
    .attr("height", viewportHeight)
    .attr("fill", `url(#${options.bgId || "mm-bg"})`);

  const grid = svg.append("g");
  for (let x = 0; x < viewportWidth; x += 44) {
    grid.append("line")
      .attr("x1", x)
      .attr("y1", 0)
      .attr("x2", x)
      .attr("y2", viewportHeight)
      .attr("stroke", palette.grid)
      .attr("stroke-width", 1);
  }
  for (let y = 0; y < viewportHeight; y += 44) {
    grid.append("line")
      .attr("x1", 0)
      .attr("y1", y)
      .attr("x2", viewportWidth)
      .attr("y2", y)
      .attr("stroke", palette.grid)
      .attr("stroke-width", 1);
  }

  const viewport = svg.append("g").attr("class", "mindmap-viewport");
  const sceneGroup = viewport.append("g").attr("class", "mindmap-scene");

  const addPath = (points) => {
    const line = d3.line().x((point) => point[0]).y((point) => point[1]).curve(d3.curveStepAfter);
    sceneGroup.append("path")
      .attr("d", line(points))
      .attr("fill", "none")
      .attr("stroke", palette.connector)
      .attr("stroke-width", 2.2)
      .attr("stroke-linecap", "round")
      .attr("stroke-linejoin", "round");
  };

  const addTextBlock = (node, lines, style) => {
    lines.forEach((line, index) => {
      sceneGroup.append("text")
        .attr("x", node.x + style.padX)
        .attr("y", node.y + style.padY + style.lineHeight + index * style.lineHeight)
        .attr("fill", style.color)
        .attr("font-family", "Inter, Helvetica, sans-serif")
        .attr("font-size", style.fontSize)
        .attr("font-weight", style.fontWeight || 500)
        .text(line);
    });
  };

  sceneGroup.append("rect")
    .attr("x", scene.root.x)
    .attr("y", scene.root.y)
    .attr("width", scene.root.width)
    .attr("height", scene.root.height)
    .attr("rx", 20)
    .attr("fill", `url(#${options.rootId || "mm-root"})`)
    .attr("stroke", palette.rootStroke)
    .attr("stroke-width", 1.8);

  addTextBlock(scene.root, scene.root.lines, {
    padX: 24,
    padY: 8,
    lineHeight: 26,
    fontSize: 19,
    fontWeight: 700,
    color: palette.text,
  });

  const renderSide = (blocks, side) => {
    const isLeft = side === "left";
    const branchX = isLeft
      ? scene.root.x - (layout.rootGap || 52) - (layout.branchW || 288)
      : scene.root.x + scene.root.width + (layout.rootGap || 52);
    const leafX = isLeft
      ? branchX - (layout.leafIndent || 74) - (layout.leafW || 320)
      : branchX + (layout.branchW || 288) + (layout.leafIndent || 74);
    const branchRootX = isLeft ? branchX + (layout.branchW || 288) : branchX;
    const branchLeafX = isLeft ? branchX : branchX + (layout.branchW || 288);
    const leafAnchorX = isLeft ? leafX + (layout.leafW || 320) : leafX;
    const total = blocks.reduce((sum, block) => sum + block.height + (block.leaves.length ? (layout.branchToLeafGap || 12) + block.leafHeight : 0), 0) + Math.max(0, (blocks.length - 1) * (layout.branchGap || 20));
    let cursorY = scene.root.y + scene.root.height / 2 - total / 2;

    blocks.forEach((block) => {
      const branchMidY = cursorY + block.height / 2;
      const rootEdgeX = isLeft ? scene.root.x : scene.root.x + scene.root.width;
      addPath([
        [rootEdgeX, scene.root.y + scene.root.height / 2],
        [rootEdgeX + (isLeft ? -28 : 28), scene.root.y + scene.root.height / 2],
        [rootEdgeX + (isLeft ? -28 : 28), branchMidY],
        [branchRootX, branchMidY],
      ]);

      sceneGroup.append("rect")
        .attr("x", branchX)
        .attr("y", cursorY)
        .attr("width", layout.branchW)
        .attr("height", block.height)
        .attr("rx", 16)
        .attr("fill", palette.branchFill)
        .attr("stroke", palette.branchStroke)
        .attr("stroke-width", 1.6);

      sceneGroup.append("circle")
        .attr("cx", isLeft ? branchX + layout.branchW - 14 : branchX + 14)
        .attr("cy", branchMidY)
        .attr("r", 4.5)
        .attr("fill", palette.accent);

      addTextBlock({ x: branchX, y: cursorY }, block.lines, {
        padX: 22,
        padY: 8,
        lineHeight: 19,
        fontSize: 12.5,
        fontWeight: 700,
        color: palette.text,
      });

      let leafY = cursorY + block.height + layout.branchToLeafGap;
      block.leaves.forEach((leaf) => {
        const leafMidY = leafY + leaf.height / 2;
        addPath([
          [branchLeafX, branchMidY],
          [branchLeafX + (isLeft ? -18 : 18), branchMidY],
          [branchLeafX + (isLeft ? -18 : 18), leafMidY],
          [leafAnchorX, leafMidY],
        ]);

        sceneGroup.append("rect")
          .attr("x", leafX)
          .attr("y", leafY)
          .attr("width", layout.leafW)
          .attr("height", leaf.height)
          .attr("rx", 14)
          .attr("fill", palette.leafFill)
          .attr("stroke", palette.leafStroke)
          .attr("stroke-width", 1);

        addTextBlock({ x: leafX, y: leafY }, leaf.lines, {
          padX: 16,
          padY: 8,
          lineHeight: 18,
          fontSize: 12,
          color: palette.muted,
        });

        leafY += leaf.height + layout.rowGap;
      });

        cursorY += block.height + (block.leaves.length ? (layout.branchToLeafGap || 12) + block.leafHeight : 0) + (layout.branchGap || 20);
      });
  };

  renderSide(scene.left || [], "left");
  renderSide(scene.right || [], "right");

  if (interactive) {
    const zoom = d3.zoom().scaleExtent([0.55, 2.25]).on("zoom", (event) => {
      viewport.attr("transform", event.transform);
    });
    svg.call(zoom);

    const pad = 28;
    const scale = Math.min(
      1,
      (viewportWidth - pad * 2) / scene.width,
      (viewportHeight - pad * 2) / scene.height
    );
    const tx = (viewportWidth - scene.width * scale) / 2;
    const ty = (viewportHeight - scene.height * scale) / 2;
    const initialTransform = d3.zoomIdentity.translate(tx, ty).scale(scale);
    svg.call(zoom.transform, initialTransform);
    return { svg, zoom, initialTransform };
  }

  return { svg: null, zoom: null, initialTransform: null };
}

function buildMindmapExportMarkup(data, context) {
  const rendered = buildRenderableMindmap(data, context);
  const scene = buildMindmapScene(rendered);
  const ns = "http://www.w3.org/2000/svg";
  const tempSvg = document.createElementNS(ns, "svg");
  renderSceneIntoSvg(tempSvg, scene, {
    interactive: false,
    viewportWidth: scene.width,
    viewportHeight: scene.height,
    width: String(scene.width),
    height: String(scene.height),
    bgId: "mm-bg-export",
    rootId: "mm-root-export",
  });
  tempSvg.setAttribute("xmlns", ns);
  tempSvg.setAttribute("width", String(scene.width));
  tempSvg.setAttribute("height", String(scene.height));
  tempSvg.setAttribute("viewBox", `0 0 ${scene.width} ${scene.height}`);
  return {
    svgMarkup: new XMLSerializer().serializeToString(tempSvg),
    width: scene.width,
    height: scene.height,
  };
}

const Mindmap = ({ data, context }) => {
  const ref = React.useRef(null);
  const wrapRef = React.useRef(null);
  const zoomRef = React.useRef(null);

  React.useEffect(() => {
    if (!data || !ref.current || !wrapRef.current) return;

    let raf = 0;
    const paint = () => {
      try {
        const viewport = wrapRef.current.getBoundingClientRect();
        const isNarrow = window.matchMedia && window.matchMedia("(max-width: 640px)").matches;
        const targetWidth = Math.ceil(viewport.width);
        const targetHeight = Math.ceil(viewport.height);
        const rendered = buildRenderableMindmap(data, context);
        const scene = buildMindmapScene(rendered);
        const renderedView = renderSceneIntoSvg(ref.current, scene, {
          interactive: true,
          viewportWidth: Math.max(isNarrow ? 320 : 980, targetWidth),
          viewportHeight: Math.max(isNarrow ? 320 : 560, targetHeight),
        });

        const exportPayload = buildMindmapExportMarkup(data, context);
        wrapRef.current.__mindmapSource = { data, context };
        wrapRef.current.__mindmapExport = exportPayload;
        zoomRef.current = {
          svg: renderedView.svg,
          zoom: renderedView.zoom,
          initialTransform: renderedView.initialTransform,
          branchCount: rendered.branches.length,
        };
      } catch (error) {
        console.error("Mindmap layout failed", error);
        wrapRef.current.__mindmapSource = { data, context };
        wrapRef.current.__mindmapExport = null;
      }
    };

    const schedulePaint = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(paint);
    };

    schedulePaint();

    const ResizeObserverCtor = window.ResizeObserver;
    const observer = ResizeObserverCtor ? new ResizeObserverCtor(() => schedulePaint()) : null;
    if (observer) observer.observe(wrapRef.current);

    return () => {
      cancelAnimationFrame(raf);
      if (observer) observer.disconnect();
    };
  }, [data, context]);

  const reset = () => zoomRef.current?.svg?.transition().duration(300)
    .call(zoomRef.current.zoom.transform, zoomRef.current.initialTransform || d3.zoomIdentity);
  const zoomIn = () => zoomRef.current?.svg?.transition().call(zoomRef.current.zoom.scaleBy, 1.2);
  const zoomOut = () => zoomRef.current?.svg?.transition().call(zoomRef.current.zoom.scaleBy, 0.84);
  const branchCount = Array.isArray(context?.sections) && context.sections.length
    ? Math.min(context.sections.length, 6)
    : Array.isArray(data?.children)
      ? Math.min(data.children.length, 6)
      : 0;

  return (
    <div className="mindmap-wrap" id="mindmap-export-root" ref={wrapRef}>
      <svg ref={ref} />
      <div className="map-controls">
        <button className="map-ctrl" onClick={zoomIn} title="Zoom in">+</button>
        <button className="map-ctrl" onClick={zoomOut} title="Zoom out">-</button>
        <button className="map-ctrl" onClick={reset} title="Reset">R</button>
      </div>
      <div className="map-legend">DRAG TO PAN · SCROLL TO ZOOM · {branchCount} SECTIONS</div>
    </div>
  );
};

Object.assign(window, {
  Mindmap,
  buildMindmapExportMarkup,
});
