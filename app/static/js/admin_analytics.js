(() => {
  const data = window.PHACO_ADMIN_CHARTS;
  if (!data || typeof Chart === "undefined") return;

  const ink = "#5b6b7c";
  const blue = "#4aa3e7";
  const blueDeep = "#0b5ea8";
  const bluePale = "#cfe8f8";
  const grid = "rgba(11, 94, 168, 0.08)";

  Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";
  Chart.defaults.font.size = 11;
  Chart.defaults.color = ink;

  const scaleMinimal = {
    beginAtZero: true,
    ticks: { precision: 0, color: ink, padding: 6 },
    grid: { color: grid, drawBorder: false, borderDash: [4, 4] },
    border: { display: false },
  };

  const dist = document.getElementById("chartDistribution");
  if (dist) {
    new Chart(dist, {
      type: "bar",
      data: {
        labels: data.distribution.labels.length ? data.distribution.labels : ["Sin datos"],
        datasets: [{
          label: "Casos sugeridos",
          data: data.distribution.cases.length ? data.distribution.cases : [0],
          backgroundColor: blue,
          hoverBackgroundColor: blueDeep,
          borderRadius: 6,
          maxBarThickness: 32,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ...scaleMinimal, grid: { display: false } },
          y: scaleMinimal,
        },
      },
    });
  }

  const riskBars = document.getElementById("chartRiskBars");
  if (riskBars) {
    new Chart(riskBars, {
      type: "bar",
      data: {
        labels: data.riskFactors.labels.length ? data.riskFactors.labels : ["Sin datos"],
        datasets: [{
          label: "Casos",
          data: data.riskFactors.counts.length ? data.riskFactors.counts : [0],
          backgroundColor: blue,
          hoverBackgroundColor: blueDeep,
          borderRadius: 6,
          maxBarThickness: 22,
        }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: scaleMinimal,
          y: { ...scaleMinimal, grid: { display: false } },
        },
      },
    });
  }

  const pareto = document.getElementById("chartRiskPareto");
  if (pareto) {
    new Chart(pareto, {
      type: "bar",
      data: {
        labels: data.riskFactors.labels.length ? data.riskFactors.labels : ["Sin datos"],
        datasets: [
          {
            type: "bar",
            label: "Casos",
            data: data.riskFactors.counts.length ? data.riskFactors.counts : [0],
            backgroundColor: bluePale,
            yAxisID: "y",
            order: 2,
            borderRadius: 6,
            maxBarThickness: 28,
          },
          {
            type: "line",
            label: "Porcentaje %",
            data: data.riskFactors.cumulative.length ? data.riskFactors.cumulative : [0],
            borderColor: blueDeep,
            backgroundColor: "transparent",
            yAxisID: "y1",
            tension: 0.25,
            order: 1,
            pointRadius: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom", labels: { usePointStyle: true, boxWidth: 8 } },
        },
        scales: {
          x: { ...scaleMinimal, grid: { display: false } },
          y: { ...scaleMinimal, position: "left", title: { display: true, text: "Casos" } },
          y1: {
            position: "right",
            min: 0,
            max: 100,
            grid: { drawOnChartArea: false },
            border: { display: false },
            ticks: { callback: (v) => `${v}%` },
            title: { display: true, text: "Acumulado" },
          },
        },
      },
    });
  }

  const reint = document.getElementById("chartReinterventionTypes");
  if (reint && data.reinterventionTypes) {
    const labels = data.reinterventionTypes.labels || [];
    const counts = data.reinterventionTypes.counts || [];
    new Chart(reint, {
      type: "bar",
      data: {
        labels: labels.length ? labels : ["Sin datos"],
        datasets: [{
          label: "Número",
          data: counts.length ? counts : [0],
          backgroundColor: blue,
          hoverBackgroundColor: blueDeep,
          borderRadius: 6,
          maxBarThickness: 26,
        }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: {
            ...scaleMinimal,
            title: { display: true, text: "Número de reintervenciones" },
          },
          y: {
            ticks: { color: ink, autoSkip: false },
            grid: { display: false },
            border: { display: false },
          },
        },
      },
    });
  }
})();
