// Lógica Frontend & Integração pywebview Bridge com Contrato Padronizado

const appState = {
  currentView: 'view-dashboard',
  jobs: [],
  history: []
};

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
      'view-studio': 'Studio — Editor Visual de Automações',
      'view-analytics': 'Análises Avançadas & Diagnósticos',
      'view-history': 'Histórico & Auditoria de Processos',
      'view-settings': 'Configurações do Mirandinha'
    };
    document.getElementById('page-title').innerText = titles[viewId] || 'Mirandinha';
    appState.currentView = viewId;

    if (viewId === 'view-history') {
      this.loadHistoryFromBackend();
    }
    if (viewId === 'view-dashboard') {
      this.loadDashboardKPIs();
    }
    if (viewId === 'view-rpa') {
      this.loadJobsFromBackend();
    }
    if (viewId === 'view-studio' && window.studioBridge) {
      window.studioBridge.init();
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
          requires_file: true,
          description: 'Atualização automática e reprogramação em lote das datas de necessidade dos componentes de diagramas de rede na transação CJ20N a partir de planilha Excel.',
          usage_steps: [
            'Selecione a planilha Excel (.xlsx) contendo as colunas: \'PEP\', \'Diagrama\' e \'Data Necessidade\'.',
            'Certifique-se de estar com o SAP Logon aberto e conectado na sessão desejada.',
            'Clique em [Iniciar] para o Mirandinha abrir a transação CJ20N e processar os diagramas em lote.',
            'Ao concluir, os diagramas atualizados e eventuais exceções serão registrados no relatório e histórico.'
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
            'Logar no SAP Financeiro.',
            'Acessar a transação "CN52N".',
            'Escolher o layout de sua preferência, sugestão "/MIRANDA-ZER".',
            'Clique no botão [Iniciar] abaixo.',
            'Atenção: O Mirandinha irá processar cada item, zerando a quantidade comprometida de cada linha.'
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
          requires_file: true,
          template_type: 'concluir_requisicoes',
          file_hint: "Colunas exigidas: Requisicao e Item.",
          description: 'Encerramento massivo e marcação do status de requisição concluída (EBAN-EBAKZ) na transação ME52N para saneamento da base de suprimentos.',
          usage_steps: [
            'Selecione a planilha Excel (.xlsx) contendo as colunas: \'Requisicao\' e \'Item\' (ou baixe a planilha modelo).',
            'Certifique-se de estar com o SAP Logon aberto e conectado na sessão desejada.',
            'Clique em [Iniciar] para o Mirandinha abrir a transação ME52N e processar as requisições em lote.',
            'Ao concluir, os itens encerrados e eventuais bloqueios serão gravados no relatório e histórico.'
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
          requires_file: true,
          template_type: 'eliminar_reserva',
          file_hint: "Colunas exigidas: Reserva e Item.",
          description: 'Exclusão e baixa definitiva de reservas de materiais órfãs na transação MB22 (flag RESB-XLOEK), liberando saldo imediatamente para o estoque.',
          usage_steps: [
            'Selecione a planilha Excel (.xlsx) contendo as colunas: \'Reserva\' e \'Item\' (ou baixe a planilha modelo).',
            'Certifique-se de estar com o SAP Logon aberto e conectado na sessão desejada.',
            'Clique em [Iniciar] para o Mirandinha abrir a transação MB22 e marcar a eliminação de cada posição.',
            'Ao concluir, o espelho das baixas e auditoria completa será gerado automaticamente.'
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
      const groupSlug = groupName.replace(/[^a-zA-Z0-9]/g, '_').toLowerCase();
      html += `
        <tr class="group-header-row" id="group-header-${groupSlug}" onclick="window.appBridge.toggleAccordionGroup('${groupSlug}')" title="Clique para expandir ou recolher este grupo">
          <td colspan="5" class="group-header-title">
            <div style="display: flex; align-items: center; justify-content: space-between;">
              <span>
                <i class="ri-folder-shared-line" style="margin-right: 6px;"></i> Grupo: ${groupName} <span style="font-weight: 500; font-size: 11.5px; color: var(--ink-muted); margin-left: 6px;">(${jobs.length} robôs)</span>
              </span>
              <i class="ri-arrow-down-s-line group-header-chevron" id="chevron-${groupSlug}"></i>
            </div>
          </td>
        </tr>
      `;

      jobs.forEach(job => {
        const itemNumber = job.order ? `${job.order}. ` : '';
        html += `
          <tr class="job-item-row group-child-${groupSlug}">
            <td style="font-weight: 600; color: var(--ink-primary); padding-left: 28px;">
              ${itemNumber}${job.name}
            </td>
            <td><span class="badge-tag idle">${job.type}</span></td>
            <td>${job.last_run || 'Nunca'}</td>
            <td><span class="badge-tag ${job.status}" id="badge-${job.id}">${job.status === 'running' ? 'Executando...' : 'Pronto'}</span></td>
            <td style="text-align: right;">
              <button class="btn btn-primary" style="padding: 6px 14px; font-size: 12.5px;" id="btn-run-${job.id}" onclick="window.appBridge.openJobModal('${job.id}')">
                Executar <i class="ri-arrow-right-line"></i>
              </button>
            </td>
          </tr>
        `;
      });
    }

    tbody.innerHTML = html;
  },

  toggleAccordionGroup: function(groupSlug) {
    const header = document.getElementById(`group-header-${groupSlug}`);
    const rows = document.querySelectorAll(`.group-child-${groupSlug}`);
    if (!header || !rows) return;

    const isCollapsed = header.classList.toggle('collapsed');
    rows.forEach(row => {
      if (isCollapsed) {
        row.classList.add('collapsed');
      } else {
        row.classList.remove('collapsed');
      }
    });
  },

  // Modal de Detalhes e Disparo RPA
  selectedJobId: null,
  selectedJobFilePath: null,

  selectJobInputFile: function() {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.select_file) {
      window.pywebview.api.select_file().then(res => {
        if (res.success && res.data) {
          this.selectedJobFilePath = res.data;
          const inputEl = document.getElementById('modal-selected-file-path');
          if (inputEl) inputEl.value = res.data;
          this.appendLog('INFO', `Planilha selecionada para a automação: ${res.data}`);
        }
      });
    } else {
      alert('Seletor nativo disponível no aplicativo Desktop.');
    }
  },

  downloadModelSpreadsheet: function(templateType = 'data_necessidade') {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.download_template_excel) {
      this.appendLog('INFO', `Gerando planilha modelo [${templateType}] para download...`);
      window.pywebview.api.download_template_excel(templateType).then(res => {
        if (res.success && res.data) {
          this.appendLog('SUCCESS', `Planilha modelo salva com sucesso em: ${res.data.file_path}`);
          if (typeof Swal !== 'undefined') {
            Swal.fire({
              title: 'Planilha Modelo Baixada!',
              html: `O modelo contendo <b>${res.data.total_examples} exemplos práticos</b> foi gerado.<br><br><small style="color: var(--ink-muted); word-break: break-all;">Salvo em: ${res.data.file_path}</small>`,
              icon: 'success',
              confirmButtonText: 'OK'
            });
          } else {
            alert(`Planilha modelo salva em: ${res.data.file_path}`);
          }
        } else {
          const err = res.error?.message || 'Erro ao gerar planilha modelo.';
          this.appendLog('ERROR', `Falha no download da planilha modelo: ${err}`);
          if (typeof Swal !== 'undefined') {
            Swal.fire('Erro', err, 'error');
          }
        }
      }).catch(err => {
        this.appendLog('ERROR', `Erro de comunicação: ${err}`);
      });
    } else {
      alert('Download de planilha modelo disponível no aplicativo Desktop.');
    }
  },

  downloadCurrentJobTemplate: function() {
    const job = appState.jobs.find(j => j.id === this.selectedJobId);
    let tType = 'data_necessidade';
    if (job && job.template_type) {
      tType = job.template_type;
    } else if (this.selectedJobId === 'job_mat_concluir_requisicoes') {
      tType = 'concluir_requisicoes';
    } else if (this.selectedJobId === 'job_mat_eliminar_reserva') {
      tType = 'eliminar_reserva';
    }
    this.downloadModelSpreadsheet(tType);
  },

  openJobModal: function(jobId) {
    const job = appState.jobs.find(j => j.id === jobId);
    if (!job) return;

    this.selectedJobId = jobId;
    this.selectedJobFilePath = null;

    document.getElementById('modal-job-name').innerText = `${job.order ? job.order + ' ' : ''}${job.name}`;
    document.getElementById('modal-job-type').innerText = `${job.group ? job.group + ' · ' : ''}${job.type}`;
    document.getElementById('modal-job-description').innerText = job.description || 'Sem descrição cadastrada.';

    const fileSection = document.getElementById('modal-file-input-section');
    const filePathInput = document.getElementById('modal-selected-file-path');
    const colsHint = document.getElementById('modal-file-cols-hint');

    if (filePathInput) filePathInput.value = '';

    if (fileSection) {
      if (job.requires_file) {
        fileSection.style.display = 'block';
        if (colsHint) {
          if (job.file_hint) {
            colsHint.innerText = job.file_hint;
          } else if (jobId === 'job_mat_concluir_requisicoes') {
            colsHint.innerHTML = "Colunas exigidas: <b>Requisicao</b> e <b>Item</b>.";
          } else if (jobId === 'job_mat_eliminar_reserva') {
            colsHint.innerHTML = "Colunas exigidas: <b>Reserva</b> e <b>Item</b>.";
          } else {
            colsHint.innerHTML = "Colunas exigidas: <b>PEP</b>, <b>Diagrama</b> e <b>Data Necessidade</b>.";
          }
        }
      } else {
        fileSection.style.display = 'none';
      }
    }

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
    this.selectedJobFilePath = null;
  },

  startModalJob: function() {
    if (!this.selectedJobId) return;
    const jobId = this.selectedJobId;
    const job = appState.jobs.find(j => j.id === jobId);

    if (job && job.requires_file && !this.selectedJobFilePath) {
      if (typeof Swal !== 'undefined') {
        Swal.fire('Planilha Obrigatória', 'Por favor, selecione o arquivo Excel (.xlsx) antes de iniciar a automação.', 'warning');
      } else {
        alert('Por favor, selecione o arquivo Excel (.xlsx) antes de iniciar a automação.');
      }
      return;
    }

    const params = this.selectedJobFilePath ? { spreadsheet_path: this.selectedJobFilePath } : {};
    this.closeJobModal();
    this.runJob(jobId, params);
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

  formatDuration: function(seconds) {
    if (!seconds && seconds !== 0) return '0 min';
    const s = parseFloat(seconds);
    if (isNaN(s)) return seconds;
    const hours = Math.floor(s / 3600);
    const mins = Math.floor((s % 3600) / 60);
    const remSecs = Math.round(s % 60);
    if (hours > 0) {
      return `${hours}h ${mins}min ${remSecs > 0 ? remSecs + 's' : ''} (${(s / 60).toFixed(0)} min)`.trim();
    }
    if (mins === 0) {
      return `${remSecs}s (${(s / 60).toFixed(1)} min)`;
    }
    return `${mins} min ${remSecs > 0 ? remSecs + 's' : ''}`.trim();
  },

  renderHistoryTable: function() {
    const tbody = document.getElementById('history-tbody');
    if (!tbody) return;

    if (!appState.history || appState.history.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 24px; color: var(--ink-muted);">Nenhum histórico registrado no banco de dados.</td></tr>`;
      return;
    }

    tbody.innerHTML = appState.history.map((item, idx) => `
      <tr>
        <td>${item.timestamp || item.date}</td>
        <td style="font-weight: 600;">${item.job_name || item.name}</td>
        <td>${this.formatDuration(item.duration_seconds !== undefined ? item.duration_seconds : item.duration)}</td>
        <td>${item.items_processed || item.items || 0} itens</td>
        <td>
          <span class="badge-tag ${item.status === 'SUCCESS' || item.status === 'Concluído' ? 'completed' : (item.status === 'CANCELLED' ? 'idle' : 'failed')}">
            ${item.status}
          </span>
        </td>
        <td style="text-align: right;">
          <button class="btn btn-outline" style="padding: 5px 12px; font-size: 12px;" onclick="window.appBridge.openHistoryModal(${idx})">
            <i class="ri-eye-line"></i> Detalhes
          </button>
        </td>
      </tr>
    `).join('');
  },

  currentHistoryPeps: [],
  currentReportPeps: [],

  openHistoryModal: function(index) {
    const item = appState.history[index];
    if (!item) return;

    const modal = document.getElementById('history-detail-modal');
    if (!modal) return;

    document.getElementById('history-modal-title').innerText = `${item.job_name || 'Rotina'} (#${item.id || index + 1})`;
    document.getElementById('history-modal-subtitle').innerText = `Executado em: ${item.timestamp || item.date || 'Data não registrada'}`;

    const statusEl = document.getElementById('hm-status');
    const isSuccess = item.status === 'SUCCESS' || item.status === 'Concluído';
    const isCancelled = item.status === 'CANCELLED';

    statusEl.innerText = item.status;
    if (isSuccess) {
      statusEl.style.color = 'var(--color-success)';
    } else if (isCancelled) {
      statusEl.style.color = 'var(--color-warning)';
    } else {
      statusEl.style.color = 'var(--color-danger)';
    }

    const dur = item.duration_seconds !== undefined ? item.duration_seconds : item.duration;
    document.getElementById('hm-duration').innerText = this.formatDuration(dur);
    document.getElementById('hm-items').innerText = `${item.items_processed || item.items || 0} itens`;
    document.getElementById('hm-saved').innerText = `${item.time_saved_hours ? item.time_saved_hours + 'h' : '0.0h'}`;

    const genInfoEl = document.getElementById('hm-general-info');
    const meta = item.metadata || {};
    const dtInicio = meta.data_inicio || item.timestamp || item.date || 'N/A';
    const dtFim = meta.data_fim || item.timestamp || item.date || 'N/A';
    
    let motivoFinalizacao = meta.motivo_finalizacao;
    if (!motivoFinalizacao) {
      if (isSuccess) motivoFinalizacao = 'Concluído com Sucesso';
      else if (isCancelled) motivoFinalizacao = 'Cancelado pelo Operador';
      else motivoFinalizacao = item.error_message ? `Falha / Interrompido: ${item.error_message}` : 'Interrompido com Erro';
    }

    const sucessosCount = meta.itens_concluidos !== undefined ? meta.itens_concluidos : (item.items_processed || item.items || 0);
    const errosCount = meta.erros_contagem !== undefined ? meta.erros_contagem : 0;
    const totalTriados = meta.total_itens_triados || (sucessosCount + errosCount);
    const totalGrade = meta.total_grade ? ` (de um total de ${meta.total_grade} itens na grade do SAP)` : '';

    let infoHtml = `
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 8px 16px;">
        <div><b>Identificador do Job:</b> <code>${item.job_id || 'N/A'}</code></div>
        <div><b>Nome do Processo:</b> ${item.job_name || 'N/A'}</div>
        <div><b>Início da Execução:</b> <span style="color: var(--ink-primary); font-weight: 600;">${dtInicio}</span></div>
        <div><b>Término da Execução:</b> <span style="color: var(--ink-primary); font-weight: 600;">${dtFim}</span></div>
        <div style="grid-column: 1 / -1;"><b>Motivo / Tipo de Finalização:</b> <span style="font-weight: 600; color: ${isSuccess ? 'var(--color-success)' : (isCancelled ? 'var(--color-warning)' : 'var(--color-danger)')};">${motivoFinalizacao}</span></div>
        <div style="grid-column: 1 / -1; border-top: 1px dashed var(--line-border); padding-top: 6px; margin-top: 4px;">
          <b>Balanço do Período:</b> 
          <span style="color: var(--color-success); font-weight: 600;">${sucessosCount} com sucesso</span> | 
          <span style="color: var(--color-danger); font-weight: 600;">${errosCount} exceções</span> | 
          <b>${totalTriados} itens triados no total</b>${totalGrade}
        </div>
      </div>
    `;

    if (item.error_message) {
      infoHtml += `<div style="margin-top: 8px; color: var(--color-danger); border-top: 1px dashed var(--line-border); padding-top: 6px;"><b>Detalhes do Diagnóstico de Falha:</b> ${item.error_message}</div>`;
    }
    genInfoEl.innerHTML = infoHtml;

    // Renderização dos PEPs com Falha no Histórico
    const pepsContainer = document.getElementById('hm-peps-container');
    const pepsTable = document.getElementById('hm-peps-table');
    const falhas = (item.metadata && item.metadata.peps_com_falha) || [];
    this.currentHistoryPeps = falhas;

    if (pepsContainer && pepsTable) {
      if (falhas.length > 0) {
        pepsTable.innerHTML = this.buildPepsTableHtml(falhas);
        pepsContainer.style.display = 'block';
      } else {
        pepsContainer.style.display = 'none';
        pepsTable.innerHTML = '';
      }
    }

    const metaBox = document.getElementById('hm-metadata-box');
    if (item.metadata && Object.keys(item.metadata).length > 0) {
      metaBox.innerText = JSON.stringify(item.metadata, null, 2);
    } else {
      metaBox.innerText = '// Nenhum metadado adicional registrado para este lote.';
    }

    modal.classList.add('active');
  },

  closeHistoryModal: function() {
    const modal = document.getElementById('history-detail-modal');
    if (modal) modal.classList.remove('active');
  },

  exportHistoryPepsToExcel: function() {
    if (!this.currentHistoryPeps || this.currentHistoryPeps.length === 0) {
      if (typeof Swal !== 'undefined') {
        Swal.fire('Aviso', 'Não há PEPs com exceção registrados nesta execução.', 'info');
      }
      return;
    }
    this.executeExcelExport(this.currentHistoryPeps, 'Historico_PEPs_Falha');
  },

  exportReportPepsToExcel: function() {
    if (!this.currentReportPeps || this.currentReportPeps.length === 0) {
      if (typeof Swal !== 'undefined') {
        Swal.fire('Aviso', 'Não há PEPs com exceção registrados nesta execução.', 'info');
      }
      return;
    }
    this.executeExcelExport(this.currentReportPeps, 'Relatorio_PEPs_Falha');
  },

  executeExcelExport: function(pepsList, jobTag) {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.export_peps_to_excel) {
      this.appendLog('INFO', `Exportando ${pepsList.length} PEPs com falha para planilha Excel...`);
      window.pywebview.api.export_peps_to_excel(pepsList, jobTag).then(response => {
        if (response.success && response.data) {
          const res = response.data;
          this.appendLog('SUCCESS', `Planilha gerada com sucesso: ${res.file_path}`);
          if (typeof Swal !== 'undefined') {
            Swal.fire({
              title: 'Planilha Exportada!',
              html: `Foram exportados <b>${res.total_exported} PEPs</b> com sucesso.<br><br><small style="color: var(--ink-muted); word-break: break-all;">Salvo em: ${res.file_path}</small>`,
              icon: 'success',
              confirmButtonText: 'OK'
            });
          }
        } else {
          this.appendLog('ERROR', `Falha ao exportar Excel: ${response.error?.message}`);
          if (typeof Swal !== 'undefined') {
            Swal.fire('Erro na Exportação', response.error?.message || 'Falha ao salvar arquivo Excel.', 'error');
          }
        }
      }).catch(err => {
        this.appendLog('ERROR', `Erro de comunicação na exportação: ${err}`);
      });
    } else {
      alert('A exportação para Excel está disponível no aplicativo Desktop.');
    }
  },

  // 3. Execução de Robôs RPA com Contrato Padronizado, Progresso e Relatório
  activeRunningJobId: null,

  updateProgress: function(current, total) {
    const progressPanel = document.getElementById('rpa-progress-panel');
    const fillEl = document.getElementById('progress-fill-element');
    const metaText = document.getElementById('progress-meta-text');
    const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;

    if (progressPanel && fillEl && metaText) {
      progressPanel.classList.add('active');
      fillEl.style.width = `${pct}%`;
      metaText.innerText = `${current} / ${total} itens (${pct}%)`;
    }

    const studioTrack = document.getElementById('studio-progress-track');
    const studioFill = document.getElementById('studio-progress-fill');
    if (studioTrack && studioFill) {
      studioTrack.style.display = 'block';
      studioFill.style.width = `${pct}%`;
    }
  },

  cancelCurrentJob: function() {
    this.appendLog('WARNING', 'Operador solicitou cancelamento do robô...');
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.cancel_rpa_job().then(res => {
        this.appendLog('INFO', 'Comando de parada enviado ao executor.');
      });
    }
  },

  runJob: function(jobId, params = {}) {
    const job = appState.jobs.find(j => j.id === jobId);
    if (!job) return;

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
      window.pywebview.api.run_rpa_job(jobId, params).then(response => {
        if (response.success) {
          this.handleJobCompletion(jobId, response.data);
        } else {
          this.appendLog('ERROR', `Falha [${response.error?.code}]: ${response.error?.message}`);
          this.resetJobUI(jobId, 'failed');
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
        this.resetJobUI(jobId, 'failed');
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
    this.loadHistoryFromBackend();
    this.loadDashboardKPIs();
    this.showReportCard(data);
    this.activeRunningJobId = null;
  },

  resetJobUI: function(jobId, statusType) {
    const badge = document.getElementById(`badge-${jobId}`);
    const btn = document.getElementById(`btn-run-${jobId}`);
    if (badge) {
      if (statusType === 'completed') {
        badge.className = 'badge-tag completed';
        badge.innerText = 'Concluído';
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
    const savedEl = document.getElementById('report-kpi-saved');
    const notesEl = document.getElementById('report-detail-notes');

    const meta = data.metadata || {};
    const dtInicio = meta.data_inicio || 'Horário de disparo';
    const dtFim = meta.data_fim || 'Agora mesmo';
    const horasPoupadas = meta.horas_poupadas !== undefined ? `${meta.horas_poupadas}h` : (data.time_saved_hours ? `${data.time_saved_hours}h` : '0.0h');

    titleEl.innerText = `Relatório de Execução — ${data.job_name || 'Rotina RPA'}`;
    durationEl.innerText = this.formatDuration(data.duration_seconds || 0);
    processedEl.innerText = `${data.processed || 0}`;
    errorsEl.innerText = `${data.errors || 0}`;
    if (savedEl) savedEl.innerText = horasPoupadas;

    let balancoNotas = `<b>Início:</b> ${dtInicio} | <b>Fim:</b> ${dtFim}<br>`;

    if (isSuccess) {
      statusValEl.innerText = 'SUCESSO';
      statusValEl.style.color = 'var(--color-success)';
      iconEl.className = 'ri-checkbox-circle-fill';
      iconEl.style.color = 'var(--color-success)';
      subEl.innerText = 'Processo executado integralmente sem impedimentos.';
      notesEl.innerHTML = `${balancoNotas}Todas as ${data.processed || 0} operações foram auditadas com sucesso no sistema. Tempo economizado para o analista: <b>${horasPoupadas}</b>.`;
    } else if (isCancelled) {
      statusValEl.innerText = 'INTERROMPIDO';
      statusValEl.style.color = 'var(--color-warning)';
      iconEl.className = 'ri-alert-fill';
      iconEl.style.color = 'var(--color-warning)';
      subEl.innerText = 'A rotina foi cancelada pelo operador durante o processamento.';
      notesEl.innerHTML = `${balancoNotas}Operação pausada com segurança. <b>${data.processed || 0} itens</b> haviam sido gravados com sucesso antes da interrupção. O trabalho já realizado poupou cerca de <b>${horasPoupadas}</b> da equipe.`;
    } else {
      statusValEl.innerText = 'FALHA';
      statusValEl.style.color = 'var(--color-danger)';
      iconEl.className = 'ri-error-warning-fill';
      iconEl.style.color = 'var(--color-danger)';
      subEl.innerText = 'A execução encontrou um erro impeditivo ou queda de conexão.';
      notesEl.innerHTML = `${balancoNotas}${data.notes || 'Verifique o console de logs em tempo real para avaliar o diagnóstico técnico.'}<br>Itens triados até a parada: <b>${data.processed || 0}</b> (Tempo manual poupado: <b>${horasPoupadas}</b>).`;
    }

    // Exibição dos PEPs com Falha no Relatório Final
    const pepsContainer = document.getElementById('report-peps-container');
    const pepsTable = document.getElementById('report-peps-table');
    const falhas = data.peps_com_falha || (data.metadata && data.metadata.peps_com_falha) || [];
    this.currentReportPeps = falhas;

    if (pepsContainer && pepsTable) {
      if (falhas.length > 0) {
        pepsTable.innerHTML = this.buildPepsTableHtml(falhas);
        pepsContainer.style.display = 'block';
      } else {
        pepsContainer.style.display = 'none';
        pepsTable.innerHTML = '';
      }
    }

    reportPanel.classList.add('active');
    reportPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  },

  buildPepsTableHtml: function(pepsList) {
    if (!pepsList || pepsList.length === 0) return '';
    let rows = pepsList.map((p, idx) => `
      <tr style="border-bottom: 1px solid var(--line-soft); font-size: 12.5px;">
        <td style="padding: 8px 12px; font-weight: 600; color: var(--color-danger); font-family: var(--font-mono);">${p.pep || 'N/A'}</td>
        <td style="padding: 8px 12px; color: var(--ink-primary);">${p.material || 'N/A'}</td>
        <td style="padding: 8px 12px; color: var(--ink-muted); font-size: 11.5px;">${p.motivo || 'Erro no processamento'}</td>
      </tr>
    `).join('');

    return `
      <table style="width: 100%; border-collapse: collapse; text-align: left;">
        <thead>
          <tr style="background: #fafbfc; border-bottom: 1px solid var(--line-border); font-size: 11px; text-transform: uppercase; color: var(--ink-muted);">
            <th style="padding: 8px 12px;">Elemento PEP</th>
            <th style="padding: 8px 12px;">Material</th>
            <th style="padding: 8px 12px;">Motivo / Diagnóstico</th>
          </tr>
        </thead>
        <tbody>
          ${rows}
        </tbody>
      </table>
    `;
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

    line.innerHTML = `<span class="log-time">[${timeStr}]</span><span class="${colorClass}">[${norm}]</span> ${message}`;
    consoleBox.appendChild(line);
    consoleBox.scrollTop = consoleBox.scrollHeight;

    // O runner é o mesmo para robôs nativos e fluxos do Studio — espelha no console do
    // Studio também, pra funcionar não importa qual view estiver ativa no momento.
    const studioConsole = document.getElementById('studio-console-output');
    if (studioConsole) {
      const studioLine = line.cloneNode(true);
      studioConsole.appendChild(studioLine);
      studioConsole.scrollTop = studioConsole.scrollHeight;
    }
  },

  clearLogs: function() {
    const consoleBox = document.getElementById('rpa-console-output');
    if (consoleBox) consoleBox.innerHTML = '';
  },

  copyConsoleLogs: function() {
    const consoleBox = document.getElementById('rpa-console-output');
    if (!consoleBox) return;

    const lines = consoleBox.querySelectorAll('.log-line');
    if (!lines || lines.length === 0) {
      if (typeof Swal !== 'undefined') {
        Swal.fire('Console Vazio', 'Não há registros de log para copiar no momento.', 'info');
      }
      return;
    }

    const logTexts = [];
    lines.forEach(lineEl => {
      // Extrair o texto limpo de cada linha de log
      logTexts.push(lineEl.innerText.trim());
    });
    const fullLog = logTexts.join('\n');

    // Tenta primeiro via API Desktop Python (bridge) para máxima confiabilidade
    if (window.pywebview && window.pywebview.api && window.pywebview.api.copy_to_clipboard) {
      window.pywebview.api.copy_to_clipboard(fullLog).then(res => {
        if (res && res.success) {
          if (typeof Swal !== 'undefined') {
            const Toast = Swal.mixin({
              toast: true,
              position: 'top-end',
              showConfirmButton: false,
              timer: 2500,
              timerProgressBar: true
            });
            Toast.fire({
              icon: 'success',
              title: `Copiado! (${lines.length} linhas)`
            });
          } else {
            alert('Logs copiados para a área de transferência!');
          }
        } else {
          this._fallbackBrowserCopy(fullLog, lines.length);
        }
      }).catch(() => {
        this._fallbackBrowserCopy(fullLog, lines.length);
      });
    } else {
      this._fallbackBrowserCopy(fullLog, lines.length);
    }
  },

  _fallbackBrowserCopy: function(text, totalLines) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(() => {
        if (typeof Swal !== 'undefined') {
          const Toast = Swal.mixin({
            toast: true,
            position: 'top-end',
            showConfirmButton: false,
            timer: 2500,
            timerProgressBar: true
          });
          Toast.fire({
            icon: 'success',
            title: `Copiado! (${totalLines} linhas)`
          });
        }
      }).catch(() => {
        this._execCommandCopy(text);
      });
    } else {
      this._execCommandCopy(text);
    }
  },

  _execCommandCopy: function(text) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand('copy');
      if (typeof Swal !== 'undefined') {
        const Toast = Swal.mixin({
          toast: true,
          position: 'top-end',
          showConfirmButton: false,
          timer: 2500,
          timerProgressBar: true
        });
        Toast.fire({
          icon: 'success',
          title: 'Logs copiados para a área de transferência!'
        });
      }
    } catch (e) {
      alert('Não foi possível copiar os logs automaticamente.');
    }
    document.body.removeChild(textarea);
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
            text.innerText = `Base Demonstrativa: ${data.total_rows} linhas, ${data.total_anomalies} anomalias detectadas. Média: R$ ${data.avg_ticket}.`;
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
                text.innerText = `Arquivo Analisado: ${filePath} (${data.total_rows} linhas).`;
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

  // Filtro de período do Dashboard (padrão: Mês Atual)
  dashboardDateFilter: {
    startDate: null,
    endDate: null
  },

  initDashboardDates: function() {
    const now = new Date();
    const year = now.getFullYear();
    const month = String(now.getMonth() + 1).padStart(2, '0');
    // Primeiro dia do mês atual
    const firstDay = `${year}-${month}-01`;
    // Último dia do mês atual
    const lastDayDate = new Date(year, now.getMonth() + 1, 0);
    const lastDay = `${year}-${month}-${String(lastDayDate.getDate()).padStart(2, '0')}`;

    const startInput = document.getElementById('dash-filter-start');
    const endInput = document.getElementById('dash-filter-end');
    if (startInput && endInput) {
      startInput.value = firstDay;
      endInput.value = lastDay;
    }
    this.dashboardDateFilter.startDate = firstDay;
    this.dashboardDateFilter.endDate = lastDay;
    this.updateDashboardPeriodLabel();
  },

  updateDashboardPeriodLabel: function() {
    const labelEl = document.getElementById('dashboard-period-label');
    const chartTitleEl = document.getElementById('activity-chart-title');
    if (!labelEl) return;

    if (!this.dashboardDateFilter.startDate && !this.dashboardDateFilter.endDate) {
      labelEl.innerText = 'Exibindo Histórico Geral (Todo o período)';
      if (chartTitleEl) chartTitleEl.innerText = 'Volume de Execuções e Itens (Geral)';
      return;
    }

    const startStr = this.dashboardDateFilter.startDate ? this.formatDateBR(this.dashboardDateFilter.startDate) : 'Início';
    const endStr = this.dashboardDateFilter.endDate ? this.formatDateBR(this.dashboardDateFilter.endDate) : 'Hoje';
    labelEl.innerText = `Filtrado de ${startStr} até ${endStr}`;
    if (chartTitleEl) chartTitleEl.innerText = `Volume no Período (${startStr} a ${endStr})`;
  },

  formatDateBR: function(isoDateStr) {
    if (!isoDateStr) return '';
    const parts = isoDateStr.split('-');
    if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
    return isoDateStr;
  },

  applyDashboardDateFilter: function() {
    const startInput = document.getElementById('dash-filter-start');
    const endInput = document.getElementById('dash-filter-end');
    const startVal = startInput ? startInput.value : '';
    const endVal = endInput ? endInput.value : '';

    if (startVal && endVal && startVal > endVal) {
      if (typeof Swal !== 'undefined') {
        Swal.fire('Data Inválida', 'A data inicial não pode ser superior à data final.', 'warning');
      } else {
        alert('A data inicial não pode ser superior à data final.');
      }
      return;
    }

    this.dashboardDateFilter.startDate = startVal || null;
    this.dashboardDateFilter.endDate = endVal || null;
    this.updateDashboardPeriodLabel();
    this.loadDashboardKPIs();
    this.appendLog('INFO', `Filtro do dashboard aplicado: ${startVal || '...'} até ${endVal || '...'}`);
  },

  setDashboardCurrentMonth: function() {
    this.initDashboardDates();
    this.loadDashboardKPIs();
  },

  resetDashboardDateFilter: function() {
    const startInput = document.getElementById('dash-filter-start');
    const endInput = document.getElementById('dash-filter-end');
    if (startInput) startInput.value = '';
    if (endInput) endInput.value = '';
    this.dashboardDateFilter.startDate = null;
    this.dashboardDateFilter.endDate = null;
    this.updateDashboardPeriodLabel();
    this.loadDashboardKPIs();
    this.appendLog('INFO', 'Filtro de período limpo: exibindo histórico total.');
  },

  loadDashboardKPIs: function() {
    if (window.pywebview && window.pywebview.api) {
      const sDate = this.dashboardDateFilter.startDate;
      const eDate = this.dashboardDateFilter.endDate;

      if (window.pywebview.api.get_system_kpis) {
        window.pywebview.api.get_system_kpis(sDate, eDate).then(response => {
          if (response.success && response.data) {
            const kpis = response.data;
            const kpiExecEl = document.getElementById('kpi-exec-count');
            const kpiTimeEl = document.getElementById('kpi-time-saved');
            const kpiRateEl = document.getElementById('kpi-success-rate');
            const kpiRowsEl = document.getElementById('kpi-rows-analyzed');

            if (kpiExecEl) kpiExecEl.innerText = (kpis.total_jobs || 0).toLocaleString('pt-BR');
            if (kpiTimeEl) kpiTimeEl.innerText = `${kpis.time_saved_hours || 0}h`;
            if (kpiRateEl) kpiRateEl.innerText = `${kpis.success_rate || 0}%`;
            if (kpiRowsEl) kpiRowsEl.innerText = (kpis.total_items || 0).toLocaleString('pt-BR');
          }
        });
      }

      if (window.pywebview.api.get_dashboard_chart_data) {
        window.pywebview.api.get_dashboard_chart_data(sDate, eDate).then(response => {
          if (response.success && response.data && typeof window.renderUpdatedDashboardCharts === 'function') {
            window.renderUpdatedDashboardCharts(response.data);
          }
        });
      }
    }
  },

  refreshData: function() {
    this.appendLog('INFO', 'Recarregando robôs, histórico e indicadores...');
    this.loadJobsFromBackend();
    this.loadHistoryFromBackend();
    this.loadDashboardKPIs();
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
  window.appBridge.initDashboardDates();
  window.appBridge.loadJobsFromBackend();
  window.appBridge.loadHistoryFromBackend();
  window.appBridge.loadDashboardKPIs();
});

// Evento disparado pelo pywebview quando a injeção da API Python estiver concluída
window.addEventListener('pywebviewready', () => {
  if (window.appBridge) {
    window.appBridge.initDashboardDates();
    window.appBridge.loadJobsFromBackend();
    window.appBridge.loadHistoryFromBackend();
    window.appBridge.loadDashboardKPIs();
  }
});



