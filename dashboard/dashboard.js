// Neon categorical palette for the dark theme (brand indigo + cyan led)
const PALETTE = ["#6f5bff", "#29f0ff", "#ffd23f", "#ff5cf0", "#39ff88", "#ff7b5c",
  "#8e7fe6", "#5ad1ff", "#c9a227", "#d6539b", "#7ee787", "#ffa657", "#b07fd6", "#2de2ff"];
const AXIS = "#8aa0c0", GRID = "#243056", LEGEND = "#e7eaf6";

function jerseySVG(primary, secondary, pattern, size) {
  const body = "M50 14 C44 14 40 17 35 17 L18 24 L11 41 L24 48 L32 43 L32 88 C32 90 33 91 35 91 L65 91 C67 91 68 90 68 88 L68 43 L76 48 L89 41 L82 24 L65 17 C60 17 56 14 50 14 Z";
  const ls = "M35 17 L18 24 L11 41 L24 48 L32 43 L34 26 Z";
  const rs = "M65 17 L82 24 L89 41 L76 48 L68 43 L66 26 Z";
  const collar = "M40 17 Q50 27 60 17 L56 15 Q50 20 44 15 Z";
  const id = "c" + Math.random().toString(36).slice(2, 8);
  let overlay = "";
  if (pattern === "stripes") for (let x = 14; x < 86; x += 12) overlay += `<rect x="${x}" y="10" width="6" height="85" fill="${secondary}"/>`;
  else if (pattern === "halves") overlay = `<rect x="50" y="10" width="50" height="90" fill="${secondary}"/>`;
  else if (pattern === "sash") overlay = `<polygon points="14,40 30,90 46,90 22,32" fill="${secondary}"/>`;
  const st = 'stroke="rgba(0,0,0,0.28)" stroke-width="1.6"';
  return `<svg class="jersey" width="${size}" height="${size}" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
    <defs><clipPath id="${id}"><path d="${body}"/></clipPath></defs>
    <path d="${ls}" fill="${secondary}" ${st}/><path d="${rs}" fill="${secondary}" ${st}/>
    <path d="${body}" fill="${primary}" ${st}/>
    <g clip-path="url(#${id})">${overlay}</g>
    <path d="${body}" fill="none" ${st}/><path d="${collar}" fill="${secondary}" ${st}/></svg>`;
}

async function load() {
  let data;
  try { data = await (await fetch("data.json", { cache: "no-store" })).json(); }
  catch (e) {
    document.getElementById("leaderboard").innerHTML =
      '<div class="empty">Could not load data.json. Generate it from the Admin tab first.</div>';
    return;
  }
  renderMeta(data);
  renderPodium(data.leaderboard || []);
  renderLeaderboard(data.leaderboard || []);
  renderTimeline(data.timeline || {});
  renderBreakdown(data.category_breakdown || []);
  renderResults(data.matches || []);
}

function renderMeta(d) {
  const m = d.meta || {};
  document.getElementById("meta").textContent =
    `${m.participants || 0} players · ${m.matches_played || 0}/${m.matches_total || 0} matches played`;
  document.getElementById("gen").textContent = d.generated_at || "—";
}

function renderPodium(rows) {
  const el = document.getElementById("podium");
  if (!rows.length) { el.innerHTML = '<div class="empty">No players yet.</div>'; return; }
  const top = rows.slice(0, 3);
  const order = [1, 0, 2];
  const crown = ["👑", "🥈", "🥉"];
  let h = '<div class="podium-wrap">';
  order.forEach(slot => {
    if (slot >= top.length) return;
    const r = top[slot];
    const jersey = jerseySVG(r.shirt_primary || "#1801B4", r.shirt_secondary || "#fff", r.shirt_pattern || "solid", 84);
    const sparks = slot === 0 ? [[15, 30, 0], [80, 20, .6], [50, 8, 1.1], [28, 55, .3]]
      .map(([x, y, d]) => `<span class="spark" style="left:${x}%;top:${y}%;animation-delay:${d}s"></span>`).join("") : "";
    h += `<div class="podium p${slot + 1}">${sparks}
      <div class="crown">${crown[slot]}</div>${jersey}
      <div class="pod-name">${esc(r.name)}</div>
      <div class="pod-pts">${r.total_points} pts · ${r.exact_score_hits} exact</div>
      <div class="pedestal">${r.rank}</div></div>`;
  });
  el.innerHTML = h + "</div>";
  if (top.length) confetti();
}

function confetti() {
  if (window._confettiDone) return; window._confettiDone = true;
  const colors = ["#6f5bff", "#29f0ff", "#ffd23f", "#ff5cf0", "#39ff88", "#ffffff"];
  for (let i = 0; i < 70; i++) {
    const c = document.createElement("div");
    c.className = "confetti";
    c.style.left = Math.random() * 100 + "vw";
    c.style.background = colors[i % colors.length];
    c.style.animationDuration = (2.5 + Math.random() * 2.5) + "s";
    c.style.animationDelay = (Math.random() * 0.8) + "s";
    document.body.appendChild(c);
    setTimeout(() => c.remove(), 6000);
  }
}

function renderLeaderboard(rows) {
  const el = document.getElementById("leaderboard");
  if (!rows.length) { el.innerHTML = '<div class="empty">No participants yet.</div>'; return; }
  let h = `<table><thead><tr><th class="rank">#</th><th>Player</th>
    <th class="num">Total</th><th class="num">Match</th><th class="num">Outcomes</th>
    <th class="num">Wildcards</th><th class="num">Exact</th></tr></thead><tbody>`;
  for (const r of rows) {
    const rc = r.rank <= 3 ? `r${r.rank}` : "";
    h += `<tr><td class="rank ${rc}">${r.rank}</td><td>${esc(r.name)}</td>
      <td class="num total">${r.total_points}</td><td class="num">${r.match_points}</td>
      <td class="num">${r.outcome_points}</td><td class="num">${r.wildcard_points}</td>
      <td class="num">${r.exact_score_hits}</td></tr>`;
  }
  el.innerHTML = h + "</tbody></table>";
}

function renderTimeline(timeline) {
  const names = Object.keys(timeline);
  const ctx = document.getElementById("timeline");
  if (!names.length) { blank(ctx, "No scored matches yet."); return; }
  const dates = [...new Set(names.flatMap(n => timeline[n].map(p => p.date)))].sort();
  const datasets = names.map((n, i) => {
    const map = Object.fromEntries(timeline[n].map(p => [p.date, p.y]));
    let last = 0;
    const series = dates.map(d => { if (d in map) last = map[d]; return last; });
    return {
      label: n, data: series, borderColor: PALETTE[i % PALETTE.length],
      backgroundColor: PALETTE[i % PALETTE.length], tension: .25, pointRadius: 2, borderWidth: 2
    };
  });
  new Chart(ctx, {
    type: "line", data: { labels: dates, datasets },
    options: {
      responsive: true, interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { color: LEGEND, boxWidth: 12 } } },
      scales: {
        x: { ticks: { color: AXIS }, grid: { color: GRID } },
        y: { ticks: { color: AXIS }, grid: { color: GRID } }
      }
    }
  });
}

function renderBreakdown(rows) {
  const ctx = document.getElementById("breakdown");
  if (!rows.length) { blank(ctx, "No scores yet."); return; }
  const top = rows.slice(0, 10);
  new Chart(ctx, {
    type: "bar",
    data: {
      labels: top.map(r => r.name),
      datasets: [
        { label: "Match", data: top.map(r => r.match), backgroundColor: PALETTE[0] },
        { label: "Outcomes", data: top.map(r => r.outcome), backgroundColor: PALETTE[1] },
        { label: "Wildcards", data: top.map(r => r.wildcard), backgroundColor: PALETTE[2] }]
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: LEGEND, boxWidth: 12 } } },
      scales: {
        x: { stacked: true, ticks: { color: AXIS }, grid: { display: false } },
        y: { stacked: true, ticks: { color: AXIS }, grid: { color: GRID } }
      }
    }
  });
}

function renderResults(matches) {
  const el = document.getElementById("results");
  if (!matches.length) { el.innerHTML = '<div class="empty">No results entered yet.</div>'; return; }
  const recent = matches.slice(-12).reverse();
  let h = "<table><tbody>";
  for (const m of recent) {
    h += `<tr><td><span class="pill">${esc(m.stage)}${m.group_code ? " " + m.group_code : ""}</span></td>
      <td style="text-align:right">${esc(m.home_team)}</td>
      <td class="num total">${m.home_goals} – ${m.away_goals}</td>
      <td>${esc(m.away_team)}</td></tr>`;
  }
  el.innerHTML = h + "</tbody></table>";
}

function blank(ctx, msg) {
  ctx.replaceWith(Object.assign(document.createElement("div"), { className: "empty", textContent: msg }));
}
function esc(s) { return String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c])); }
load();
