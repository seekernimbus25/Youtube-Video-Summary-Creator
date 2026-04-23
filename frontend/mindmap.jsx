/* Horizontal mind-map tree — matches reference: center root, left/right branches, leaf cards */

const Mindmap = ({ data }) => {
  const ref = React.useRef(null);
  const wrapRef = React.useRef(null);
  const zoomRef = React.useRef(null);

  React.useEffect(() => {
    if (!data || !ref.current || !wrapRef.current) return;
    try {
    const svg = d3.select(ref.current);
    svg.selectAll("*").remove();

    const getLabel = (n) => {
      if (n == null) return "";
      if (typeof n === "string") return n;
      if (typeof n === "object" && (n.name != null || n.label != null)) {
        return String(n.name != null ? n.name : n.label);
      }
      return "";
    };
    const rootLabel = getLabel(data) || "TOPIC";

    const bbox = wrapRef.current.getBoundingClientRect();
    const W = Math.max(900, bbox.width);
    const H = Math.max(460, bbox.height);
    svg.attr("viewBox", `0 0 ${W} ${H}`).attr("width", "100%").attr("height", "100%")
       .attr("preserveAspectRatio", "xMidYMid meet");

    // background — warm dark ink matching the inset panel aesthetic
    const defs = svg.append("defs");
    const bgGrad = defs.append("radialGradient").attr("id","mmBg").attr("cx","50%").attr("cy","50%").attr("r","75%");
    bgGrad.append("stop").attr("offset","0%").attr("stop-color","#1a1610");
    bgGrad.append("stop").attr("offset","100%").attr("stop-color","#0a0806");
    svg.append("rect").attr("width", W).attr("height", H).attr("fill","url(#mmBg)");

    // faint horizontal scan lines echo the grill texture
    const scanPat = defs.append("pattern").attr("id","scan").attr("width", 4).attr("height", 4).attr("patternUnits","userSpaceOnUse");
    scanPat.append("rect").attr("width", 4).attr("height", 4).attr("fill","transparent");
    scanPat.append("line").attr("x1",0).attr("x2",4).attr("y1",0).attr("y2",0).attr("stroke","rgba(255,255,255,.025)");
    svg.append("rect").attr("width", W).attr("height", H).attr("fill","url(#scan)");

    const ledColor = (getComputedStyle(document.body).getPropertyValue("--led-amber") || "#ff7a1a").trim();
    const ledGlow  = (getComputedStyle(document.body).getPropertyValue("--led-amber-glow") || "#ffbf6a").trim();
    // Use amber/led-tinted palette to match faceplate accents
    const branchColor = ledColor;
    const branchTextColor = "#f4ead3";     // ivory, matches faceplate highlight
    const leafBg = "#221d15";              // warm dark card, sits on black ink
    const leafStroke = "rgba(255,180,100,0.22)";
    const leafText = "#e8dec6";            // ivory body text

    const g = svg.append("g");

    const rawTop = (data && (data.children != null ? data.children : data.nodes)) || [];
    const children = Array.isArray(rawTop) ? rawTop.slice() : [];
    // alternate: even idx → right, odd → left — keeps balance visually like reference
    const right = [], left = [];
    children.forEach((c, i) => (i % 2 === 0 ? right : left).push(c));

    // sizes
    const rootW = Math.min(260, Math.max(180, (rootLabel.length * 10) + 40));
    const rootH = 54;
    const rootX = W / 2;
    const rootY = H / 2;

    const branchPillH = 40;
    const branchPillPadX = 18;
    const leafCardPadX = 14;
    const leafCardPadY = 10;
    const leafLineH = 15;
    const leafCardW = 220;
    const leafGap = 10;
    const branchGap = 28;

    // measure branch pill width by text length (before drawSide; avoids TDZ / ordering surprises)
    const measureBranchWidth = (text) => {
      const t = (text == null) ? "" : String(text);
      return Math.min(240, Math.max(120, t.length * 8.2 + branchPillPadX * 2 + 26));
    };

    // compute leaf card heights by wrapping text
    const wrap = (text, maxChars = 34) => {
      const s = (text == null) ? "" : String(text);
      const words = s.split(/\s+/);
      const lines = [];
      let line = "";
      words.forEach(w => {
        if ((line + " " + w).trim().length > maxChars) { lines.push(line.trim()); line = w; }
        else line = (line + " " + w).trim();
      });
      if (line) lines.push(line);
      return lines;
    };

    // Layout one side — compute y positions for branches and leaves
    const layoutSide = (branches, sideSign) => {
      // for each branch: compute total block height = max(branchPillH, leaves height)
      const blocks = branches.map(branch => {
        const leaves = (branch.children || []);
        const leafBlocks = leaves.map(l => {
          const lines = wrap(getLabel(l), 30);
          const h = leafCardPadY * 2 + lines.length * leafLineH;
          return { node: l, lines, h };
        });
        const leafTotal = leafBlocks.reduce((s, lb) => s + lb.h, 0) + Math.max(0, (leafBlocks.length - 1) * leafGap);
        return {
          node: branch,
          leafBlocks,
          leafTotal,
          height: Math.max(branchPillH + 20, leafTotal),
        };
      });
      const total = blocks.reduce((s, b) => s + b.height, 0) + Math.max(0, (blocks.length - 1) * branchGap);
      let y = rootY - total / 2;
      blocks.forEach(b => {
        b.yStart = y;
        b.yCenter = y + b.height / 2;
        // position each leaf inside the block, vertically centered on the branch block
        let ly = b.yCenter - b.leafTotal / 2;
        b.leafBlocks.forEach(lb => {
          lb.yStart = ly;
          lb.yCenter = ly + lb.h / 2;
          ly += lb.h + leafGap;
        });
        y += b.height + branchGap;
      });
      // assign x positions
      const branchX = rootX + sideSign * 170;   // distance from root to branch center
      const leafX   = rootX + sideSign * 380;   // distance from root to inner edge of leaf card
      blocks.forEach(b => {
        b.x = branchX;
        b.leafBlocks.forEach(lb => { lb.x = leafX; });
      });
      return blocks;
    };

    const rightBlocks = layoutSide(right, +1);
    const leftBlocks  = layoutSide(left,  -1);

    // ---- draw links first (so they sit under nodes) ----
    const linkG = g.append("g").attr("fill","none").attr("stroke", branchColor).attr("stroke-opacity", 0.55).attr("stroke-width", 1.4).attr("stroke-linecap","round");

    const curve = (x1, y1, x2, y2) => {
      const mx = (x1 + x2) / 2;
      return `M ${x1},${y1} C ${mx},${y1} ${mx},${y2} ${x2},${y2}`;
    };

    const drawSide = (blocks, sideSign) => {
      blocks.forEach(b => {
        // root → branch
        const rx = rootX + sideSign * (rootW / 2);
        const bl = getLabel(b.node);
        const bx = b.x - sideSign * (measureBranchWidth(bl) / 2);
        linkG.append("path").attr("d", curve(rx, rootY, bx, b.yCenter));

        // branch → each leaf
        b.leafBlocks.forEach(lb => {
          const bx2 = b.x + sideSign * (measureBranchWidth(bl) / 2);
          const lx = lb.x - sideSign * 0; // leaf card inner edge
          // actually, leaf card spans from lb.x to lb.x + sideSign*leafCardW
          const leafInnerX = sideSign > 0 ? lb.x : lb.x;
          linkG.append("path")
            .attr("stroke", branchColor)
            .attr("stroke-opacity", 0.32)
            .attr("d", curve(bx2, b.yCenter, leafInnerX, lb.yCenter));
        });
      });
    };

    drawSide(rightBlocks, +1);
    drawSide(leftBlocks,  -1);

    // ---- draw root pill — glowing LED button, matches DISTILL aesthetic ----
    const rootGroup = g.append("g");
    rootGroup.append("rect")
      .attr("x", rootX - rootW / 2)
      .attr("y", rootY - rootH / 2)
      .attr("width", rootW)
      .attr("height", rootH)
      .attr("rx", rootH / 2)
      .attr("fill", ledColor)
      .attr("stroke", "#2b1605")
      .attr("stroke-width", 1.6)
      .attr("filter", "drop-shadow(0 0 14px " + ledGlow + ")");
    // subtle top highlight sheen
    rootGroup.append("rect")
      .attr("x", rootX - rootW / 2 + 3)
      .attr("y", rootY - rootH / 2 + 2)
      .attr("width", rootW - 6)
      .attr("height", 10)
      .attr("rx", 6)
      .attr("fill", "rgba(255,255,255,0.25)");
    rootGroup.append("text")
      .attr("x", rootX).attr("y", rootY)
      .attr("text-anchor","middle").attr("dy","0.35em")
      .attr("fill", "#ffffff")
      .attr("font-family","Unica One, Helvetica, sans-serif")
      .attr("font-weight", 400)
      .attr("font-size", 17)
      .attr("letter-spacing","0.1em")
      .text(rootLabel.toUpperCase());

    // ---- draw branch pills ----
    const drawBranches = (blocks, sideSign) => {
      blocks.forEach(b => {
        const btext = getLabel(b.node) || "·";
        const bw = measureBranchWidth(btext);
        const bh = branchPillH;
        const bx = b.x - bw / 2;
        const by = b.yCenter - bh / 2;

        // pill — warm dark with amber accent, like a recessed LED label
        const gr = g.append("g").style("cursor","pointer");
        gr.append("rect")
          .attr("x", bx).attr("y", by)
          .attr("width", bw).attr("height", bh)
          .attr("rx", bh / 2)
          .attr("fill", "#15110b")
          .attr("stroke", branchColor)
          .attr("stroke-opacity", 0.85)
          .attr("stroke-width", 1.4);

        // LED indicator dot on the pill
        gr.append("circle")
          .attr("cx", bx + 18).attr("cy", b.yCenter).attr("r", 5)
          .attr("fill", ledColor)
          .attr("filter", "drop-shadow(0 0 4px " + ledGlow + ")");

        gr.append("text")
          .attr("x", bx + 32).attr("y", b.yCenter)
          .attr("dy","0.35em")
          .attr("fill", branchTextColor)
          .attr("font-family","JetBrains Mono, ui-monospace, monospace")
          .attr("font-weight", 600)
          .attr("font-size", 11)
          .attr("letter-spacing","0.1em")
          .attr("text-transform","uppercase")
          .text(btext.toUpperCase());

        // leaves
        b.leafBlocks.forEach(lb => {
          const cardX = sideSign > 0 ? lb.x : lb.x - leafCardW;
          const cardY = lb.yStart;
          const gl = g.append("g");
          gl.append("rect")
            .attr("x", cardX).attr("y", cardY)
            .attr("width", leafCardW).attr("height", lb.h)
            .attr("rx", 6)
            .attr("fill", leafBg)
            .attr("stroke", leafStroke)
            .attr("stroke-width", 1);
          // thin amber left-edge accent, like the LED side-bar
          gl.append("rect")
            .attr("x", sideSign > 0 ? cardX : cardX + leafCardW - 2)
            .attr("y", cardY + 6)
            .attr("width", 2)
            .attr("height", lb.h - 12)
            .attr("fill", ledColor).attr("opacity", 0.7);

          const tx = cardX + leafCardPadX;
          lb.lines.forEach((ln, i) => {
            gl.append("text")
              .attr("x", tx)
              .attr("y", cardY + leafCardPadY + (i + 1) * leafLineH - 4)
              .attr("fill", leafText)
              .attr("font-family","Inter, Helvetica, sans-serif")
              .attr("font-size", 11)
              .attr("letter-spacing","0.01em")
              .text(ln);
          });
        });
      });
    };

    drawBranches(rightBlocks, +1);
    drawBranches(leftBlocks, -1);

    // ---- zoom ----
    const zoom = d3.zoom().scaleExtent([0.45, 2.5])
      .on("zoom", (e) => g.attr("transform", e.transform));
    svg.call(zoom);
    zoomRef.current = { svg, zoom };
    } catch (err) {
      console.error("Mindmap layout failed", err);
    }
  }, [data]);

  const reset = () => zoomRef.current?.svg.transition().duration(350)
    .call(zoomRef.current.zoom.transform, d3.zoomIdentity);
  const zoomIn  = () => zoomRef.current?.svg.transition().call(zoomRef.current.zoom.scaleBy, 1.3);
  const zoomOut = () => zoomRef.current?.svg.transition().call(zoomRef.current.zoom.scaleBy, 0.77);

  return (
    <div className="mindmap-wrap" id="mindmap-export-root" ref={wrapRef}>
      <svg ref={ref} />
      <div className="map-controls">
        <button className="map-ctrl" onClick={zoomIn} title="Zoom in">+</button>
        <button className="map-ctrl" onClick={zoomOut} title="Zoom out">−</button>
        <button className="map-ctrl" onClick={reset} title="Reset">⟲</button>
      </div>
      <div className="map-legend">◦ DRAG TO PAN · SCROLL TO ZOOM · {data?.children?.length ?? 0} BRANCHES</div>
    </div>
  );
};

Object.assign(window, { Mindmap });
