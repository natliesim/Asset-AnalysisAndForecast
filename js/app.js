(() => {
  const DATA = window.ASSET_DATA;
  const view = document.getElementById("view");
  const rail = document.getElementById("rail");
  const byId = Object.fromEntries(DATA.assets.map((a) => [a.id, a]));

  const money = (n) => "$" + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: n < 10 ? 3 : 2 });
  const pct = (n, d = 1) => `${n >= 0 ? "+" : "−"}${Math.abs(n * 100).toFixed(d)}%`;
  const signed = (n, d = 2) => `${n >= 0 ? "+" : "−"}${Math.abs(n).toFixed(d)}`;
  const h = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content; };
  const tone = (label) => (/reliable/i.test(label) ? "" : /bullish/i.test(label) ? "bull" : /bearish/i.test(label) ? "bear" : "");
  const fmtD = (s) => new Date(s + "T00:00:00").toLocaleDateString(undefined, { month: "short", year: "numeric" });
  const HZ = { 5: "1 week", 20: "1 month", 60: "3 months" };
  const scoreWord = (n) => (n >= 70 ? "Strong" : n >= 58 ? "Some skill" : n >= 45 ? "Close to guessing" : "Worse than guessing");
  const corrWord = (c) => { const a = Math.abs(c); return a < 0.1 ? "none" : a < 0.25 ? "weak" : a < 0.5 ? "moderate" : "strong"; };
  const banner = DATA.sample
    ? `<div class="banner">Showing simulated sample data. Run <code>python model/train.py</code> to load live market prices.</div>`
    : "";

  function renderRail(active) {
    rail.replaceChildren(h(`
      <a href="#" class="home ${active ? "" : "active"}" title="Overview"><span class="sq">◇</span>Home</a>
      ${DATA.assets.map((a) => `<a href="#${a.id}" class="${a.id === active ? "active" : ""}"><span class="sq">${a.symbol}</span>${a.name}</a>`).join("")}
    `));
  }

  function renderHome() {
    view.replaceChildren(h(`
      ${banner}
      <section class="hero">
        <h1>Prediction Modelling <span style="color:var(--text-faint)">(Assets)</span></h1>
        <p>Machine learning built to forecast the future of your assets. Every
        forecast is transparent and explainable, broken down by the factors that move each market.</p>
      </section>
      <div class="grid">
        ${DATA.assets.map((a) => `
          <a class="card" href="#${a.id}">
            <div class="row"><h3>${a.name}</h3><span class="label">${a.symbol}</span></div>
            <div class="spark" data-id="${a.id}"></div>
            <div class="row">
              <span class="price">${money(a.price.perUnit)}<small style="font-size:.8rem;color:var(--text-faint)"> /${a.unit}</small></span>
              <span class="chg ${a.price.changePct >= 0 ? "up" : "down"}">${pct(a.price.changePct, 2)}</span>
            </div>
            <div class="row" style="margin-top:12px">
              <span class="pill ${tone(a.recommendation.label)}">${a.recommendation.label}</span>
              <span class="label">Accuracy ${a.score}/100</span>
            </div>
          </a>`).join("")}
      </div>
      <section class="how">
        <h2>How the forecast works</h2>
        <ol>
          <li><b>Data.</b> About 20 years of daily prices, plus official factor data: the Federal Reserve's dollar index, real interest rates and inflation expectations (FRED), the St. Louis Fed financial stress index, and a newspaper-based Geopolitical Risk Index.</li>
          <li><b>Factor analysis.</b> For each factor we measure how it moves with the asset, whether its moves have led the asset's next month, how that link has changed over time, and what happened after big rises or falls.</li>
          <li><b>Models.</b> Logistic regression (a straight-line model), gradient-boosted trees (which can learn curved patterns and combinations of factors) and an ensemble of both each predict whether the price will be higher in 1 week, 1 month and 3 months.</li>
          <li><b>Testing.</b> For every year since ${DATA.firstTestYear}, models are trained only on earlier years and then tested on that year. The best of the three is used for today's forecast, and its score is shown on every page.</li>
        </ol>
        <p class="note">Updated ${DATA.generated}. Educational tool, not financial advice.</p>
      </section>
    `));
    view.querySelectorAll(".spark").forEach((n) => {
      const pts = byId[n.dataset.id].history.slice(-130);
      n.appendChild(Charts.spark(pts, pts[pts.length - 1][1] >= pts[0][1] ? "#8fae97" : "#c99a8a"));
    });
  }

  function meter(c) {
    const w = Math.min(Math.abs(c) / 0.08, 1) * 50;
    const style = c >= 0 ? `left:50%;width:${w}%;background:var(--up)` : `right:50%;width:${w}%;background:var(--down)`;
    const word = c > 0.01 ? "Pushes up" : c < -0.01 ? "Pushes down" : "Neutral";
    return `<span class="meter">${word}<span class="bar"><i style="${style}"></i></span></span>`;
  }

  // Scale both lines to 0–100 over the window so their shapes can be compared;
  // the tooltip still shows real values.
  function scaled(points) {
    const v = points.map((p) => p[1]), lo = Math.min(...v), hi = Math.max(...v);
    return points.map(([d, x]) => [d, ((x - lo) / (hi - lo || 1)) * 100, x]);
  }

  function factorBody(a, f) {
    const isDiff = f.transform === "diff";
    const chg = isDiff ? `${signed(f.recentChange)} pts` : pct(f.recentChange);
    const maxAbs = Math.max(...f.buckets.map((b) => Math.abs(b.avgReturn)), 0.001);
    return `
      <p>${f.explanation}</p>
      <div class="stats">
        <div><b>${signed(f.corrAll)}</b><span>Moves together since 2006 (${corrWord(f.corrAll)})</span></div>
        <div><b>${signed(f.corr1y)}</b><span>Moves together, last year</span></div>
        <div><b>${signed(f.lead)}</b><span>Predicts next month (${corrWord(f.lead)})</span></div>
        <div><b>${Math.round(f.levelPercentile * 100)}%</b><span>Today's level vs past 10 years</span></div>
      </div>

      <h4>${a.name} vs ${f.name.toLowerCase()} · past year</h4>
      <div class="fchart" data-f="${f.id}"></div>
      <div class="legend"><span class="a">${a.name}</span><span class="f">${f.name}</span>both scaled to the same height</div>
      <div class="tip" data-tip="${f.id}"></div>

      <h4>What happened next</h4>
      <p class="note" style="margin-top:0">${a.name}'s return over the following month, grouped by how much ${f.name.toLowerCase()} moved in the month before (2006 to today).</p>
      <div class="buckets">
        ${f.buckets.map((b, i) => `
          <div class="${i === f.nowBucket ? "now" : ""}">
            <span>${f.name} ${b.label.toLowerCase()}${i === f.nowBucket ? ' <em>← now</em>' : ""}</span>
            <span class="bk"><i class="${b.avgReturn >= 0 ? "up" : "down"}" style="width:${(Math.abs(b.avgReturn) / maxAbs) * 100}%"></i></span>
            <span>${pct(b.avgReturn)} avg · up ${Math.round(b.upShare * 100)}%</span>
          </div>`).join("")}
      </div>

      <h4>How the link has changed</h4>
      <div class="rchart" data-r="${f.id}"></div>
      <div class="tip" data-rtip="${f.id}"></div>
      <p class="note">1-year rolling correlation of daily moves. Above the line they move together; below it they move in opposite directions. Last month's change: ${chg}.</p>
      <p class="note">${f.about} <br>Source: ${f.source}.</p>`;
  }

  function yearBars(yearly) {
    const W = 600, H = 150, pad = { l: 8, r: 36, t: 10, b: 20 }, lo = 0.25, hi = 0.85;
    const bw = (W - pad.l - pad.r) / yearly.length;
    const y = (v) => pad.t + (1 - (v - lo) / (hi - lo)) * (H - pad.t - pad.b);
    const bars = yearly.map((r, i) => {
      const x = pad.l + i * bw, top = y(Math.max(lo, Math.min(hi, r.accuracy)));
      const win = r.accuracy > r.baseline;
      return `<rect x="${x + 3}" y="${top}" width="${bw - 6}" height="${y(lo) - top}" rx="2" fill="${win ? "#9fbea7" : "#d9a998"}"><title>${r.year}: ${Math.round(r.accuracy * 100)}% vs guessing ${Math.round(r.baseline * 100)}%</title></rect>
        <line x1="${x + 1}" x2="${x + bw - 1}" y1="${y(r.baseline)}" y2="${y(r.baseline)}" stroke="#5c5c58" stroke-width="1.5"/>
        ${i % 2 === 0 || yearly.length < 9 ? `<text x="${x + bw / 2}" y="${H - 5}" text-anchor="middle">${String(r.year).slice(2)}'</text>` : ""}`;
    }).join("");
    const grid = [0.3, 0.5, 0.7].map((v) => `<line x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}" stroke="#f0f0ed"/><text x="${W - pad.r + 6}" y="${y(v) + 3}">${v * 100}%</text>`).join("");
    return `<svg viewBox="0 0 ${W} ${H}" class="chart">${grid}${bars}</svg>`;
  }

  function modelSection(a) {
    const hz = a.forecast.horizons, m = hz[1];
    const cmp = a.model.comparison["20"];
    const imp = [...a.factors.map((f) => ({ name: f.name, v: f.importance })), { name: "Momentum & trend", v: a.momentum.importance }]
      .sort((x, y) => y.v - x.v);
    const maxI = Math.max(...imp.map((x) => Math.abs(x.v)), 0.002);
    const top = a.model.coefficients.slice(0, 6), maxW = Math.max(...top.map((c) => Math.abs(c.weight)), 0.01);
    const cell = (x) => `<td class="${x.accuracy > x.baseline ? "pos" : "neg"}">${Math.round(x.accuracy * 100)}%</td>`;
    return `
      <section class="model">
        <span class="label">Model &amp; accuracy</span>
        <div class="scorehead"><span class="big">${a.score}<small> / 100</small></span><span>${scoreWord(a.score)}</span></div>
        <div class="score"><div class="track"><i style="width:${a.score}%"></i><b style="left:50%"></b></div>
          <div class="ends"><span>0</span><span>50 = guessing</span><span>100</span></div></div>
        <p class="note">Tested year by year from ${fmtD(m.testFrom)} to ${fmtD(m.testTo)} (${m.testSize.toLocaleString()} trading days), always on data the model hadn't seen. Half the score is how often it was right compared with guessing; half is how well its probabilities separated up days from down days (AUC).</p>

        <h4>Forecast accuracy</h4>
        <div class="scroll"><table>
          <thead><tr><th>Horizon</th><th>Model used</th><th>Right</th><th>Guessing</th><th>AUC</th></tr></thead>
          <tbody>${hz.map((x) => `<tr><td>${HZ[x.days]}</td><td>${x.modelName.replace(" (average of both)", "")}</td>${cell(x)}<td>${Math.round(x.baseline * 100)}%</td><td>${x.auc.toFixed(2)}</td></tr>`).join("")}</tbody>
        </table></div>

        <h4>Model comparison · 1 month</h4>
        <div class="scroll"><table>
          <thead><tr><th>Model</th><th>Score</th><th>Right</th><th>AUC</th></tr></thead>
          <tbody>${cmp.map((x) => `<tr class="${x.model === m.model ? "chosen" : ""}"><td>${x.name}${x.model === m.model ? " ✓" : ""}</td><td>${x.score}</td>${cell(x)}<td>${x.auc.toFixed(2)}</td></tr>`).join("")}</tbody>
        </table></div>
        <p class="note" style="margin-top:-8px">✓ = used for the forecast. Trees can learn curved patterns and combinations (e.g. "the dollar matters more when stress is high"); logistic regression only draws straight lines.</p>

        <h4>Year by year · 1 month</h4>
        ${yearBars(a.model.yearly)}
        <div class="legend"><span style="color:#9fbea7">Beat guessing</span><span style="color:#d9a998">Missed</span><span class="a">Guessing</span></div>

        <h4>Which factors the model relies on</h4>
        <div class="weights">${imp.map((x) => `<div><span>${x.name}</span><span class="wbar"><i class="${x.v >= 0 ? "up" : "down"}" style="width:${(Math.abs(x.v) / maxI) * 100}%"></i></span><span>${x.v >= 0 ? "" : "−"}${Math.abs(x.v * 100).toFixed(1)}</span></div>`).join("")}</div>
        <p class="note">How much the model's ranking (AUC, in points) drops over the last 3 years when that factor is scrambled. Red means scrambling it helped, so the model is picking up noise there.</p>

        <h4>Straight-line weights (logistic regression)</h4>
        <div class="weights">${top.map((c) => `<div><span>${c.feature}</span><span class="wbar"><i class="${c.weight >= 0 ? "up" : "down"}" style="width:${(Math.abs(c.weight) / maxW) * 100}%"></i></span><span>${signed(c.weight)}</span></div>`).join("")}</div>
        <p class="note">Positive: when this rises, the model leans toward "price up".</p>
      </section>`;
  }

  function renderAsset(a) {
    const [w, m, q] = a.forecast.horizons;
    const rec = a.recommendation;
    view.replaceChildren(h(`
      ${banner}
      <div class="detail">
        <header>
          <span class="label">${a.ticker} · as of ${a.price.asOf}</span>
          <h1>Factors affecting ${a.name}</h1>
          <p>What moves ${a.name.toLowerCase()}, what happened after past moves, and how each factor shapes today's forecast. Factors are ordered by how much the model relies on them.</p>
        </header>

        <section style="min-width:0">
          ${a.factors.map((f, i) => `
            <details class="factor" ${i === 0 ? "open" : ""}>
              <summary><h3>${f.name}</h3>${meter(f.push)}<span class="plus">+</span></summary>
              <div class="body">${factorBody(a, f)}</div>
            </details>`).join("")}
          <details class="factor">
            <summary><h3>Momentum &amp; trend</h3>${meter(a.momentum.push)}<span class="plus">+</span></summary>
            <div class="body"><p>${a.name}'s own recent returns (1 week to 6 months), volatility, and distance from its 200-day average. Commodity trends often persist for a while, so the model also looks at where the price has been heading.</p></div>
          </details>
          ${modelSection(a)}
        </section>

        <aside class="side">
          <div class="box">
            <div style="display:flex;justify-content:space-between"><span class="label">${a.unitLabel} · Today</span>
              <span class="chg ${a.price.changePct >= 0 ? "up" : "down"}">${pct(a.price.changePct, 2)}</span></div>
            <div class="big">${money(a.price.perUnit)}<small> / ${a.unit}</small></div>
          </div>

          <div>
            <h2>Forecast</h2>
            <div id="fc" style="margin-top:10px"></div>
            <div class="legend"><span class="a">Price</span><span class="f">Forecast</span>shaded = likely range</div>
            <div class="tip" id="fctip"></div>
            <p class="label" style="margin:16px 0 0">Chance the price is higher in</p>
            <div class="probs">
              ${[w, m, q].map((x) => `<div><b>${Math.round(x.probUp * 100)}%</b><span>${HZ[x.days]}</span></div>`).join("")}
            </div>
          </div>

          <div class="rec">
            <span class="label">Recommendation</span>
            <h2>${rec.label}</h2>
            <p style="margin:0">${rec.text}</p>
            <p class="note">Accuracy score ${a.score}/100 (${scoreWord(a.score).toLowerCase()}). Bullish = expected to rise; bearish = expected to fall. Not financial advice.</p>
          </div>
        </aside>
      </div>
    `));

    const hist = a.history.slice(-120);
    Charts.line(document.getElementById("fc"), {
      series: [
        { name: "Price", points: hist, color: "#5c5c58" },
        { name: "Forecast", points: [hist[hist.length - 1], ...a.forecast.path.map((p) => [p[0], p[1]])], color: "#c96442", dash: "4 3" },
      ],
      band: a.forecast.path.map((p) => [p[0], p[2], p[3]]),
      marker: hist[hist.length - 1][0], width: 380, height: 220, format: money,
      tip: document.getElementById("fctip"),
    });

    const draw = (d) => {
      const f = a.factors.find((x) => x.id === d.dataset.fid);
      if (!f || d.dataset.done) return;
      const start = f.series[0][0];
      const ah = a.history.filter((p) => p[0] >= start);
      const fFmt = f.transform === "diff" ? (n) => n.toFixed(2) : (n) => n.toLocaleString(undefined, { maximumFractionDigits: 2 });
      Charts.line(d.querySelector(".fchart"), {
        series: [
          { name: a.name, points: scaled(ah), color: "#5c5c58", format: money },
          { name: f.name, points: scaled(f.series), color: "#c96442", width: 1.3, format: fFmt },
        ],
        height: 170, format: () => "", tip: d.querySelector(`[data-tip="${f.id}"]`),
      });
      Charts.line(d.querySelector(".rchart"), {
        series: [{ name: "Correlation", points: f.rolling, color: "#c96442", width: 1.4 }],
        height: 130, fixed: [-1, 1], zero: true, format: (n) => signed(n),
        tip: d.querySelector(`[data-rtip="${f.id}"]`),
      });
      d.dataset.done = 1;
    };
    view.querySelectorAll("details.factor").forEach((d, i) => {
      if (!a.factors[i]) return;
      d.dataset.fid = a.factors[i].id;
      if (d.open) draw(d);
      d.addEventListener("toggle", () => d.open && draw(d));
    });
  }

  function route() {
    const id = location.hash.slice(1);
    renderRail(byId[id] ? id : null);
    if (byId[id]) { renderAsset(byId[id]); document.title = `${byId[id].name} · Asset Forecasts`; }
    else { renderHome(); document.title = "Asset Forecasts"; }
    window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", route);
  route();
})();
