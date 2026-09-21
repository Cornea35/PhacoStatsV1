(() => {
  const data = window.PHACO_REFRACTIVE;
  if (!data) return;

  if (typeof Chart !== "undefined") {
    Chart.defaults.color = "#9ab0c8";
    Chart.defaults.plugins.tooltip.backgroundColor = "rgba(18, 26, 43, 0.96)";
    Chart.defaults.plugins.tooltip.titleColor = "#e8eef5";
    Chart.defaults.plugins.tooltip.bodyColor = "#9ab0c8";
    Chart.defaults.plugins.tooltip.borderColor = "rgba(148, 175, 210, 0.2)";
    Chart.defaults.plugins.tooltip.borderWidth = 1;
  }

  const starColors = {
    5: "#2a9d8f",
    4: "#8fbc5a",
    3: "#e9c46a",
    2: "#e76f51",
    1: "#9b2226",
  };

  function pctBarChart(canvasId, pctMap, labels, keys, colors) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === "undefined") return;
    const values = keys.map((k) => (pctMap && pctMap[k]) || 0);
    new Chart(canvas, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Porcentaje",
            data: values,
            backgroundColor: colors,
            borderWidth: 0,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: (ctx) => `${ctx.parsed.x}%` } },
        },
        scales: {
          x: {
            beginAtZero: true,
            max: 100,
            title: { display: true, text: "Porcentaje" },
            ticks: { callback: (v) => `${v}%` },
          },
          y: { grid: { display: false } },
        },
      },
    });
  }

  const starKeys = ["5", "4", "3", "2", "1"];
  const starLabels = ["5★", "4★", "3★", "2★", "1★"];
  const starColorList = starKeys.map((k) => starColors[k]);
  pctBarChart("chartSeqStars", data.seq_star_pct, starLabels, starKeys, starColorList);
  pctBarChart("chartAstigStars", data.astig_star_pct, starLabels, starKeys, starColorList);

  const binKeys = ["4.5–5.0", "3.5–4.5", "2.5–3.5", "1.5–2.5", "1.0–1.5"];
  const binColors = ["#2a9d8f", "#8fbc5a", "#e9c46a", "#e76f51", "#9b2226"];
  pctBarChart("chartOverallBins", data.overall_bin_pct, binKeys, binKeys, binColors);

  // Double-angle plot from server (2·J0, 2·J45); cylinder negativo
  const polar = document.getElementById("chartPolarAstig");
  if (!polar) return;
  const ctx = polar.getContext("2d");
  const W = polar.width;
  const H = polar.height;
  const cx = W / 2;
  const cy = H / 2;
  const maxR = Math.min(W, H) * 0.42;
  const rings = [0.25, 0.5, 1, 1.5, 2];
  const maxD = 2.25;

  function toXY(x, y) {
    const scale = maxR / maxD;
    return [cx + x * scale, cy - y * scale];
  }

  const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxR);
  grad.addColorStop(0, "rgba(42, 157, 143, 0.35)");
  grad.addColorStop(0.45, "rgba(233, 196, 106, 0.22)");
  grad.addColorStop(0.75, "rgba(231, 111, 81, 0.18)");
  grad.addColorStop(1, "rgba(155, 34, 38, 0.12)");
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(cx, cy, maxR, 0, Math.PI * 2);
  ctx.fill();

  ctx.strokeStyle = "rgba(148, 175, 210, 0.25)";
  ctx.fillStyle = "#9ab0c8";
  ctx.font = "11px Segoe UI, sans-serif";
  ctx.textAlign = "center";
  rings.forEach((d) => {
    const r = (d / maxD) * maxR;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillText(String(d), cx + r + 2, cy - 4);
  });

  ctx.beginPath();
  ctx.moveTo(cx - maxR, cy);
  ctx.lineTo(cx + maxR, cy);
  ctx.moveTo(cx, cy - maxR);
  ctx.lineTo(cx, cy + maxR);
  ctx.strokeStyle = "rgba(148, 175, 210, 0.35)";
  ctx.stroke();
  ctx.fillStyle = "#7ec0f0";
  ctx.fillText("0° WTR", cx + maxR + 22, cy + 4);
  ctx.fillText("90° ATR", cx, cy - maxR - 8);
  ctx.fillText("180° WTR", cx - maxR - 28, cy + 4);

  const points = data.polar_points || [];
  points.forEach((p) => {
    const [px, py] = toXY(p.x, p.y);
    const stars = Math.round(p.overall_stars || 3);
    ctx.fillStyle = starColors[stars] || "#4aa3e7";
    ctx.beginPath();
    const s = 5;
    ctx.moveTo(px, py - s);
    ctx.lineTo(px + s, py);
    ctx.lineTo(px, py + s);
    ctx.lineTo(px - s, py);
    ctx.closePath();
    ctx.fill();
  });

  const mv = data.mean_vector || {};
  if (mv.x != null && mv.y != null) {
    const [mx, my] = toXY(mv.x, mv.y);
    ctx.strokeStyle = "#7ec0f0";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(mx, my);
    ctx.stroke();
    ctx.fillStyle = "#7ec0f0";
    ctx.beginPath();
    ctx.arc(mx, my, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.font = "10px Segoe UI, sans-serif";
    ctx.fillText("centroide", mx, my - 10);
  }
})();
