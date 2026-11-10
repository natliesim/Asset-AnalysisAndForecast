(() => {
  const DATA = window.ASSET_DATA;
  const view = document.getElementById("view");
  const rail = document.getElementById("rail");
  const byId = Object.fromEntries(DATA.assets.map((a) => [a.id, a]));

  const money = (n) => "$" + n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: n < 10 ? 3 : 2 });
  const pct = (n, d = 1) => `${n >= 0 ? "+" : "−"}${Math.abs(n * 100).toFixed(d)}%`;
  const h = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content; };
  const tone = (label) => (/bullish/i.test(label) ? "bull" : /bearish/i.test(label) ? "bear" : "");
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
              <span class="label">${Math.round(a.forecast.horizons[1].probUp * 100)}% up · 1 mo</span>
            </div>
          </a>`).join("")}
      </div>
      <section class="how">
        <h2>How the forecast works</h2>
        <ol>
          <li>Daily prices for each asset and its drivers (US dollar, interest rates, inflation expectations, market fear, demand) are collected.</li>
          <li>For each asset a <b>logistic regression</b> learns how recent moves in those drivers relate to whether the price was higher 1 week, 1 month and 3 months later.</li>
          <li>The model is tested on the most recent 20% of history it never saw, and its accuracy is shown next to every forecast.</li>
          <li>Because the model is linear, each factor's push up or down is shown directly. Nothing is hidden.</li>
        </ol>
        <p class="note">Updated ${DATA.generated}. Educational tool, not financial advice.</p>
      </section>
    `));
    view.querySelectorAll(".spark").forEach((n) => {
      const a = byId[n.dataset.id];
      const pts = a.history.slice(-130);
      n.appendChild(Charts.spark(pts, pts[pts.length - 1][1] >= pts[0][1] ? "#8fae97" : "#c99a8a"));
    });
  }

  function meter(c) {
    const w = Math.min(Math.abs(c) / 0.6, 1) * 50;
    const style = c >= 0 ? `left:50%;width:${w}%;background:var(--up)` : `right:50%;width:${w}%;background:var(--down)`;
    const word = c > 0.05 ? "Pushes up" : c < -0.05 ? "Pushes down" : "Neutral";
    return `<span class="meter">${word}<span class="bar"><i style="${style}"></i></span></span>`;
  }

  function rebase(points, n = 260) {
    const p = points.slice(-n), b = p[0][1];
    return p.map(([d, v]) => [d, (v / b) * 100]);
  }

  function renderAsset(a) {
    const [w, m, q] = a.forecast.horizons;
    const rec = a.recommendation;
    const factors = [...a.factors].sort((x, y) => Math.abs(y.contribution) - Math.abs(x.contribution));
    view.replaceChildren(h(`
      ${banner}
      <div class="detail">
        <header>
          <span class="label">${a.ticker} · as of ${a.price.asOf}</span>
          <h1>Factors affecting ${a.name}</h1>
          <p>What moves ${a.name.toLowerCase()}, and how each factor is shaping the model's forecast right now. Tap a factor to see its chart.</p>
        </header>

        <section>
          ${factors.map((f, i) => `
            <details class="factor" ${i === 0 ? "open" : ""}>
              <summary><h3>${f.name}</h3>${meter(f.contribution)}<span class="plus">+</span></summary>
              <div class="body">
                <p>${f.explanation}</p>
                <div class="fchart" data-f="${f.id}"></div>
                <div class="legend"><span class="a">${a.name}</span><span class="f">${f.name} (${f.source})</span><span style="color:transparent">.</span>both rebased to 100 one year ago</div>
                <div class="tip" data-tip="${f.id}"></div>
                <p class="note">${f.about}</p>
              </div>
            </details>`).join("")}
          <details class="factor">
            <summary><h3>Momentum &amp; trend</h3>${meter(a.momentum)}<span class="plus">+</span></summary>
            <div class="body"><p>${a.name}'s own recent price trend and volatility. Markets often keep moving in the same direction for a while, so the model also looks at where the price has been heading.</p></div>
          </details>
        </section>

        <aside class="side">
          <div class="box">
            <div class="row" style="display:flex;justify-content:space-between"><span class="label">${a.unitLabel} · Today</span>
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
              ${[w, m, q].map((x, i) => `<div><b>${Math.round(x.probUp * 100)}%</b><span>${["1 week", "1 month", "3 months"][i]}</span></div>`).join("")}
            </div>
          </div>

          <div class="rec">
            <span class="label">Recommendation</span>
            <h2>${rec.label}</h2>
            <p style="margin:0">${rec.text}</p>
            <p class="note">Back-test accuracy (1-month model): ${Math.round(m.accuracy * 100)}% vs ${Math.round(m.baseline * 100)}% from always guessing the more common outcome. Not financial advice.</p>
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

    const drawFactor = (node) => {
      if (node.dataset.done) return;
      const f = a.factors.find((x) => x.id === node.dataset.f);
      const start = f.series[Math.max(0, f.series.length - 260)][0];
      const ah = a.history.filter((p) => p[0] >= start);
      Charts.line(node, {
        series: [
          { name: a.name, points: rebase(ah, ah.length), color: "#5c5c58" },
          { name: f.name, points: rebase(f.series), color: "#c96442", width: 1.3 },
        ],
        height: 180, format: (n) => n.toFixed(0), tip: view.querySelector(`[data-tip="${f.id}"]`),
      });
      node.dataset.done = 1;
    };
    view.querySelectorAll("details.factor").forEach((d) => {
      const node = d.querySelector(".fchart");
      if (!node) return;
      if (d.open) drawFactor(node);
      d.addEventListener("toggle", () => d.open && drawFactor(node));
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
