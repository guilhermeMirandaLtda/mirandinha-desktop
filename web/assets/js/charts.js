// Inicialização de Gráficos com paleta Mofi
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

function initCharts() {
  // 1. Gráfico de Atividade (Linha)
  const ctxActivity = document.getElementById('chart-activity');
  if (ctxActivity) {
    activityChart = new Chart(ctxActivity, {
      type: 'line',
      plugins: typeof ChartDataLabels !== 'undefined' ? [ChartDataLabels] : [],
      data: {
        labels: ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom'],
        datasets: [
          {
            label: 'Execuções no Dia',
            data: [0, 0, 0, 0, 0, 0, 0],
            borderColor: MOFI_PALETTE.primary,
            backgroundColor: 'rgba(122, 112, 186, 0.12)',
            fill: true,
            tension: 0.35,
            borderWidth: 2.5,
            pointRadius: 4,
            pointHoverRadius: 6,
            datalabels: {
              align: 'top',
              anchor: 'end',
              color: MOFI_PALETTE.primary,
              font: { weight: 'bold', size: 11, family: 'Outfit' },
              formatter: function(value) {
                return value > 0 ? value : '';
              }
            }
          },
          {
            label: 'Itens Processados',
            data: [0, 0, 0, 0, 0, 0, 0],
            borderColor: MOFI_PALETTE.secondary,
            backgroundColor: 'rgba(72, 163, 215, 0.08)',
            fill: true,
            tension: 0.35,
            borderWidth: 2.5,
            pointRadius: 4,
            pointHoverRadius: 6,
            datalabels: {
              align: 'bottom',
              anchor: 'start',
              color: MOFI_PALETTE.secondary,
              font: { weight: 'bold', size: 11, family: 'Outfit' },
              formatter: function(value) {
                return value > 0 ? value : '';
              }
            }
          }
        ]
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: 'top', labels: { font: { family: 'Outfit' } } }
        },
        scales: {
          y: { 
            beginAtZero: true,
            grid: { color: MOFI_PALETTE.lineColor } 
          },
          x: { grid: { display: false } }
        }
      }
    });
  }

  // 2. Gráfico Donut de Distribuição
  const ctxDist = document.getElementById('chart-distribution');
  if (ctxDist) {
    distributionChart = new Chart(ctxDist, {
      type: 'doughnut',
      plugins: typeof ChartDataLabels !== 'undefined' ? [ChartDataLabels] : [],
      data: {
        labels: ['Zerar Compromisso', 'Robô Extrator'],
        datasets: [{
          data: [0, 0],
          backgroundColor: [
            MOFI_PALETTE.primary,
            MOFI_PALETTE.secondary,
            '#88967E',
            MOFI_PALETTE.warning
          ],
          borderWidth: 0,
          datalabels: {
            color: '#FFFFFF',
            font: { weight: 'bold', size: 12, family: 'Outfit' },
            formatter: function(value) {
              return value > 0 ? value : '';
            }
          }
        }]
      },
      options: {
        responsive: true,
        plugins: {
          legend: { position: 'bottom', labels: { font: { family: 'Outfit', size: 11 } } }
        },
        cutout: '65%'
      }
    });
  }

  // 3. Gráficos Analíticos
  const ctxTrend = document.getElementById('chart-analytics-trend');
  if (ctxTrend) {
    trendChart = new Chart(ctxTrend, {
      type: 'bar',
      data: {
        labels: ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago'],
        datasets: [{
          label: 'Média Operacional',
          data: [45, 52, 58, 64, 78, 85, 91, 98],
          backgroundColor: MOFI_PALETTE.primary,
          borderRadius: 4
        }]
      },
      options: { responsive: true }
    });
  }

  const ctxScatter = document.getElementById('chart-analytics-scatter');
  if (ctxScatter) {
    scatterChart = new Chart(ctxScatter, {
      type: 'scatter',
      data: {
        datasets: [{
          label: 'Pontos & Outliers',
          data: [
            {x: 10, y: 20}, {x: 15, y: 30}, {x: 25, y: 45}, {x: 35, y: 40},
            {x: 45, y: 80}, {x: 55, y: 65}, {x: 70, y: 110}, {x: 85, y: 95}
          ],
          backgroundColor: MOFI_PALETTE.secondary
        }]
      },
      options: { responsive: true }
    });
  }
}

window.renderUpdatedAnalytics = function(data) {
  if (trendChart && data.trend) {
    trendChart.data.labels = data.trend.labels;
    trendChart.data.datasets[0].data = data.trend.values;
    trendChart.update();
  }
  if (scatterChart && data.scatter) {
    scatterChart.data.datasets[0].data = data.scatter;
    scatterChart.update();
  }
};

window.renderUpdatedDashboardCharts = function(chartData) {
  if (!chartData) return;

  // Atualiza gráfico de atividade temporal (últimos 7 dias)
  if (activityChart && chartData.activity) {
    activityChart.data.labels = chartData.activity.labels || [];
    if (activityChart.data.datasets[0]) {
      activityChart.data.datasets[0].data = chartData.activity.jobs || [];
      activityChart.data.datasets[0].label = 'Execuções no Dia';
    }
    if (activityChart.data.datasets[1]) {
      activityChart.data.datasets[1].data = chartData.activity.items || [];
      activityChart.data.datasets[1].label = 'Itens Processados';
    }
    activityChart.update();
  }

  // Atualiza gráfico donut de distribuição por robô
  if (distributionChart && chartData.distribution) {
    distributionChart.data.labels = chartData.distribution.labels || [];
    if (distributionChart.data.datasets[0]) {
      distributionChart.data.datasets[0].data = chartData.distribution.data || [];
    }
    distributionChart.update();
  }
};

