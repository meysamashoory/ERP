/* Power-BI-like interactive dashboard charts. */
(function () {
  "use strict";

  var root = document.getElementById("dash-analytics");
  if (!root || typeof Chart === "undefined") return;

  var raw = root.getAttribute("data-charts") || "{}";
  var data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    return;
  }

  var typeSel = document.getElementById("dash-chart-type");
  var scopeSel = document.getElementById("dash-chart-scope");
  var resetBtn = document.getElementById("dash-chart-reset");
  var titleEl = document.getElementById("dash-main-title");
  var mainCanvas = document.getElementById("dash-main-chart");
  var seasonCanvas = document.getElementById("dash-season-chart");
  if (!mainCanvas || !seasonCanvas) return;

  var mainChart = null;
  var seasonChart = null;
  var palette = ["#0e7490", "#2563eb", "#ca8a04", "#be123c", "#059669", "#7c3aed", "#db2777", "#334155"];

  function scopePayload(scope) {
    if (scope === "seasons") {
      return {
        title: "مجموع فصلی",
        labels: (data.seasons && data.seasons.labels) || [],
        values: (data.seasons && data.seasons.totals) || [],
      };
    }
    if (scope === "top") {
      return {
        title: "پرفروش‌ترین / پرتولیدترین",
        labels: (data.top_products && data.top_products.labels) || [],
        values: (data.top_products && data.top_products.values) || [],
        names: (data.top_products && data.top_products.names) || [],
      };
    }
    if (scope === "low") {
      return {
        title: "کم‌فروش‌ترین / کم‌تولیدترین",
        labels: (data.low_products && data.low_products.labels) || [],
        values: (data.low_products && data.low_products.values) || [],
        names: (data.low_products && data.low_products.names) || [],
      };
    }
    return {
      title: "روند سالانه",
      labels: (data.years && data.years.labels) || [],
      values: (data.years && data.years.values) || [],
    };
  }

  function destroyMain() {
    if (mainChart) {
      mainChart.destroy();
      mainChart = null;
    }
  }

  function renderMain() {
    var type = (typeSel && typeSel.value) || "bar";
    var scope = (scopeSel && scopeSel.value) || "years";
    var payload = scopePayload(scope);
    if (titleEl) titleEl.textContent = payload.title;
    destroyMain();

    var labels = payload.labels;
    var values = payload.values;
    var colors = labels.map(function (_, i) {
      return palette[i % palette.length];
    });

    var dataset = {
      label: payload.title,
      data: values,
      backgroundColor: type === "line" ? "rgba(14,116,144,0.18)" : colors,
      borderColor: type === "line" ? "#0e7490" : colors,
      borderWidth: type === "line" ? 2 : 1,
      fill: type === "line",
      tension: 0.25,
    };

    mainChart = new Chart(mainCanvas.getContext("2d"), {
      type: type,
      data: { labels: labels, datasets: [dataset] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: type === "doughnut" },
          tooltip: {
            callbacks: {
              afterLabel: function (ctx) {
                var names = payload.names || [];
                return names[ctx.dataIndex] ? String(names[ctx.dataIndex]) : "";
              },
            },
          },
        },
        scales:
          type === "doughnut"
            ? {}
            : {
                x: { grid: { display: false } },
                y: { beginAtZero: true, ticks: { precision: 0 } },
              },
      },
    });
  }

  function renderSeason() {
    if (seasonChart) seasonChart.destroy();
    var seasons = data.seasons || {};
    seasonChart = new Chart(seasonCanvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: seasons.labels || [],
        datasets: seasons.datasets || [],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { position: "bottom" } },
        scales: {
          x: { stacked: true, grid: { display: false } },
          y: { stacked: true, beginAtZero: true },
        },
      },
    });
  }

  if (typeSel) typeSel.addEventListener("change", renderMain);
  if (scopeSel) scopeSel.addEventListener("change", renderMain);
  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      if (typeSel) typeSel.value = "bar";
      if (scopeSel) scopeSel.value = "years";
      renderMain();
    });
  }

  renderMain();
  renderSeason();
})();
