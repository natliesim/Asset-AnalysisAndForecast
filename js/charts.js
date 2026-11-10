// Tiny SVG line charts — no libraries.
const Charts = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const el = (tag, attrs = {}) => {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  };
  const fmtDate = (s) => new Date(s + "T00:00:00").toLocaleDateString(undefined, { month: "short", year: "2-digit" });

  function spark(points, color = "#9a9a95") {
    const w = 220, h = 46, v = points.map((p) => p[1]);
    const lo = Math.min(...v), hi = Math.max(...v);
    const x = (i) => (i / (v.length - 1)) * w, y = (n) => h - 3 - ((n - lo) / (hi - lo || 1)) * (h - 6);
    const svg = el("svg", { viewBox: `0 0 ${w} ${h}`, class: "chart", preserveAspectRatio: "none" });
    svg.appendChild(el("path", { d: v.map((n, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(n).toFixed(1)}`).join(""), fill: "none", stroke: color, "stroke-width": 1.4, "vector-effect": "non-scaling-stroke" }));
    return svg;
  }

  // series: [{points:[[date,val]], color, width, dash, name}], band: [[date,lo,hi]]
  function line(target, { series, band = null, width = 600, height = 200, format = (n) => n.toFixed(2), tip = null, marker = null, zero = false, fixed = null }) {
    const W = width, H = height, pad = { l: 8, r: 52, t: 10, b: 22 };
    const dates = [...new Set(series.flatMap((s) => s.points.map((p) => p[0])).concat(band ? band.map((b) => b[0]) : []))].sort();
    const idx = new Map(dates.map((d, i) => [d, i]));
    const vals = series.flatMap((s) => s.points.map((p) => p[1])).concat(band ? band.flatMap((b) => [b[1], b[2]]) : []);
    let lo = Math.min(...vals), hi = Math.max(...vals);
    const span = hi - lo || 1; lo -= span * 0.06; hi += span * 0.06;
    if (fixed) [lo, hi] = fixed;
    const x = (d) => pad.l + (idx.get(d) / (dates.length - 1)) * (W - pad.l - pad.r);
    const y = (n) => pad.t + (1 - (n - lo) / (hi - lo)) * (H - pad.t - pad.b);

    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, class: "chart" });
    // grid + y labels
    for (let i = 0; i <= 3; i++) {
      const v = lo + ((hi - lo) * i) / 3, yy = y(v);
      svg.appendChild(el("line", { x1: pad.l, x2: W - pad.r, y1: yy, y2: yy, stroke: "#f0f0ed" }));
      const t = el("text", { x: W - pad.r + 6, y: yy + 3 }); t.textContent = format(v); svg.appendChild(t);
    }
    // x labels
    for (let i = 0; i < 4; i++) {
      const d = dates[Math.round((i / 3) * (dates.length - 1))];
      const t = el("text", { x: x(d), y: H - 6, "text-anchor": i === 0 ? "start" : i === 3 ? "end" : "middle" });
      t.textContent = fmtDate(d); svg.appendChild(t);
    }
    if (zero && lo < 0 && hi > 0) svg.appendChild(el("line", { x1: pad.l, x2: W - pad.r, y1: y(0), y2: y(0), stroke: "#cfcfca" }));
    if (marker) svg.appendChild(el("line", { x1: x(marker), x2: x(marker), y1: pad.t, y2: H - pad.b, stroke: "#e2e2de", "stroke-dasharray": "3 3" }));
    if (band) {
      const top = band.map((b) => `${x(b[0])},${y(b[2])}`), bot = band.map((b) => `${x(b[0])},${y(b[1])}`).reverse();
      svg.appendChild(el("polygon", { points: top.concat(bot).join(" "), fill: "#c96442", opacity: 0.08 }));
    }
    for (const s of series) {
      svg.appendChild(el("path", {
        d: s.points.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(""),
        fill: "none", stroke: s.color, "stroke-width": s.width || 1.6, "stroke-dasharray": s.dash || "", "stroke-linejoin": "round",
      }));
    }
    // hover
    const guide = el("line", { y1: pad.t, y2: H - pad.b, stroke: "#d0d0cb", visibility: "hidden" });
    svg.appendChild(guide);
    const lookups = series.map((s) => new Map(s.points.map((p) => [p[0], p.length > 2 ? p[2] : p[1]])));
    const move = (ev) => {
      const r = svg.getBoundingClientRect();
      const px = ((ev.touches ? ev.touches[0].clientX : ev.clientX) - r.left) * (W / r.width);
      const i = Math.max(0, Math.min(dates.length - 1, Math.round(((px - pad.l) / (W - pad.l - pad.r)) * (dates.length - 1))));
      const d = dates[i];
      guide.setAttribute("x1", x(d)); guide.setAttribute("x2", x(d)); guide.setAttribute("visibility", "visible");
      if (tip) {
        const parts = series.map((s, k) => (lookups[k].has(d) ? `${s.name}: ${(s.format || format)(lookups[k].get(d))}` : null)).filter(Boolean);
        tip.textContent = `${new Date(d + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })} · ${parts.join(" · ")}`;
      }
    };
    svg.addEventListener("mousemove", move);
    svg.addEventListener("touchmove", move, { passive: true });
    svg.addEventListener("mouseleave", () => { guide.setAttribute("visibility", "hidden"); if (tip) tip.textContent = ""; });
    target.replaceChildren(svg);
  }

  return { spark, line };
})();
