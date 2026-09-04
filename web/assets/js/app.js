// Lógica Frontend & Integração pywebview Bridge com Contrato Padronizado

const appState = {
  currentView: 'view-dashboard',
  jobs: [],
  history: []
};

// Escapa texto vindo de dados (nomes de robô, caminhos de arquivo, logs do backend)
// antes de inserir via innerHTML.
function escapeHtml(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

window.appBridge = {
  switchView: function(viewId) {
    document.querySelectorAll('.view-section').forEach(sec => sec.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));

    const targetSection = document.getElementById(viewId);
    if (targetSection) targetSection.classList.add('active');

    const activeNav = document.querySelector(`[data-target="${viewId}"]`);
    if (activeNav) activeNav.classList.add('active');

    const titles = {
      'view-dashboard': 'Visão Geral do Sistema',
      'view-rpa': 'Central de Automações Robóticas (RPA)',
      'view-analytics': 'Análises Avançadas & Diagnósticos',
      'view-history': 'Histórico & Auditoria de Processos',
      'view-settings': 'Configurações do Mirandinha'
    };
    document.getElementById('page-title').innerText = titles[viewId] || 'Mirandinha';
    appState.currentView = viewId;

    if (viewId === 'view-history') {
      this.loadHistoryFromBackend();
    }
  },

  // 1. Catálogo de Robôs provido pelo Backend (Python como Autoridade Única)
  loadJobsFromBackend: function() {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.get_available_jobs().then(response => {
        if (response.success && response.data) {
          appState.jobs = response.data;
          this.renderJobsTable();
        } else {
          this.appendLog('ERROR', `Erro ao listar robôs: ${response.error?.message}`);
        }
      }).catch(err => {
        this.appendLog('ERROR', `Erro de comunicação: ${err}`);
      });
    } else {
      // Fallback para desenvolvimento em navegador
      appState.jobs = [
        {
          id: 'job_mat_data_necessidade',
          group: 'Materiais',
          order: '1.1',
          name: 'Data Necessidade',
          type: 'SAP / Gestão de Materiais',
          description: 'Atualização automática e reprogramação em lote das datas de necessidade das reservas e ordens de serviço pendentes no ERP.',
          usage_steps: [
            'Certifique-se de que a planilha de insumos ou a lista de ordens no SAP esteja com os números de reserva válidos.',
            'O robô fará a conexão com a interface transacional e localizará cada item de material pendente.',
            'As datas de necessidade serão reprogramadas de acordo com o cronograma atualizado de suprimentos.',
            'Ao concluir, um espelho das alterações e relatório de consistência será gerado automaticamente.'
          ],
          last_run: 'Nunca',
          status: 'idle'
        },
        {
          id: 'job_mat_zerar_compromisso',
          group: 'Materiais',
          order: '1.2',
          name: 'Zerar Compromisso',
          type: 'SAP / Gestão de Materiais',
          description: 'Automação nativa via SAP GUI Scripting para zerar a quantidade reservada (MENGE) e local de descarga (ABLAD) dos itens de materiais diretamente na transação CN52N.',
          usage_steps: [
            'Abra o SAP Logon e conecte-se ao ambiente desejado.',
            'Acesse a transação CN52N com os critérios e filtros de sua escolha e execute (F8) para exibir o relatório ALV na tela.',
            'Certifique-se de que a grade ALV com as colunas POSID, MAKTX e FLMNG está visível na janela principal.',
            'Volte ao Mirandinha e clique em [Iniciar]. O robô fará o drill-down linha por linha, zerando os compromissos e tratando eventuais popups de orçamento automaticamente.'
          ],
          last_run: 'Nunca',
          status: 'idle'
        },
        {
          id: 'job_mat_concluir_requisicoes',
          group: 'Materiais',
          order: '1.3',
          name: 'Concluir Requisições',
          type: 'SAP / Suprimentos',
          description: 'Encerramento massivo e conclusão de requisições de compra atendidas ou obsoletas para saneamento da base de compras.',
          usage_steps: [
            'Carregue ou aponte a lista de requisições de compras que devem receber o status \'Concluída\'.',
            'O robô valida se não existem pedidos de compra ativos em aberto atrelados a cada requisição.',
            'Efetua a marcação do indicador de requisição concluída.',
            'Emite resumo com totais processados com sucesso e eventuais exceções de bloqueio.'
          ],
          last_run: 'Nunca',
          status: 'idle'
        },
        {
          id: 'job_mat_eliminar_reserva',
          group: 'Materiais',
          order: '1.4',
          name: 'Eliminar Reserva',
          type: 'SAP / Gestão de Materiais',
          description: 'Exclusão definitiva ou baixa de reservas de materiais órfãs, liberando itens para requisições prioritárias.',
          usage_steps: [
            'Selecione o arquivo de entrada com o número das reservas e seus respectivos centros/depósitos.',
            'O robô abre a transação de modificação de reservas (ex: MB22/SAP).',
            'Marca o flag de eliminação/bloqueio em cada posição da reserva indicada.',
            'Grava o log de auditoria comprovando a devolução das quantidades ao estoque disponível.'
          ],
          last_run: 'Nunca',
          status: 'idle'
        }
      ];
      this.renderJobsTable();
    }
  },

  renderJobsTable: function() {
    const tbody = document.getElementById('rpa-jobs-tbody');
    if (!tbody) return;

    // Agrupamento dos robôs por grupo
    const grouped = {};
    appState.jobs.forEach(job => {
      const g = job.group || 'Geral';
      if (!grouped[g]) grouped[g] = [];
      grouped[g].push(job);
    });

    let html = '';
    for (const [groupName, jobs] of Object.entries(grouped)) {
      html += `
        <tr class="group-header-row">
          <td colspan="5" class="group-header-title">
            <i class="ri-folder-shared-line"></i> Grupo: ${escapeHtml(groupName)}
          </td>
        </tr>
      `;

      jobs.forEach(job => {
        const itemNumber = job.order ? `${escapeHtml(job.order)}. ` : '';
        const jobId = escapeHtml(job.id);
        html += `
          <tr>
            <td style="font-weight: 600; color: var(--ink-primary); padding-left: 28px;">
              ${itemNumber}${escapeHtml(job.name)}
            </td>
            <td><span class="badge-tag idle">${escapeHtml(job.type)}</span></td>
            <td>${escapeHtml(job.last_run || 'Nunca')}</td>
            <td><span class="badge-tag ${escapeHtml(job.status)}" id="badge-${jobId}">${job.status === 'running' ? 'Executando...' : 'Pronto'}</span></td>
            <td style="text-align: right;">
              <button class="btn btn-primary" style="padding: 6px 14px; font-size: 12.5px;" id="btn-run-${jobId}" onclick="window.appBridge.openJobModal('${jobId}')">
                Executar <i class="ri-arrow-right-line"></i>
              </button>
            </td>
          </tr>
        `;
      });
    }

    tbody.innerHTML = html;
  },

  // Modal de Detalhes e Disparo RPA
  selectedJobId: null,

  openJobModal: function(jobId) {
    const job = appState.jobs.find(j => j.id === jobId);
    if (!job) return;

    this.selectedJobId = jobId;
    document.getElementById('modal-job-name').innerText = `${job.order ? job.order + ' ' : ''}${job.name}`;
    document.getElementById('modal-job-type').innerText = `${job.group ? job.group + ' · ' : ''}${job.type}`;
    document.getElementById('modal-job-description').innerText = job.description || 'Sem descrição cadastrada.';

    const stepsContainer = document.getElementById('modal-job-steps');
    if (stepsContainer) {
      if (job.usage_steps && job.usage_steps.length > 0) {
        stepsContainer.innerHTML = job.usage_steps.map((step, idx) => `
          <div class="step-item">
            <div class="step-number">${idx + 1}</div>
            <div>${step}</div>
          </div>
        `).join('');
      } else {
        stepsContainer.innerHTML = `<div class="step-item"><div class="step-number">1</div><div>Pressione o botão Iniciar para executar a automação.</div></div>`;
      }
    }

    const modal = document.getElementById('rpa-job-modal');
    if (modal) modal.classList.add('active');
  },

  closeJobModal: function() {
    const modal = document.getElementById('rpa-job-modal');
    if (modal) modal.classList.remove('active');
    this.selectedJobId = null;
  },

  startModalJob: function() {
    if (!this.selectedJobId) return;
    const jobId = this.selectedJobId;
    this.closeJobModal();
    this.runJob(jobId);
  },

  // 2. Histórico de Auditoria carregado do SQLite pelo Backend
  loadHistoryFromBackend: function() {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.get_job_history(50).then(response => {
        if (response.success && response.data) {
          appState.history = response.data;
          this.renderHistoryTable();
        } else {
          this.appendLog('ERROR', `Erro ao obter histórico: ${response.error?.message}`);
        }
      });
    } else {
      this.renderHistoryTable();
    }
  },

  renderHistoryTable: function() {
    const tbody = document.getElementById('history-tbody');
    if (!tbody) return;

    if (!appState.history || appState.history.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 24px; color: var(--ink-muted);">Nenhum histórico registrado no banco de dados.</td></tr>`;
      return;
    }

    tbody.innerHTML = appState.history.map(item => {
      const when = item.timestamp_fmt || item.timestamp || item.date || '';
      const name = item.job_name || item.name || '';
      const dur = item.duration_seconds != null ? item.duration_seconds + 's' : (item.duration || '—');
      const items = item.items_processed || item.items || 0;
      const ok = item.status === 'SUCCESS' || item.status === 'Concluído';
      const cancelled = item.status === 'CANCELLED';
      const badgeClass = ok ? 'completed' : (cancelled ? 'idle' : 'failed');
      const simTag = item.is_simulated
        ? ' <span class="badge-tag idle" title="Execução simulada — não contabilizada nos indicadores">Simulação</span>'
        : '';
      return `
      <tr>
        <td>${escapeHtml(when)}</td>
        <td style="font-weight: 600;">${escapeHtml(name)}${simTag}</td>
        <td>${escapeHtml(dur)}</td>
        <td>${escapeHtml(items)} itens</td>
        <td>
          <span class="badge-tag ${badgeClass}">${escapeHtml(item.status)}</span>
        </td>
      </tr>
      `;
    }).join('');
  },

  // 3. Execução de Robôs RPA com Contrato Padronizado, Progresso e Relatório
  activeRunningJobId: null,

  updateProgress: function(current, total) {
    const progressPanel = document.getElementById('rpa-progress-panel');
    const fillEl = document.getElementById('progress-fill-element');
    const metaText = document.getElementById('progress-meta-text');
    if (!progressPanel || !fillEl || !metaText) return;

    progressPanel.classList.add('active');
    const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;
    fillEl.style.width = `${pct}%`;
    metaText.innerText = `${current} / ${total} itens (${pct}%)`;
  },

  cancelCurrentJob: function() {
    this.appendLog('WARNING', 'Operador solicitou cancelamento do robô...');
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.cancel_rpa_job().then(res => {
        this.appendLog('INFO', 'Comando de parada enviado ao executor.');
      });
    }
  },

  runJob: function(jobId) {
    const job = appState.jobs.find(j => j.id === jobId);
    if (!job) return;

    if (this.activeRunningJobId) {
      this.appendLog('WARNING', 'Já existe uma automação em execução. Aguarde a conclusão ou cancele-a.');
      if (typeof Swal !== 'undefined') {
        Swal.fire({ title: 'Automação em andamento', text: 'Aguarde a conclusão do robô atual antes de iniciar outro.', icon: 'info' });
      }
      return;
    }

    this.activeRunningJobId = jobId;
    job.status = 'running';

    // Oculta relatório anterior e exibe barra de progresso
    this.closeReportCard();
    const progressPanel = document.getElementById('rpa-progress-panel');
    const progressJobName = document.getElementById('progress-job-name');
    if (progressPanel) {
      progressPanel.classList.add('active');
      if (progressJobName) progressJobName.innerText = `Executando: ${job.name}`;
      this.updateProgress(0, 100);
    }

    const badge = document.getElementById(`badge-${jobId}`);
    const btn = document.getElementById(`btn-run-${jobId}`);
    if (badge) {
      badge.className = 'badge-tag running';
      badge.innerText = 'Executando...';
    }
    if (btn) {
      btn.disabled = true;
      btn.className = 'btn btn-running-pulse';
      btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> Em Execução...';
    }

    this.appendLog('INFO', `Disparando [${job.name}] em thread isolada...`);

    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.run_rpa_job(jobId).then(response => {
        if (response.success) {
          this.handleJobCompletion(jobId, response.data);
        } else if (response.error?.code === 'RPA_BUSY') {
          // Corrida rara: o backend já estava ocupado. Não mexe no activeRunningJobId
          // (o robô anterior segue rodando); apenas normaliza este botão.
          this.appendLog('WARNING', response.error.message);
          this.resetJobUI(jobId, 'idle');
          if (job) job.status = 'idle';
        } else {
          this.appendLog('ERROR', `Falha [${response.error?.code}]: ${response.error?.message}`);
          this.resetJobUI(jobId, 'failed');
          this.activeRunningJobId = null;
          this.showReportCard({
            job_name: job.name,
            status: 'FAILED',
            duration_seconds: 0,
            processed: 0,
            errors: 1,
            notes: `Ocorreu uma falha: ${response.error?.message || 'Consulte o console para mais detalhes.'}`
          });
        }
      }).catch(err => {
        this.appendLog('ERROR', `Exceção de comunicação: ${err}`);
        const progressPanel = document.getElementById('rpa-progress-panel');
        if (progressPanel) progressPanel.classList.remove('active');
        this.resetJobUI(jobId, 'failed');
        this.activeRunningJobId = null;
      });
    } else {
      let cur = 0;
      const total = 50;
      const interval = setInterval(() => {
        cur += 10;
        this.updateProgress(cur, total);
        if (cur >= total) {
          clearInterval(interval);
          this.handleJobCompletion(jobId, { job_name: job.name, processed: 50, duration_seconds: 2.8, status: 'SUCCESS', errors: 0 });
        }
      }, 500);
    }
  },

  handleJobCompletion: function(jobId, data) {
    const job = appState.jobs.find(j => j.id === jobId);
    const isCancelled = data && data.status === 'CANCELLED';
    const finalStatus = isCancelled ? 'cancelled' : 'completed';

    if (job) {
      job.status = finalStatus;
      job.last_run = 'Agora mesmo';
    }

    // Esconde barra de progresso
    const progressPanel = document.getElementById('rpa-progress-panel');
    if (progressPanel) progressPanel.classList.remove('active');

    this.resetJobUI(jobId, finalStatus);
    this.activeRunningJobId = null;
    this.loadHistoryFromBackend();
    this.loadDashboardKPIs();
    this.loadDashboardCharts();
    this.showReportCard(data);
  },

  resetJobUI: function(jobId, statusType) {
    const badge = document.getElementById(`badge-${jobId}`);
    const btn = document.getElementById(`btn-run-${jobId}`);
    if (badge) {
      if (statusType === 'completed') {
        badge.className = 'badge-tag completed';
        badge.innerText = 'Concluído';
      } else if (statusType === 'idle') {
        badge.className = 'badge-tag idle';
        badge.innerText = 'Pronto';
      } else if (statusType === 'cancelled') {
        badge.className = 'badge-tag idle';
        badge.innerText = 'Interrompido';
      } else {
        badge.className = 'badge-tag failed';
        badge.innerText = 'Falha';
      }
    }
    if (btn) {
      btn.disabled = false;
      btn.className = 'btn btn-primary';
      btn.innerHTML = 'Executar <i class="ri-arrow-right-line"></i>';
    }
  },

  showReportCard: function(data) {
    const reportPanel = document.getElementById('rpa-report-panel');
    if (!reportPanel || !data) return;

    const isSuccess = data.status === 'SUCCESS';
    const isCancelled = data.status === 'CANCELLED';

    const statusValEl = document.getElementById('report-kpi-status');
    const iconEl = document.getElementById('report-icon-status');
    const titleEl = document.getElementById('report-title-text');
    const subEl = document.getElementById('report-subtitle-text');
    const durationEl = document.getElementById('report-kpi-duration');
    const processedEl = document.getElementById('report-kpi-processed');
    const errorsEl = document.getElementById('report-kpi-errors');
    const notesEl = document.getElementById('report-detail-notes');

    titleEl.innerText = `Relatório de Execução — ${data.job_name || 'Rotina RPA'}`;
    durationEl.innerText = `${data.duration_seconds || 0}s`;
    processedEl.innerText = `${data.processed || 0}`;
    errorsEl.innerText = `${data.errors || 0}`;

    if (isSuccess) {
      statusValEl.innerText = 'SUCESSO';
      statusValEl.style.color = 'var(--color-success)';
      iconEl.className = 'ri-checkbox-circle-fill';
      iconEl.style.color = 'var(--color-success)';
      subEl.innerText = 'Processo executado integralmente sem impedimentos.';
      notesEl.innerText = `Todas as ${data.processed || 0} operações foram validadas e auditadas com sucesso no sistema.`;
    } else if (isCancelled) {
      statusValEl.innerText = 'INTERROMPIDO';
      statusValEl.style.color = 'var(--color-warning)';
      iconEl.className = 'ri-alert-fill';
      iconEl.style.color = 'var(--color-warning)';
      subEl.innerText = 'A rotina foi cancelada pelo operador durante o processamento.';
      notesEl.innerText = `Operação pausada com segurança. ${data.processed || 0} itens haviam sido gravados antes da interrupção.`;
    } else {
      statusValEl.innerText = 'FALHA';
      statusValEl.style.color = 'var(--color-danger)';
      iconEl.className = 'ri-error-warning-fill';
      iconEl.style.color = 'var(--color-danger)';
      subEl.innerText = 'A execução encontrou um erro impeditivo.';
      notesEl.innerText = data.notes || 'Verifique o console de logs em tempo real para avaliar a causa técnica do erro.';
    }

    reportPanel.classList.add('active');
    reportPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  },

  closeReportCard: function() {
    const reportPanel = document.getElementById('rpa-report-panel');
    if (reportPanel) reportPanel.classList.remove('active');
  },



  // 4. Emissão e Exibição de Logs com Mapeamento de Cores Mofi
  appendLog: function(level, message) {
    const consoleBox = document.getElementById('rpa-console-output');
    if (!consoleBox) return;

    const timeStr = new Date().toLocaleTimeString();
    const line = document.createElement('div');
    line.className = 'log-line';
    
    let colorClass = 'log-info';
    const norm = (level || 'INFO').toUpperCase();
    if (norm === 'SUCCESS') colorClass = 'log-success';
    else if (norm === 'WARNING' || norm === 'WARN') colorClass = 'log-warn';
    else if (norm === 'ERROR') colorClass = 'log-error';
    else if (norm === 'DEBUG') colorClass = 'log-debug';

    line.innerHTML = `<span class="log-time">[${timeStr}]</span><span class="${colorClass}">[${norm}]</span> ${escapeHtml(message)}`;
    consoleBox.appendChild(line);
    consoleBox.scrollTop = consoleBox.scrollHeight;
  },

  clearLogs: function() {
    const consoleBox = document.getElementById('rpa-console-output');
    if (consoleBox) consoleBox.innerHTML = '';
  },

  loadSampleDataset: function() {
    this.appendLog('INFO', 'Solicitando processamento analítico ao Python...');
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.get_sample_analytics().then(response => {
        if (response.success && response.data) {
          const data = response.data;
          window.renderUpdatedAnalytics(data);
          const banner = document.getElementById('analytics-summary-banner');
          const text = document.getElementById('analytics-summary-text');
          if (banner && text) {
            banner.style.display = 'block';
            text.innerText = `Base demonstrativa (sintética): ${data.total_rows} linhas · ${data.total_anomalies} anomalias (IQR) · média ${data.mean_value} · desvio-padrão ${data.std_dev}.`;
          }
          this.appendLog('SUCCESS', 'Dados analíticos carregados com sucesso.');
        } else {
          this.appendLog('ERROR', `Erro analítico: ${response.error?.message}`);
        }
      });
    }
  },

  selectLocalDataFile: function() {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.select_file().then(response => {
        if (response.success && response.data) {
          const filePath = response.data;
          this.appendLog('INFO', `Arquivo selecionado: ${filePath}`);
          window.pywebview.api.analyze_file(filePath).then(anaResponse => {
            if (anaResponse.success && anaResponse.data) {
              const data = anaResponse.data;
              window.renderUpdatedAnalytics(data);
              const banner = document.getElementById('analytics-summary-banner');
              const text = document.getElementById('analytics-summary-text');
              if (banner && text) {
                banner.style.display = 'block';
                const col = data.analyzed_column ? ` · coluna "${data.analyzed_column}"` : '';
                text.innerText = `${data.file_name}: ${data.total_rows} linhas${col} · ${data.total_anomalies} anomalias (IQR) · média ${data.mean_value} · desvio-padrão ${data.std_dev}.`;
              }
              this.appendLog('SUCCESS', `Arquivo ${data.file_name} processado.`);
            } else {
              this.appendLog('ERROR', `Falha ao analisar arquivo: ${anaResponse.error?.message}`);
            }
          });
        }
      });
    } else {
      alert('Utilize o aplicativo no modo Desktop para seleção de arquivos.');
    }
  },

  selectExportDir: function() {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.select_folder().then(response => {
        if (response.success && response.data) {
          document.getElementById('setting-export-dir').value = response.data;
          this.appendLog('INFO', `Pasta de exportação definida: ${response.data}`);
        }
      });
    }
  },

  loadDashboardKPIs: function() {
    if (!(window.pywebview && window.pywebview.api && window.pywebview.api.get_system_kpis)) return;
    window.pywebview.api.get_system_kpis().then(response => {
      if (!response.success || !response.data) return;
      const kpis = response.data;
      const set = (id, val) => { const el = document.getElementById(id); if (el) el.innerText = val; };
      const hasData = kpis.has_data;

      set('kpi-exec-count', hasData ? kpis.total_jobs.toLocaleString('pt-BR') : '—');
      set('kpi-time-saved', hasData ? `${kpis.time_saved_hours}h` : '—');
      set('kpi-success-rate', (kpis.success_rate == null) ? '—' : `${kpis.success_rate}%`);
      set('kpi-rows-analyzed', hasData ? kpis.total_items.toLocaleString('pt-BR') : '—');
    });
  },

  loadDashboardCharts: function() {
    if (!(window.pywebview && window.pywebview.api && window.pywebview.api.get_dashboard_series)) return;
    window.pywebview.api.get_dashboard_series().then(response => {
      if (response.success && response.data && typeof window.renderDashboardCharts === 'function') {
        window.renderDashboardCharts(response.data);
      }
    });
  },

  refreshData: function() {
    if (this.activeRunningJobId) {
      this.appendLog('WARNING', 'Atualização adiada: há uma automação em execução. Aguarde a conclusão.');
      this.loadDashboardKPIs();
      this.loadDashboardCharts();
      return;
    }
    this.appendLog('INFO', 'Recarregando robôs, histórico e indicadores...');
    this.loadJobsFromBackend();
    this.loadHistoryFromBackend();
    this.loadDashboardKPIs();
    this.loadDashboardCharts();
  },

  // Interceptação de Fechamento com SweetAlert2
  confirmExitApp: function() {

    if (this.activeRunningJobId) {
      if (typeof Swal !== 'undefined') {
        Swal.fire({
          title: 'Automação em Andamento!',
          html: 'Existe um robô executando no momento. Fechar agora pode interromper processos no SAP e perder dados parciais.<br><br><b>Deseja realmente cancelar a automação e encerrar o Mirandinha?</b>',
          icon: 'warning',
          showCancelButton: true,
          confirmButtonText: 'Sim, cancelar e sair',
          cancelButtonText: 'Continuar executando',
          reverseButtons: true
        }).then((result) => {
          if (result.isConfirmed) {
            // Solicita parada e grava estado antes de sair
            if (window.pywebview && window.pywebview.api) {
              window.pywebview.api.cancel_rpa_job().then(() => {
                setTimeout(() => {
                  window.pywebview.api.force_close_app();
                }, 400);
              });
            }
          }
        });
        return false;
      }
    }
    return true;
  }
};

// Intercepta tentativa de fechamento da janela ou navegador
window.addEventListener('beforeunload', (e) => {
  if (window.appBridge.activeRunningJobId) {
    e.preventDefault();
    e.returnValue = 'Existe uma automação em andamento. Deseja sair?';
    window.appBridge.confirmExitApp();
    return e.returnValue;
  }
});

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const target = item.getAttribute('data-target');
      if (target) window.appBridge.switchView(target);
    });
  });

  if (typeof initCharts === 'function') initCharts();
  window.appBridge.loadJobsFromBackend();
  window.appBridge.loadHistoryFromBackend();
  window.appBridge.loadDashboardKPIs();
  window.appBridge.loadDashboardCharts();
});


