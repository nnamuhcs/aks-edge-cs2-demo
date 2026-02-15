const btn = document.getElementById("track-now");
const backfillBtn = document.getElementById("backfill-history");
const rebuildBtn = document.getElementById("rebuild-real");
const enrichImagesBtn = document.getElementById("enrich-images");
const output = document.getElementById("track-result");
const rows = Array.from(document.querySelectorAll(".pick-row"));
const chartTitle = document.getElementById("chart-title");
const chartMeta = document.getElementById("chart-meta");
const canvas = document.getElementById("price-chart");
const simCanvas = document.getElementById("sim-chart");
const simKpis = document.getElementById("sim-kpis");
const infoTriggers = Array.from(document.querySelectorAll(".info-trigger"));
const headerTooltip = document.getElementById("header-tooltip");
const chartHover = document.getElementById("chart-hover");
const CHART_FONT_STACK = "\"Avenir Next\", \"Segoe UI\", sans-serif";

let activeInfoTrigger = null;
let currentPoints = [];
let chartGeom = null;
let hoverIndex = null;
let simPoints = [];
let simGeom = null;
let simHoverIndex = null;

function hideHeaderTooltip() {
  if (!headerTooltip) return;
  headerTooltip.hidden = true;
  headerTooltip.textContent = "";
  activeInfoTrigger = null;
}

function showHeaderTooltip(trigger) {
  if (!headerTooltip) return;
  const tip = trigger.dataset.tip || "";
  if (!tip) return;

  if (activeInfoTrigger === trigger && !headerTooltip.hidden) {
    hideHeaderTooltip();
    return;
  }

  activeInfoTrigger = trigger;
  headerTooltip.textContent = tip;
  headerTooltip.hidden = false;

  const rect = trigger.getBoundingClientRect();
  const tooltipRect = headerTooltip.getBoundingClientRect();
  const left = Math.min(
    window.innerWidth - tooltipRect.width - 12,
    Math.max(12, rect.left + rect.width / 2 - tooltipRect.width / 2)
  );
  const top = Math.min(window.innerHeight - tooltipRect.height - 12, rect.bottom + 10);

  headerTooltip.style.left = `${left}px`;
  headerTooltip.style.top = `${top}px`;
}

function hideChartHover() {
  if (!chartHover) return;
  chartHover.hidden = true;
}

function drawLineChart(points, highlightPointIndex = null) {
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  ctx.clearRect(0, 0, width, height);

  currentPoints = points || [];
  chartGeom = null;

  if (!points || points.length === 0) {
    ctx.fillStyle = "#a7b3c4";
    ctx.font = `22px ${CHART_FONT_STACK}`;
    ctx.fillText("No price history available", 40, 74);
    if (chartMeta) chartMeta.textContent = "No historical data for this skin yet.";
    return;
  }

  const scale = Math.max(0.8, Math.min(1.0, width / 1400));
  const padLeft = Math.round(90 * scale);
  const padRight = Math.round(34 * scale);
  const padTop = Math.round(40 * scale);
  const padBottom = Math.round(86 * scale);
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;

  const prices = points.map((p) => p.price_usd);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const span = Math.max(0.01, max - min);
  const stepX = plotW / Math.max(1, points.length - 1);

  chartGeom = { padLeft, padRight, padTop, padBottom, plotW, plotH, min, max, span, stepX, width, height };

  ctx.strokeStyle = "#364458";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#b8c8da";
  ctx.font = `${Math.round(16 * scale)}px ${CHART_FONT_STACK}`;

  for (let i = 0; i <= 4; i += 1) {
    const y = padTop + (plotH * i) / 4;
    ctx.beginPath();
    ctx.moveTo(padLeft, y);
    ctx.lineTo(width - padRight, y);
    ctx.stroke();

    const v = max - (span * i) / 4;
    ctx.fillText(`$${v.toFixed(2)}`, 12, y + 6);
  }

  ctx.beginPath();
  ctx.moveTo(padLeft, height - padBottom);
  ctx.lineTo(width - padRight, height - padBottom);
  ctx.stroke();

  const xLabelIndexes = [0, Math.floor((points.length - 1) / 2), points.length - 1];
  const seen = new Set();
  xLabelIndexes.forEach((idx) => {
    if (idx < 0 || seen.has(idx)) return;
    seen.add(idx);

    const x = padLeft + stepX * idx;
    const label = points[idx].date;
    const labelW = ctx.measureText(label).width;
    const safeX = Math.max(padLeft, Math.min(x - labelW / 2, width - padRight - labelW));
    ctx.fillText(label, safeX, height - 38);
  });

  ctx.fillStyle = "#a7b8cb";
  ctx.font = `${Math.round(14 * scale)}px ${CHART_FONT_STACK}`;
  ctx.fillText("Price (USD)", 12, 24);
  ctx.fillText("Date", width - 52, height - 12);

  ctx.strokeStyle = "#86dcff";
  ctx.lineWidth = 3;
  ctx.beginPath();
  points.forEach((p, i) => {
    const x = padLeft + stepX * i;
    const y = padTop + ((max - p.price_usd) / span) * plotH;
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  ctx.fillStyle = "#86dcff";
  points.forEach((p, i) => {
    const x = padLeft + stepX * i;
    const y = padTop + ((max - p.price_usd) / span) * plotH;
    ctx.beginPath();
    ctx.arc(x, y, 3.2, 0, Math.PI * 2);
    ctx.fill();
  });

  if (highlightPointIndex !== null && highlightPointIndex >= 0 && highlightPointIndex < points.length) {
    const hp = points[highlightPointIndex];
    const x = padLeft + stepX * highlightPointIndex;
    const y = padTop + ((max - hp.price_usd) / span) * plotH;

    ctx.strokeStyle = "rgba(134,220,255,0.45)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, padTop);
    ctx.lineTo(x, height - padBottom);
    ctx.stroke();

    ctx.fillStyle = "#d3f6ff";
    ctx.beginPath();
    ctx.arc(x, y, 5.4, 0, Math.PI * 2);
    ctx.fill();
  }

  const last = points[points.length - 1];
  if (chartMeta) {
    chartMeta.textContent = `Latest: $${last.price_usd.toFixed(2)} | Total points: ${points.length}`;
  }
}

function drawSimChart(points, highlightPointIndex = null) {
  if (!simCanvas) return;
  const ctx = simCanvas.getContext("2d");
  const width = simCanvas.width;
  const height = simCanvas.height;
  ctx.clearRect(0, 0, width, height);
  simPoints = points || [];
  simGeom = null;

  if (!points || points.length === 0) {
    ctx.fillStyle = "#a7b3c4";
    ctx.font = `22px ${CHART_FONT_STACK}`;
    ctx.fillText("Portfolio history unavailable", 40, 74);
    return;
  }

  const padLeft = 86;
  const padRight = 30;
  const padTop = 28;
  const padBottom = 66;
  const plotW = width - padLeft - padRight;
  const plotH = height - padTop - padBottom;
  const stepX = plotW / Math.max(1, points.length - 1);

  const equities = points.map((p) => Number(p.equity));
  const min = Math.min(...equities);
  const max = Math.max(...equities);
  const span = Math.max(0.01, max - min);
  simGeom = { padLeft, padRight, padTop, padBottom, plotW, plotH, min, max, span, stepX, width, height };

  ctx.strokeStyle = "#364458";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#b8c8da";
  ctx.font = `14px ${CHART_FONT_STACK}`;

  for (let i = 0; i <= 4; i += 1) {
    const y = padTop + (plotH * i) / 4;
    ctx.beginPath();
    ctx.moveTo(padLeft, y);
    ctx.lineTo(width - padRight, y);
    ctx.stroke();
    const v = max - (span * i) / 4;
    ctx.fillText(`$${v.toFixed(0)}`, 10, y + 5);
  }

  const labels = [0, Math.floor((points.length - 1) / 2), points.length - 1];
  const drawn = new Set();
  labels.forEach((idx) => {
    if (idx < 0 || drawn.has(idx)) return;
    drawn.add(idx);
    const x = padLeft + stepX * idx;
    const label = points[idx].date;
    const w = ctx.measureText(label).width;
    ctx.fillText(label, Math.max(padLeft, Math.min(x - w / 2, width - padRight - w)), height - 36);
  });

  const drawSeries = (color, getY) => {
    ctx.strokeStyle = color;
    ctx.lineWidth = 3;
    ctx.beginPath();
    points.forEach((p, i) => {
      const x = padLeft + stepX * i;
      const y = getY(p);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  };

  const yAi = (p) => padTop + ((max - Number(p.equity)) / span) * plotH;
  const aiUp = Number(points[points.length - 1].equity) >= Number(points[0].equity);
  const aiColor = aiUp ? "#31e3a5" : "#ff7d92";
  drawSeries(aiColor, yAi);

  const endX = padLeft + stepX * (points.length - 1);
  const aiEndY = yAi(points[points.length - 1]);
  ctx.fillStyle = aiColor;
  ctx.beginPath();
  ctx.arc(endX, aiEndY, 5, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = aiColor;
  ctx.font = `13px ${CHART_FONT_STACK}`;
  ctx.fillText("My Portfolio", padLeft + 6, padTop + 14);

  if (highlightPointIndex !== null && highlightPointIndex >= 0 && highlightPointIndex < points.length) {
    const hp = points[highlightPointIndex];
    const x = padLeft + stepX * highlightPointIndex;
    const y = yAi(hp);
    ctx.strokeStyle = "rgba(138, 245, 205, 0.42)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, padTop);
    ctx.lineTo(x, height - padBottom);
    ctx.stroke();
    ctx.fillStyle = "#dcfff2";
    ctx.beginPath();
    ctx.arc(x, y, 5.4, 0, Math.PI * 2);
    ctx.fill();
  }
}

async function loadSimulation() {
  if (!simKpis) return;
  try {
    const res = await fetch("/simulation/ai-portfolio?initial_capital=8000&top_n=5");
    if (!res.ok) throw new Error("simulation unavailable");
    const sim = await res.json();
    const pnl = Number(sim.ending_capital) - Number(sim.initial_capital);
    const winning = pnl >= 0;
    simKpis.innerHTML = "";
    [
      `My Portfolio: ${winning ? "WINNING" : "LOSING"}`,
      `Start: $${Number(sim.initial_capital).toFixed(2)}`,
      `My Portfolio: $${Number(sim.ending_capital).toFixed(2)}`,
      `${winning ? "Profit" : "Loss"}: ${winning ? "+" : "-"}$${Math.abs(pnl).toFixed(2)}`,
      `Gain/Loss %: ${Number(sim.total_return_pct).toFixed(2)}%`,
      `Days Traded: ${sim.days_traded}`,
      `Win/Loss Days: ${sim.win_days}/${sim.loss_days}`,
      `Max Drawdown: ${Number(sim.max_drawdown_pct).toFixed(2)}%`,
    ].forEach((t, i) => {
      const span = document.createElement("span");
      span.className = "audit-badge";
      if (i === 0 || i === 2 || i === 3 || i === 4) {
        span.classList.add(winning ? "positive" : "negative");
      }
      span.textContent = t;
      simKpis.appendChild(span);
    });
    simHoverIndex = null;
    drawSimChart(sim.points || []);
  } catch {
    simKpis.innerHTML = '<span class="audit-badge">Need more history to display portfolio performance.</span>';
    simHoverIndex = null;
    drawSimChart([], null);
  }
}

function simCanvasMouseToLocal(event) {
  const rect = simCanvas.getBoundingClientRect();
  return {
    x: (event.clientX - rect.left) * (simCanvas.width / rect.width),
    y: (event.clientY - rect.top) * (simCanvas.height / rect.height),
  };
}

function onSimChartHover(event) {
  if (!simGeom || !simPoints.length || !chartHover) return;
  const { x, y } = simCanvasMouseToLocal(event);
  const inPlotX = x >= simGeom.padLeft && x <= simGeom.width - simGeom.padRight;
  const inPlotY = y >= simGeom.padTop && y <= simGeom.height - simGeom.padBottom;
  if (!inPlotX || !inPlotY) {
    if (simHoverIndex !== null) {
      simHoverIndex = null;
      drawSimChart(simPoints, null);
    }
    hideChartHover();
    return;
  }

  const idx = Math.max(
    0,
    Math.min(
      simPoints.length - 1,
      Math.round((x - simGeom.padLeft) / Math.max(1, simGeom.stepX))
    )
  );
  if (simHoverIndex !== idx) {
    simHoverIndex = idx;
    drawSimChart(simPoints, simHoverIndex);
  }

  const point = simPoints[idx];
  chartHover.textContent = `${point.date} | $${Number(point.equity).toFixed(2)}`;
  chartHover.hidden = false;
  chartHover.style.left = `${event.clientX + 12}px`;
  chartHover.style.top = `${event.clientY - 8}px`;
}

function onSimChartLeave() {
  hideChartHover();
  if (simHoverIndex !== null) {
    simHoverIndex = null;
    drawSimChart(simPoints, null);
  }
}

function canvasMouseToLocal(event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: (event.clientX - rect.left) * (canvas.width / rect.width),
    y: (event.clientY - rect.top) * (canvas.height / rect.height),
  };
}

function onChartHover(event) {
  if (!chartGeom || !currentPoints.length || !chartHover) return;
  const { x, y } = canvasMouseToLocal(event);

  const inPlotX = x >= chartGeom.padLeft && x <= chartGeom.width - chartGeom.padRight;
  const inPlotY = y >= chartGeom.padTop && y <= chartGeom.height - chartGeom.padBottom;
  if (!inPlotX || !inPlotY) {
    if (hoverIndex !== null) {
      hoverIndex = null;
      drawLineChart(currentPoints, null);
    }
    hideChartHover();
    return;
  }

  const idx = Math.max(
    0,
    Math.min(
      currentPoints.length - 1,
      Math.round((x - chartGeom.padLeft) / Math.max(1, chartGeom.stepX))
    )
  );

  if (hoverIndex !== idx) {
    hoverIndex = idx;
    drawLineChart(currentPoints, hoverIndex);
  }

  const point = currentPoints[idx];
  chartHover.textContent = `${point.date} | $${point.price_usd.toFixed(2)}`;
  chartHover.hidden = false;
  chartHover.style.left = `${event.clientX + 12}px`;
  chartHover.style.top = `${event.clientY - 8}px`;
}

function onChartLeave() {
  hideChartHover();
  if (hoverIndex !== null) {
    hoverIndex = null;
    drawLineChart(currentPoints, null);
  }
}

async function loadHistory(skinId, skinName) {
  if (!skinId) return;
  const res = await fetch(`/history/${skinId}`);
  if (!res.ok) {
    drawLineChart([]);
    return;
  }

  const history = await res.json();
  const points = history
    .map((h) => ({ date: h.snapshot_date, price_usd: Number(h.price_usd) }))
    .sort((a, b) => (a.date < b.date ? -1 : 1));

  if (chartTitle) chartTitle.textContent = `${skinName} - Price Trend (Full History)`;
  hoverIndex = null;
  drawLineChart(points, null);
}

async function loadAudit() {
  const summaryBox = document.getElementById("audit-summary");
  const rowsBox = document.getElementById("audit-rows");
  if (!summaryBox || !rowsBox) return;

  try {
    const [summaryRes, snapshotsRes] = await Promise.all([
      fetch("/audit/summary"),
      fetch("/audit/snapshots?limit=30"),
    ]);
    const summary = await summaryRes.json();
    const snapshots = await snapshotsRes.json();

    const srcText = (summary.source_breakdown || [])
      .map((s) => `${s.source}: ${s.count}`)
      .join(" | ");

    summaryBox.innerHTML = "";
    [
      `Tracked: ${summary.tracked_skins}/${summary.tracked_universe_target}`,
      `Covered with data: ${summary.covered_skins ?? "-"}`,
      `Snapshots: ${summary.total_snapshots}`,
      `Verified: ${summary.verified_snapshots ?? "-"}`,
      `Unverified: ${summary.unverified_snapshots ?? "-"}`,
      `Days: ${summary.distinct_days}`,
      `Range: ${summary.first_snapshot_date || "-"} to ${summary.last_snapshot_date || "-"}`,
      `Sources: ${srcText}`,
      "AI Engine: LightGBM/XGBoost-style + ARIMA/GARCH-inspired (Demo)",
    ].forEach((t) => {
      const span = document.createElement("span");
      span.className = "audit-badge";
      span.textContent = t;
      summaryBox.appendChild(span);
    });

    rowsBox.innerHTML = "";
    snapshots.forEach((r) => {
      const tr = document.createElement("tr");
      const ref = r.source_ref ? `<a href="${r.source_ref}" target="_blank" rel="noreferrer">link</a>` : "-";
      tr.innerHTML = `
        <td>${r.snapshot_date}</td>
        <td>${r.skin_name}</td>
        <td>$${Number(r.price_usd).toFixed(2)}</td>
        <td>${r.volume_24h}</td>
        <td>${r.source}</td>
        <td>${ref}</td>
      `;
      rowsBox.appendChild(tr);
    });
  } catch {
    summaryBox.textContent = "Audit endpoints unavailable.";
  }
}

document.documentElement.setAttribute("data-theme", "graphite");

rows.forEach((row) => {
  row.addEventListener("click", () => {
    hideHeaderTooltip();
    rows.forEach((r) => r.classList.remove("active"));
    row.classList.add("active");
    loadHistory(row.dataset.skinId, row.dataset.skinName);
  });
});

if (rows.length > 0) {
  rows[0].classList.add("active");
  loadHistory(rows[0].dataset.skinId, rows[0].dataset.skinName);
} else {
  drawLineChart([]);
}

if (canvas) {
  canvas.addEventListener("mousemove", onChartHover);
  canvas.addEventListener("mouseleave", onChartLeave);
}

if (simCanvas) {
  simCanvas.addEventListener("mousemove", onSimChartHover);
  simCanvas.addEventListener("mouseleave", onSimChartLeave);
}

infoTriggers.forEach((trigger) => {
  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    showHeaderTooltip(trigger);
  });
});

document.addEventListener("click", (event) => {
  if (!headerTooltip || headerTooltip.hidden) return;
  const isTrigger = infoTriggers.some((t) => t === event.target);
  if (isTrigger || headerTooltip.contains(event.target)) return;
  hideHeaderTooltip();
});

window.addEventListener("resize", () => {
  if (activeInfoTrigger) showHeaderTooltip(activeInfoTrigger);
});

if (btn) {
  btn.addEventListener("click", async () => {
    output.textContent = "Syncing Steam market prices...";
    try {
      const res = await fetch("/track", { method: "POST" });
      const data = await res.json();
      output.textContent = `Synced ${data.created_snapshots} snapshots (${data.date}).`;
      setTimeout(() => window.location.reload(), 700);
    } catch {
      output.textContent = "Sync failed. Try again.";
    }
  });
}

if (backfillBtn) {
  backfillBtn.addEventListener("click", async () => {
    output.textContent = "Loading historical market prices...";
    try {
      const res = await fetch("/backfill?days=180", { method: "POST" });
      const data = await res.json();
      output.textContent = `Backfilled ${data.created_snapshots} snapshots across ${data.days} days.`;
      setTimeout(() => window.location.reload(), 900);
    } catch {
      output.textContent = "Backfill failed. Try again.";
    }
  });
}

if (rebuildBtn) {
  rebuildBtn.addEventListener("click", async () => {
    output.textContent = "Rebuilding tracked dataset from Steam...";
    try {
      const res = await fetch("/maintenance/rebuild-real?days=180", { method: "POST" });
      const data = await res.json();
      output.textContent = `Deleted ${data.deleted_snapshots}, rebuilt ${data.historical_created} history + ${data.latest_created} latest snapshots.`;
      setTimeout(() => window.location.reload(), 1200);
    } catch {
      output.textContent = "Rebuild failed. Try again.";
    }
  });
}

if (enrichImagesBtn) {
  enrichImagesBtn.addEventListener("click", async () => {
    output.textContent = "Refreshing skin images from Steam...";
    try {
      const res = await fetch("/maintenance/enrich-images", { method: "POST" });
      const data = await res.json();
      output.textContent = `Updated ${data.updated_records} skin records.`;
      setTimeout(() => window.location.reload(), 900);
    } catch {
      output.textContent = "Image refresh failed.";
    }
  });
}

loadAudit();
loadSimulation();
