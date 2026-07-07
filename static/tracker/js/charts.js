(function () {
  const palette = {
    blue: "#2563eb",
    cyan: "#0891b2",
    teal: "#0d9488",
    purple: "#7c3aed",
    pink: "#db2777",
    orange: "#ea580c",
    green: "#16a34a",
    amber: "#f59e0b",
    red: "#ef4444",
    slate: "#64748b",
    navy: "#0f172a",
    grid: "rgba(226, 232, 240, .72)",
  };

  const seriesPalette = [
    palette.blue,
    palette.cyan,
    palette.teal,
    palette.purple,
    palette.pink,
    palette.orange,
    palette.green,
    palette.amber,
  ];

  function setupChartDefaults() {
    if (!window.Chart) return;

    Chart.defaults.font.family =
      'Inter, Geist, "SF Pro Display", "Segoe UI", system-ui, sans-serif';
    Chart.defaults.font.size = 12;
    Chart.defaults.color = palette.slate;
    Chart.defaults.devicePixelRatio = Math.min(window.devicePixelRatio || 1, 2);
    Chart.defaults.animation.duration = 780;
    Chart.defaults.animation.easing = "easeOutQuart";
  }

  function percentLabel(value, values) {
    const total = values.reduce((sum, item) => sum + Number(item || 0), 0);
    if (!total) return "0%";
    return `${Math.round((Number(value || 0) / total) * 100)}%`;
  }

  function basePlugins(values, noun) {
    return {
      legend: {
        position: "bottom",
        labels: {
          boxWidth: 10,
          color: palette.slate,
          padding: 16,
          pointStyle: "circle",
          usePointStyle: true,
        },
      },
      tooltip: {
        backgroundColor: palette.navy,
        bodyColor: "#e2e8f0",
        borderColor: "rgba(255, 255, 255, .1)",
        borderWidth: 1,
        caretPadding: 8,
        cornerRadius: 8,
        displayColors: true,
        padding: 12,
        titleColor: "#ffffff",
        titleFont: { weight: "700" },
        callbacks: {
          label(context) {
            const raw = Number(context.raw || 0);
            const label = context.dataset.label || context.label || noun;
            const suffix = raw === 1 ? noun : `${noun}s`;
            return ` ${label}: ${raw} ${suffix} (${percentLabel(raw, values)})`;
          },
        },
      },
    };
  }

  function barOptions(values, noun, overrides) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      resizeDelay: 120,
      layout: { padding: { top: 8, right: 8, bottom: 0, left: 0 } },
      interaction: { intersect: false, mode: "index" },
      animation: {
        delay(context) {
          return context.type === "data" ? context.dataIndex * 45 : 0;
        },
      },
      plugins: Object.assign(basePlugins(values, noun), {
        legend: { display: false },
      }),
      scales: {
        x: {
          border: { display: false },
          grid: { display: false },
          ticks: { color: palette.slate, maxRotation: 0, autoSkip: true },
        },
        y: {
          beginAtZero: true,
          border: { display: false },
          grid: { color: palette.grid, drawTicks: false },
          ticks: { color: palette.slate, precision: 0, stepSize: 1 },
        },
      },
      ...overrides,
    };
  }

  function doughnutOptions(values, noun, cutout) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      resizeDelay: 120,
      cutout: cutout || "68%",
      animation: {
        animateRotate: true,
        animateScale: true,
      },
      plugins: basePlugins(values, noun),
    };
  }

  function stackedOptions(values, noun) {
    const options = barOptions(values, noun);
    options.plugins.legend = {
      position: "bottom",
      labels: {
        boxWidth: 10,
        color: palette.slate,
        padding: 16,
        pointStyle: "circle",
        usePointStyle: true,
      },
    };
    options.scales.x.stacked = true;
    options.scales.y.stacked = true;
    return options;
  }

  window.CYSDCharts = {
    palette,
    seriesPalette,
    setupChartDefaults,
    barOptions,
    doughnutOptions,
    stackedOptions,
    percentLabel,
  };
})();
