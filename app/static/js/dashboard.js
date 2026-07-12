(() => {
  const data = window.PHACO_CHARTS;
  if (!data || typeof Chart === "undefined") return;

  const ink = "#5b6b7c";
  const grid = "rgba(11, 94, 168, 0.08)";
  const blue = "#4aa3e7";
  const blueSoft = "rgba(74, 163, 231, 0.18)";
  const blueDeep = "#0b5ea8";
  const bluePale = "#cfe8f8";
  const blueMid = "#7eb8e8";
  const slate = "#9aa8b5";

  const palette = [blueDeep, blue, blueMid, bluePale, slate, "#e8eef3"];

  Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";
  Chart.defaults.font.size = 11;
  Chart.defaults.color = ink;
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.legend.labels.boxHeight = 10;
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.pointStyle = "circle";
  Chart.defaults.plugins.tooltip.backgroundColor = "rgba(255,255,255,0.96)";
  Chart.defaults.plugins.tooltip.titleColor = blueDeep;
  Chart.defaults.plugins.tooltip.bodyColor = ink;
  Chart.defaults.plugins.tooltip.borderColor = "rgba(11, 94, 168, 0.15)";
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.displayColors = false;
  Chart.defaults.elements.bar.borderRadius = 6;
  Chart.defaults.elements.bar.borderSkipped = false;
  Chart.defaults.elements.line.borderWidth = 2;
  Chart.defaults.elements.point.radius = 0;
  Chart.defaults.elements.point.hoverRadius = 3;

  const scaleMinimal = {
    beginAtZero: true,
    ticks: {
      precision: 0,
      color: ink,
      padding: 6,
    },
    grid: {
      color: grid,
      drawBorder: false,
      borderDash: [4, 4],
    },
    border: { display: false },
  };

  const common = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 450, easing: "easeOutQuart" },
    plugins: {
      legend: {
        position: "bottom",
        labels: { padding: 14 },
      },
    },
  };

  new Chart(document.getElementById("chartMonthly"), {
    type: "line",
    data: {
      labels: data.monthly.labels,
      datasets: [
        {
          label: "Cirugías",
          data: data.monthly.surgeries,
          borderColor: blueDeep,
          backgroundColor: blueSoft,
          tension: 0.35,
          fill: true,
          pointHoverBackgroundColor: blueDeep,
        },
        {
          label: "Complicaciones",
          data: data.monthly.complications,
          borderColor: blue,
          backgroundColor: "transparent",
          tension: 0.35,
          fill: false,
          borderDash: [5, 4],
          pointHoverBackgroundColor: blue,
        },
      ],
    },
    options: {
      ...common,
      scales: {
        x: { ...scaleMinimal, grid: { display: false }, border: { display: false } },
        y: scaleMinimal,
      },
    },
  });

  new Chart(document.getElementById("chartSurgeons"), {
    type: "bar",
    data: {
      labels: data.surgeons.labels,
      datasets: [
        {
          label: "Cirugías",
          data: data.surgeons.totals,
          backgroundColor: blue,
          hoverBackgroundColor: blueDeep,
          maxBarThickness: 28,
        },
        {
          label: "Complicaciones",
          data: data.surgeons.complications,
          backgroundColor: bluePale,
          hoverBackgroundColor: blueMid,
          maxBarThickness: 28,
        },
      ],
    },
    options: {
      ...common,
      scales: {
        x: { ...scaleMinimal, grid: { display: false }, border: { display: false } },
        y: scaleMinimal,
      },
    },
  });

  const doughnutOpts = {
    ...common,
    cutout: "72%",
    plugins: {
      ...common.plugins,
      legend: {
        position: "bottom",
        labels: { padding: 12 },
      },
    },
  };

  new Chart(document.getElementById("chartStages"), {
    type: "doughnut",
    data: {
      labels: data.stages.labels.length ? data.stages.labels : ["Sin datos"],
      datasets: [
        {
          data: data.stages.counts.length ? data.stages.counts : [1],
          backgroundColor: data.stages.counts.length ? palette : [bluePale],
          borderWidth: 0,
          hoverOffset: 4,
        },
      ],
    },
    options: doughnutOpts,
  });

  new Chart(document.getElementById("chartTypes"), {
    type: "doughnut",
    data: {
      labels: data.types.labels.length ? data.types.labels : ["Sin datos"],
      datasets: [
        {
          data: data.types.counts.length ? data.types.counts : [1],
          backgroundColor: data.types.counts.length ? palette : [bluePale],
          borderWidth: 0,
          hoverOffset: 4,
        },
      ],
    },
    options: doughnutOpts,
  });

  const riskCanvas = document.getElementById("chartRisks");
  if (riskCanvas && data.risks && !Chart.getChart(riskCanvas)) {
    const riskLabels = data.risks.labels.length ? data.risks.labels : ["Sin factores registrados"];
    const riskCounts = data.risks.counts.length ? data.risks.counts : [0];
    const riskPct = data.risks.pct || [];
    new Chart(riskCanvas, {
      type: "bar",
      data: {
        labels: riskLabels,
        datasets: [
          {
            label: "Casos",
            data: riskCounts,
            backgroundColor: blue,
            hoverBackgroundColor: blueDeep,
            borderRadius: 6,
            maxBarThickness: 22,
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 450, easing: "easeOutQuart" },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const n = ctx.parsed.x;
                const pct = riskPct[ctx.dataIndex];
                return pct != null ? `${n} casos (${pct}% del total)` : `${n} casos`;
              },
            },
          },
        },
        scales: {
          x: {
            beginAtZero: true,
            ticks: { precision: 0, color: ink, padding: 6 },
            grid: { color: grid, drawBorder: false, borderDash: [4, 4] },
            border: { display: false },
            title: { display: true, text: "Número de casos", color: ink, font: { size: 11 } },
          },
          y: {
            ticks: { color: ink, padding: 6, autoSkip: false },
            grid: { display: false },
            border: { display: false },
          },
        },
      },
    });
  }
})();
