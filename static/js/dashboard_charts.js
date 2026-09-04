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
  var compareA = document.getElementById("dash-compare-a");
  var compareB = document.getElementById("dash-compare-b");
  var compareLabels = document.getElementById("dash-compare-labels");
  var comparePct = document.getElementById("dash-compare-pct");
  var compareValues = document.getElementById("dash-compare-values");
  var titleEl = document.getElementById("dash-main-title");
  var mainCanvas = document.getElementById("dash-main-chart");
  var seasonCanvas = document.getElementById("dash-season-chart");
  if (!mainCanvas || !seasonCanvas) return;

  var mainChart = null;
  var seasonChart = null;
  var palette = ["#0e7490", "#2563eb", "#ca8a04", "#be123c", "#059669", "#7c3aed", "#db2777", "#334155"];
  var points = data.compare_points || [];
  var defaultCompare = data.compare || {};

  function fillCompareSelects() {
    if (!compareA || !compareB) return;
    compareA.innerHTML = "";
    compareB.innerHTML = "";
    if (!points.length) {
      var empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "—";
      compareA.appendChild(empty.cloneNode(true));
      compareB.appendChild(empty);
      return;
    }
    points.forEach(function (p) {
      var optA = document.createElement("option");
      optA.value = p.id;
      optA.textContent = (p.group ? p.group + ": " : "") + p.label;
      var optB = optA.cloneNode(true);
      compareA.appendChild(optA);
      compareB.appendChild(optB);
    });
    var idA = defaultCompare.id_a || points[0].id;
    var idB = defaultCompare.id_b || (points[1] ? points[1].id : points[0].id);
    compareA.value = idA;
    compareB.value = idB;
  }

  function pointById(id) {
    for (var i = 0; i < points.length; i++) {
      if (points[i].id === id) return points[i];
    }
    return null;
  }

  function updateCompare() {
    if (!compareLabels || !comparePct) return;
    var a = pointById(compareA && compareA.value);
    var b = pointById(compareB && compareB.value);
    if (!a || !b) {
      compareLabels.textContent = "— → —";
      comparePct.textContent = "—";
      comparePct.className = "num";
      if (compareValues) compareValues.textContent = "";
      return;
    }
    compareLabels.textContent = a.label + " → " + b.label;
    if (compareValues) {
      compareValues.textContent = "(" + a.value + " → " + b.value + ")";
    }
    if (!a.value) {
      comparePct.textContent = "—";
      comparePct.className = "num";
      return;
    }
    var pct = ((b.value - a.value) / a.value) * 100;
    var rounded = Math.round(pct * 10) / 10;
    comparePct.textContent = (rounded > 0 ? "+" : "") + rounded + "%";
    comparePct.className =
      "num " + (rounded < 0 ? "text-danger" : rounded > 0 ? "text-ok" : "");
  }

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
  if (compareA) compareA.addEventListener("change", updateCompare);
  if (compareB) compareB.addEventListener("change", updateCompare);
  if (resetBtn) {
    resetBtn.addEventListener("click", function () {
      if (typeSel) typeSel.value = "bar";
      if (scopeSel) scopeSel.value = "years";
      fillCompareSelects();
      updateCompare();
      renderMain();
    });
  }

  fillCompareSelects();
  updateCompare();
  renderMain();
  renderSeason();
})();
