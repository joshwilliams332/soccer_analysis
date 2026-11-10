/* Mingus FC shared helpers: data loading, formatting, header and footer. */
const MFC = (() => {
  const cache = {};
  const load = (name) => cache[name] || (cache[name] = fetch(`data/${name}.json`, { cache: "no-cache" })
    .then((r) => { if (!r.ok) throw new Error(`${name}: ${r.status}`); return r.json(); }));

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const num = (x, d = 2) => (x == null || Number.isNaN(x) ? "–" : Number(x).toFixed(d));
  const pct = (p, d = 0) => (p == null ? "–" : `${(p * 100).toFixed(d)}%`);
  const ord = (n) => { const s = ["th", "st", "nd", "rd"], v = n % 100; return n + (s[(v - 20) % 10] || s[v] || s[0]); };
  const param = (k) => new URLSearchParams(location.search).get(k);

  /* Rank tone: top quarter green (good), bottom quarter red (bad), the rest white (okay). 1 = best. */
  const tone = (r) => {
    if (!r || !r.of) return "";
    const q = Math.max(1, Math.round(r.of / 4));
    return r.rank <= q ? "good" : r.rank > r.of - q ? "bad" : "";
  };
  const rk = (r, label) => (r ? `<span class="rk ${tone(r)}">${label ?? ord(r.rank)}</span>` : "");
  const form = (arr) => (arr || []).slice(-5).map((x) => `<span class="res ${x}">${x}</span>`).join("");

  const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const day = (iso) => new Date(iso).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", timeZone: tz });
  const time = (iso) => new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit", timeZone: tz });
  const dayKey = (iso) => new Date(iso).toLocaleDateString("en-CA", { timeZone: tz });
  const ago = (iso) => {
    const m = Math.round((Date.now() - new Date(iso)) / 60000);
    return m < 60 ? `${m} min ago` : m < 48 * 60 ? `${Math.round(m / 60)} hr ago` : day(iso);
  };

  const MARK = `<svg viewBox="0 0 100 100" aria-hidden="true">
    <polygon points="14,84 14,16 34,16 50,46 66,16 86,16 86,84 68,84 68,46 56,68 44,68 32,46 32,84" fill="currentColor"/>
    <path d="M6,78 C14,72 18,62 26,62 C34,62 36,69 42,68 C50,67 52,48 60,46 C66,44 69,51 74,50 C82,48 86,30 92,20" fill="none" stroke="#101820" stroke-width="12" stroke-linecap="round"/>
    <path d="M6,78 C14,72 18,62 26,62 C34,62 36,69 42,68 C50,67 52,48 60,46 C66,44 69,51 74,50 C82,48 86,30 92,20" fill="none" stroke="#2747D6" stroke-width="5.5" stroke-linecap="round"/>
    <circle cx="92" cy="20" r="10.5" fill="#2747D6" opacity=".22"/><circle cx="92" cy="20" r="6" fill="#2747D6" stroke="#101820" stroke-width="2.5"/>
  </svg>`;

  const NAV = [["index.html", "Matches"], ["table.html", "Table"], ["players.html", "Players"], ["model.html", "Model"]];

  function header(active) {
    const el = document.createElement("header");
    el.className = "top";
    el.innerHTML = `<div class="wrap">
      <a class="brand" href="index.html" aria-label="Mingus FC home">${MARK}<span class="wordmark">MINGUS</span><span class="sub">FC</span></a>
      <nav class="main">${NAV.map(([h, t]) => `<a href="${h}" class="${h === active ? "on" : ""}">${t}</a>`).join("")}</nav>
    </div>`;
    document.body.prepend(el);
  }

  async function footer() {
    const el = document.createElement("footer");
    el.className = "foot";
    let built = "";
    try {
      const meta = await load("meta");
      built = `Updated ${ago(meta.built)} · ${esc(meta.season)} season · through gameweek ${meta.last_finished_gw ?? "–"}<br>`;
    } catch (e) { /* footer still renders */ }
    el.innerHTML = `<div class="wrap">${built}
      Data: Fantasy Premier League public data (player xG and xA; team xG is the sum of its players'). Projections,
      probabilities and ranks are Mingus estimates from that data, not sportsbook lines.<br>
      <div class="rg">For entertainment · 21+ · Gamble responsibly · 1-800-GAMBLER</div>
      <div>Mingus FC · <a href="model.html" style="color:#fff">How accurate are the projections?</a></div></div>`;
    document.body.append(el);
  }

  function fail(where, err) {
    where.innerHTML = `<div class="card empty">Couldn't load the data (${esc(err.message)}). Try again in a minute.</div>`;
  }

  return { load, esc, num, pct, ord, param, rk, tone, form, day, time, dayKey, header, footer, fail };
})();
