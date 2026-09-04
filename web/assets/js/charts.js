// Inicialização de Gráficos com paleta Mofi.
// Todos os gráficos começam VAZIOS e são preenchidos com dados reais vindos do backend:
//  - Dashboard  -> window.appBridge.loadDashboardCharts() -> window.renderDashboardCharts(data)
//  - Análises   -> window.appBridge.loadSampleDataset()/selectLocalDataFile() -> window.renderUpdatedAnalytics(data)
let activityChart = null;
let distributionChart = null;
let trendChart = null;
let scatterChart = null;

const MOFI_PALETTE = {
  primary: '#7A70BA',
  secondary: '#48A3D7',
  accent: '#5527FF',
  success: '#2E8A5C',
  warning: '#B67A1E',
  danger: '#C6164F',
  lineColor: '#E8E6ED'
};

const DIST_COLORS = ['#7A70BA', '#48A3D7', '#88967E', '#B67A1E', '#2E8A5C', '#C6164F', '#5527FF'];

function initCharts() {
  const ctxActivity = document.getElementById('chart-activity');
  if (ctxActivity) {
    activityChart = new Chart(ctxActivity, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          {
            label: 'Execuções RPA',
            data: [],
            borderColor: MOFI_PALETTE.primary,
            backgroundColor: 'rgba(122, 112, 186, 0.1)',
            fill: true,
            tension: 0.35,
            borderWidth: 2.5
          },
          {
            label: 'Itens Processados',
            data: [],
            borderColor: MOFI_PALETTE.secondary,
            backgroundColor: 'rgba(72, 163, 215, 0.08)',
            fill: true,
            tension: 0.35,
            borderWidth: 2.5,
            yAxisID: 'y1'
          }
        ]
      },
      options: {
        responsive: true,
        plugins: { legend: { position: 'top', labels: { font: { family: 'Outfit' } } } },
        scales: {
          y: { beginAtZero: true, grid: { color: MOFI_PALETTE.lineColor }, ticks: { precision: 0 } },
          y1: { beginAtZero: true, position: 'right', grid: { display: false } },
          x: { grid: { display: false } }
        }
      }
    });
  }

  const ctxDist = document.getElementById('chart-distribution');
  if (ctxDist) {
    distributionChart = new Chart(ctxDist, {
      type: 'doughnut',
      data: {
        labels: [],
        datasets: [{ data: [], backgroundColor: DIST_COLORS, borderWidth: 0 }]
      },
      options: {
        responsive: true,
        plugins: { legend: { position: 'bottom', labels: { font: { family: 'Outfit', size: 11 } } } },
        cutout: '70%'
      }
    });
  }

  const ctxTrend = document.getElementById('chart-analytics-trend');
  if (ctxTrend) {
    trendChart = new Chart(ctxTrend, {
      type: 'bar',
      data: {
        labels: [],
        datasets: [{ label: 'Valores', data: [], backgroundColor: MOFI_PALETTE.primary, borderRadius: 4 }]
      },
      options: { responsive: true, scales: { y: { beginAtZero: true } } }
    });
  }

  const ctxScatter = document.getElementById('chart-analytics-scatter');
  if (ctxScatter) {
    scatterChart = new Chart(ctxScatter, {
      type: 'scatter',
      data: {
        datasets: [{ label: 'Pontos & Outliers', data: [], backgroundColor: MOFI_PALETTE.secondary }]
      },
      options: { responsive: true }
    });
  }
}

window.renderDashboardCharts = function(data) {
  if (!data) return;
  if (activityChart && data.week) {
    activityChart.data.labels = data.week.labels || [];
    activityChart.data.datasets[0].data = data.week.executions || [];
    activityChart.data.datasets[1].data = data.week.items || [];
    activityChart.update();
  }
  if (distributionChart && data.distribution) {
    distributionChart.data.labels = data.distribution.labels || [];
    distributionChart.data.datasets[0].data = data.distribution.values || [];
    distributionChart.update();
  }
};

window.renderUpdatedAnalytics = function(data) {
  if (trendChart && data.trend) {
    trendChart.data.labels = data.trend.labels || [];
    trendChart.data.datasets[0].data = data.trend.values || [];
    trendChart.update();
  }
  if (scatterChart && data.scatter) {
    scatterChart.data.datasets[0].data = data.scatter || [];
    scatterChart.update();
  }
};
