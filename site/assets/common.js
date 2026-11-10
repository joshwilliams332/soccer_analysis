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

  const NAV = [["index.html", "Matches"], ["table.html", "Table"], ["players.html", "Players"], ["fixtures.html", "Fixtures"], ["compare.html", "Compare"]];

  /* Small two-color dot per club (our own simple colors; no crests or kits). */
  const COLORS = {
    ARS: ["#DB0007", "#FFFFFF"], AVL: ["#670E36", "#95BFE5"], BOU: ["#DA291C", "#000000"], BRE: ["#E30613", "#FFFFFF"],
    BHA: ["#0057B8", "#FFFFFF"], BUR: ["#6C1D45", "#99D6EA"], CHE: ["#034694", "#034694"], COV: ["#6CABDD", "#FFFFFF"],
    CRY: ["#1B458F", "#C4122E"], EVE: ["#003399", "#003399"], FUL: ["#FFFFFF", "#000000"], HUL: ["#F5A12D", "#000000"],
    IPS: ["#0044A9", "#FFFFFF"], LEE: ["#FFFFFF", "#1D428A"], LEI: ["#003090", "#FDBE11"], LIV: ["#C8102E", "#C8102E"],
    MCI: ["#6CABDD", "#6CABDD"], MUN: ["#DA291C", "#DA291C"], NEW: ["#241F20", "#FFFFFF"], NFO: ["#DD0000", "#DD0000"],
    SHU: ["#EE2737", "#FFFFFF"], SOU: ["#D71920", "#FFFFFF"], SUN: ["#EB172B", "#FFFFFF"], TOT: ["#FFFFFF", "#132257"],
    WHU: ["#7A263A", "#1BB1E7"], WOL: ["#FDB913", "#231F20"], LUT: ["#F78F1E", "#002D62"],
  };
  const dot = (ab) => {
    const [a, b] = COLORS[ab] || ["#9CA3AF", "#9CA3AF"];
    return `<span class="dot" style="background:linear-gradient(90deg,${a} 50%,${b} 50%)"></span>`;
  };
  const team = (ab, name) => `<span class="tm">${dot(ab)}${esc(name ?? ab)}</span>`;
  const teamUrl = (id) => `team.html?id=${id}`;
  const playerUrl = (id) => `player.html?id=${id}`;
  const tlink = (id, ab, name) => `<a class="lk" href="${teamUrl(id)}">${team(ab, name)}</a>`;
  const plink = (id, name) => `<a class="lk" href="${playerUrl(id)}">${esc(name)}</a>`;
  const us = (n) => (n == null ? "–" : n > 0 ? `+${n}` : `${n}`);

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
      Data: Fantasy Premier League public data (player xG and xA; team xG is the sum of its players'). Odds: average of
      bookmakers via football-data.co.uk when published. Ranks and colors are Mingus's own comparisons.<br>
      <div class="rg">For entertainment · 21+ · Gamble responsibly · 1-800-GAMBLER</div>
      <div>Mingus FC</div></div>`;
    document.body.append(el);
  }

  /* xG trend: 3-match rolling average lines (for = dark green solid, against = light red dashed; colors checked for
     color-blind separation, with dash + direct labels as backup), each match as a dot, tap / hover tooltip. */
  const FOR = "#166534", AGAINST = "#F87171";
  function xgChart(box, results) {
    const rows = results.filter((m) => m.xgf != null);
    if (rows.length < 2) { box.innerHTML = `<div class="muted small">Not enough matches yet.</div>`; return; }
    const roll = (k) => rows.map((_, i) => { const w = rows.slice(Math.max(0, i - 2), i + 1); return w.reduce((s, m) => s + m[k], 0) / w.length; });
    const rf = roll("xgf"), ra = roll("xga");
    const draw = () => {
      const W = Math.max(box.clientWidth, 280), H = 210, L = 30, R = 78, T = 12, B = 26;
      const top = Math.max(2, Math.ceil(Math.max(...rows.map((m) => Math.max(m.xgf, m.xga)))));
      const x = (i) => L + (rows.length === 1 ? 0 : (i * (W - L - R)) / (rows.length - 1));
      const y = (v) => T + (H - T - B) * (1 - v / top);
      const path = (vals) => vals.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join("");
      const step = rows.length > 14 ? 2 : 1;
      let g = "";
      for (let v = 0; v <= top; v++) g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="#E1E5E3" stroke-width="1"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" font-size="11" fill="#5F6B66">${v}</text>`;
      rows.forEach((m, i) => { if (i % step === 0) g += `<text x="${x(i)}" y="${H - 6}" text-anchor="middle" font-size="10.5" fill="#5F6B66">${m.gw}</text>`; });
      const dots = (k, c) => rows.map((m, i) => `<circle cx="${x(i)}" cy="${y(m[k])}" r="4" fill="${c}" fill-opacity=".35" stroke="#fff" stroke-width="2"/>`).join("");
      const end = rows.length - 1;
      let ly1 = y(rf[end]), ly2 = y(ra[end]);
      if (Math.abs(ly1 - ly2) < 14) { const mid = (ly1 + ly2) / 2; const up = rf[end] >= ra[end]; ly1 = mid + (up ? -8 : 8); ly2 = mid + (up ? 8 : -8); }
      box.innerHTML = `<div class="chart-legend">
          <span><svg viewBox="0 0 22 8"><line x1="0" x2="22" y1="4" y2="4" stroke="${FOR}" stroke-width="2.5"/></svg>xG for</span>
          <span><svg viewBox="0 0 22 8"><line x1="0" x2="22" y1="4" y2="4" stroke="${AGAINST}" stroke-width="2.5" stroke-dasharray="5 3"/></svg>xG against</span>
          <span class="muted" style="font-weight:600">Lines: 3-match average · dots: each match</span></div>
        <div class="chart"><svg viewBox="0 0 ${W} ${H}" height="${H}" role="img" aria-label="xG for and against by gameweek">
          ${g}${dots("xga", AGAINST)}${dots("xgf", FOR)}
          <path d="${path(ra)}" fill="none" stroke="${AGAINST}" stroke-width="2" stroke-dasharray="6 4" stroke-linejoin="round" stroke-linecap="round"/>
          <path d="${path(rf)}" fill="none" stroke="${FOR}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
          <text x="${W - R + 8}" y="${ly1 + 4}" font-size="11.5" font-weight="700" fill="#101820">For ${num(rf[end])}</text>
          <text x="${W - R + 8}" y="${ly2 + 4}" font-size="11.5" font-weight="700" fill="#101820">Against ${num(ra[end])}</text>
          <line class="xh" x1="0" x2="0" y1="${T}" y2="${H - B}" stroke="#101820" stroke-width="1" opacity="0"/>
          ${rows.map((_, i) => { const w = (W - L - R) / Math.max(rows.length - 1, 1); return `<rect data-i="${i}" x="${x(i) - w / 2}" y="0" width="${w}" height="${H}" fill="transparent"/>`; }).join("")}
        </svg><div class="tip"></div></div>`;
      const svg = box.querySelector("svg"), tip = box.querySelector(".tip"), xh = box.querySelector(".xh");
      const show = (i) => {
        const m = rows[i];
        xh.setAttribute("x1", x(i)); xh.setAttribute("x2", x(i)); xh.setAttribute("opacity", ".25");
        tip.innerHTML = `GW${m.gw} ${m.home ? "v" : "@"} ${esc(m.opp_short)} · ${m.res} ${m.gf}-${m.ga}<br>xG ${num(m.xgf)} – ${num(m.xga)}<br>3-match avg ${num(rf[i])} – ${num(ra[i])}`;
        const px = (x(i) / W) * svg.clientWidth;
        tip.style.left = `${Math.min(Math.max(px, 80), svg.clientWidth - 80)}px`; tip.style.top = `${(y(Math.max(m.xgf, m.xga)) / H) * svg.clientHeight + 24}px`;
        tip.classList.add("on");
      };
      const hide = () => { tip.classList.remove("on"); xh.setAttribute("opacity", "0"); };
      svg.querySelectorAll("rect[data-i]").forEach((r) => {
        r.addEventListener("mouseenter", () => show(+r.dataset.i));
        r.addEventListener("click", () => show(+r.dataset.i));
      });
      svg.addEventListener("mouseleave", hide);
    };
    draw();
    let t; window.addEventListener("resize", () => { clearTimeout(t); t = setTimeout(draw, 150); });
  }

  function fail(where, err) {
    where.innerHTML = `<div class="card empty">Couldn't load the data (${esc(err.message)}). Try again in a minute.</div>`;
  }

  return { load, esc, num, pct, ord, param, rk, tone, form, dot, team, us, teamUrl, playerUrl, tlink, plink, xgChart, day, time, dayKey, header, footer, fail };
})();
