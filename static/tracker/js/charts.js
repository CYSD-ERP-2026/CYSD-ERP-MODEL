/**
 * CYSD ERP – Chart.js Helper Library
 * ====================================
 * Centralised chart configuration, palette, and factory functions.
 * All chart instances across the app use these helpers to ensure
 * visual consistency and easy theming.
 *
 * Features:
 *  - Gradient fills for bar and line charts
 *  - Value labels rendered directly on bar segments
 *  - Smooth entrance animations with staggered delays
 *  - Premium navy-on-white tooltips with percent breakdown
 *  - Accessible color palette with sufficient contrast
 */
(function () {
  "use strict";

  // ── Design Tokens ─────────────────────────────────────────────────────
  const palette = {
    blue:   "#2563eb",
    cyan:   "#0891b2",
    teal:   "#0d9488",
    purple: "#7c3aed",
    pink:   "#db2777",
    orange: "#ea580c",
    green:  "#16a34a",
    amber:  "#f59e0b",
    red:    "#ef4444",
    slate:  "#64748b",
    navy:   "#0f172a",
    grid:   "rgba(226, 232, 240, .65)",
    // Semi-transparent variants for gradient stops
    blueAlpha:   "rgba(37,  99, 235, .15)",
    cyanAlpha:   "rgba(8,  145, 178, .15)",
    tealAlpha:   "rgba(13, 148, 136, .15)",
    purpleAlpha: "rgba(124, 58, 237, .15)",
    redAlpha:    "rgba(239, 68,  68, .15)",
    amberAlpha:  "rgba(245,158, 11, .15)",
  };

  // Series palette used for multi-dataset / stacked charts
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

  function isCompactViewport() {
    return window.matchMedia && window.matchMedia("(max-width: 575.98px)").matches;
  }

  // ── Global Chart.js Defaults ──────────────────────────────────────────
  function setupChartDefaults() {
    if (!window.Chart) return;

    const compact = isCompactViewport();

    Chart.defaults.font.family =
      'Inter, Geist, "SF Pro Display", "Segoe UI", system-ui, sans-serif';
    Chart.defaults.font.size   = compact ? 10 : 12;
    Chart.defaults.color       = palette.slate;
    Chart.defaults.devicePixelRatio = Math.min(window.devicePixelRatio || 1, 2);

    // Smooth default animation
    Chart.defaults.animation.duration = 820;
    Chart.defaults.animation.easing   = "easeOutQuart";

    // Responsive resize debounce
    Chart.defaults.resizeDelay = 120;
  }

  // ── Utility: create a vertical gradient for a single dataset ─────────
  /**
   * Build a canvas linear gradient for a bar/line chart.
   * @param {CanvasRenderingContext2D} ctx
   * @param {string} colorSolid  – top / base colour (opaque)
   * @param {string} colorAlpha  – bottom colour (semi-transparent)
   * @param {number} height      – canvas height in px
   */
  function makeGradient(ctx, colorSolid, colorAlpha, height) {
    const grad = ctx.createLinearGradient(0, 0, 0, height || 320);
    grad.addColorStop(0, colorSolid);
    grad.addColorStop(1, colorAlpha);
    return grad;
  }

  // ── Utility: percent label helper ────────────────────────────────────
  function percentLabel(value, values) {
    const total = values.reduce((s, v) => s + Number(v || 0), 0);
    if (!total) return "0%";
    return `${Math.round((Number(value || 0) / total) * 100)}%`;
  }

  // ── Base plugin config shared across all chart types ─────────────────
  function basePlugins(values, noun) {
    const compact = isCompactViewport();

    return {
      legend: {
        position: "bottom",
        labels: {
          boxWidth: compact ? 8 : 10,
          color: palette.slate,
          padding: compact ? 10 : 18,
          pointStyle: "circle",
          usePointStyle: true,
          font: { size: compact ? 10 : 12, weight: "500" },
        },
      },
      tooltip: {
        backgroundColor: palette.navy,
        bodyColor: "#e2e8f0",
        borderColor: "rgba(255,255,255,.10)",
        borderWidth: 1,
        caretPadding: 8,
        cornerRadius: 10,
        displayColors: true,
        padding: compact ? 10 : 14,
        titleColor: "#ffffff",
        titleFont: { weight: "700", size: compact ? 11 : 13 },
        bodyFont: { size: compact ? 10 : 12 },
        callbacks: {
          label(context) {
            const raw  = Number(context.raw || 0);
            const lbl  = context.dataset.label || context.label || noun;
            const sfx  = raw === 1 ? noun : `${noun}s`;
            const pct  = percentLabel(raw, values);
            return `  ${lbl}: ${raw} ${sfx}  (${pct})`;
          },
        },
      },
    };
  }

  // ── Bar chart value-label plugin (drawn above/beside each bar) ────────
  /**
   * Inline Chart.js plugin: renders the raw value at the end of each bar.
   * Respects horizontal vs vertical orientation automatically.
   */
  const valueLabelPlugin = {
    id: "cysdValueLabels",
    afterDatasetsDraw(chart) {
      if (chart.width < 360) return;

      const { ctx, data } = chart;
      const isHorizontal  = chart.options.indexAxis === "y";

      chart.data.datasets.forEach((dataset, datasetIndex) => {
        const meta = chart.getDatasetMeta(datasetIndex);
        if (meta.hidden) return;

        meta.data.forEach((bar, index) => {
          const value = dataset.data[index];
          if (!value) return;

          ctx.save();
          ctx.fillStyle    = palette.slate;
          ctx.font         = `600 11px Inter, system-ui, sans-serif`;
          ctx.textBaseline = isHorizontal ? "middle" : "bottom";
          ctx.textAlign    = isHorizontal ? "left" : "center";

          const GAP = 5;
          let x, y;
          if (isHorizontal) {
            x = bar.x + GAP;
            y = bar.y;
          } else {
            x = bar.x;
            y = bar.y - GAP;
          }

          ctx.fillText(value, x, y);
          ctx.restore();
        });
      });
    },
  };

  // Register globally so all chart instances pick it up automatically
  if (window.Chart) {
    Chart.register(valueLabelPlugin);
  }

  // ── Bar Options Factory ───────────────────────────────────────────────
  function barOptions(values, noun, overrides) {
    const compact = isCompactViewport();

    const base = {
      responsive: true,
      maintainAspectRatio: false,
      resizeDelay: 120,
      layout: {
        padding: compact
          ? { top: 12, right: 8, bottom: 0, left: 0 }
          : { top: 20, right: 24, bottom: 4, left: 4 },
      },
      interaction: { intersect: false, mode: "index" },
      animation: {
        duration: 820,
        easing: "easeOutQuart",
        delay(context) {
          return context.type === "data" ? context.dataIndex * 55 : 0;
        },
      },
      plugins: Object.assign(basePlugins(values, noun), {
        legend: { display: false },
        cysdValueLabels: {},  // activate value labels
      }),
      scales: {
        x: {
          border: { display: false },
          grid:   { display: false },
          ticks: {
            color: palette.slate,
            maxRotation: compact ? 0 : 30,
            autoSkip: true,
            font: { size: compact ? 9 : 11 },
          },
        },
        y: {
          beginAtZero: true,
          border: { display: false },
          grid: {
            color: palette.grid,
            drawTicks: false,
          },
          ticks: {
            color: palette.slate,
            precision: 0,
            stepSize: 1,
            font: { size: compact ? 9 : 11 },
            padding: compact ? 3 : 6,
          },
        },
      },
    };

    // Deep-merge overrides (shallow for nested objects)
    if (overrides) {
      const { scales: oScales, plugins: oPlugins, ...rest } = overrides;
      Object.assign(base, rest);
      if (oScales) {
        base.scales = base.scales || {};
        Object.keys(oScales).forEach(k => {
          base.scales[k] = Object.assign({}, base.scales[k] || {}, oScales[k]);
        });
      }
      if (oPlugins) {
        base.plugins = Object.assign({}, base.plugins, oPlugins);
      }
    }

    return base;
  }

  // ── Doughnut Options Factory ──────────────────────────────────────────
  function doughnutOptions(values, noun, cutout) {
    return {
      responsive: true,
      maintainAspectRatio: false,
      resizeDelay: 120,
      cutout: cutout || "68%",
      animation: {
        animateRotate: true,
        animateScale: true,
        duration: 900,
        easing: "easeOutCubic",
      },
      plugins: basePlugins(values, noun),
    };
  }

  // ── Stacked Bar Options Factory ───────────────────────────────────────
  function stackedOptions(values, noun) {
    const compact = isCompactViewport();
    const opts = barOptions(values, noun);
    // Show legend for stacked charts so domain colours are explained
    opts.plugins.legend = {
      position: "bottom",
      labels: {
        boxWidth: compact ? 8 : 10,
        color: palette.slate,
        padding: compact ? 10 : 18,
        pointStyle: "circle",
        usePointStyle: true,
        font: { size: compact ? 10 : 12, weight: "500" },
      },
    };
    // Disable per-bar value labels on stacked charts (too noisy)
    opts.plugins.cysdValueLabels = false;
    opts.scales.x = Object.assign({}, opts.scales.x, { stacked: true });
    opts.scales.y = Object.assign({}, opts.scales.y, { stacked: true });
    return opts;
  }

  // ── Gradient Bar Dataset Helper ───────────────────────────────────────
  /**
   * Wrap a plain dataset object so the backgroundColor becomes a live
   * gradient that resolves on the first render.
   *
   * Usage:
   *   data: { datasets: [ gradientDataset(ctx, { label, data, ... }, '#2563eb', 'rgba(37,99,235,.12)') ] }
   *
   * @param {CanvasRenderingContext2D} ctx     – canvas context
   * @param {object}                  dataset – Chart.js dataset object
   * @param {string}                  solid   – opaque colour
   * @param {string}                  alpha   – translucent colour
   * @param {number}                  height  – canvas height (px)
   */
  function gradientDataset(ctx, dataset, solid, alpha, height) {
    return Object.assign({}, dataset, {
      backgroundColor: makeGradient(ctx, solid, alpha, height),
    });
  }

  // ── Public API ────────────────────────────────────────────────────────
  window.CYSDCharts = {
    palette,
    seriesPalette,
    setupChartDefaults,
    makeGradient,
    gradientDataset,
    barOptions,
    doughnutOptions,
    stackedOptions,
    percentLabel,
  };
})();
