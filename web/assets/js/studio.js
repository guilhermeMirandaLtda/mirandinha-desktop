// Studio — editor visual de automações (Etapa 3)
// Canvas via Drawflow (vendorizado, sem build step). O grafo é dado — este arquivo só
// desenha e chama a bridge; validar e executar é sempre trabalho do Python
// (core/studio/validator.py, core/rpa/tasks/graph_task.py).

const STUDIO_CATEGORY_SLUG = {
  'Sessão & fluxo': 'sessao',
  'Interação de tela': 'tela',
  'Grid / ALV': 'grid',
  'Robustez': 'robustez',
  'Lógica & dados': 'logica',
  'Dados': 'dados'
};

const STUDIO_ON_ERROR_CHIP = {
  abort: 'danger',
  skip_item: 'warn',
  continue: 'success',
  route: 'info'
};

function studioEscapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

window.studioBridge = {
  catalog: {},
  editor: null,
  currentGraph: null,
  currentSource: null,
  idMap: {},
  reverseIdMap: {},
  selectedNodeId: null,
  currentFlowMeta: null, // {is_published} — só existe quando a origem é 'flow' (já salvo)
  _catalogLoaded: false,
  _editorInitialized: false,

  // ---- ciclo de vida da view: galeria (lista) <-> editor (canvas cheio) ----

  init: function() {
    if (!window.pywebview || !window.pywebview.api) {
      const grid = document.getElementById('studio-gallery-grid');
      if (grid) grid.innerHTML = '<div class="studio-source-empty"><i class="ri-error-warning-line"></i> O Studio precisa do aplicativo desktop rodando (pywebview) — não funciona numa aba de navegador solta.</div>';
      return;
    }

    if (!this._catalogLoaded) {
      this._catalogLoaded = true;
      this.loadCatalog();
    }

    this.showGallery();
  },

  loadCatalog: function() {
    window.pywebview.api.studio_node_catalog().then(res => {
      if (res.success) this.catalog = res.data;
    });
  },

  // Ponto de entrada: uma tela só de fluxos escolhíveis — o canvas fica cheio pro fluxo
  // aberto, sem uma coluna lateral disputando espaço com ele o tempo todo.
  showGallery: function() {
    const gallery = document.getElementById('studio-gallery-view');
    const editor = document.getElementById('studio-editor-view');
    if (editor) editor.style.display = 'none';
    if (gallery) gallery.style.display = 'block';
    this.renderGallery();
  },

  showEditor: function() {
    const gallery = document.getElementById('studio-gallery-view');
    const editor = document.getElementById('studio-editor-view');
    if (gallery) gallery.style.display = 'none';
    if (editor) editor.style.display = 'block';

    // Drawflow precisa do container já visível (dimensões reais) — cria só na primeira
    // vez que o editor realmente aparece, nunca enquanto ainda está com display:none.
    if (!this._editorInitialized) {
      this._editorInitialized = true;
      const container = document.getElementById('studio-drawflow');
      this.editor = new Drawflow(container);
      this.editor.reroute = true;
      this.editor.start();
      this.editor.on('nodeSelected', (id) => this.onNodeSelected(id));
      this.editor.on('nodeUnselected', () => this.showInspectorEmpty());
    }
  },

  renderGallery: function() {
    const container = document.getElementById('studio-gallery-grid');
    if (!container) return;

    Promise.all([
      window.pywebview.api.studio_list_samples(),
      window.pywebview.api.studio_list_flows(),
      window.pywebview.api.studio_list_team_library(),
    ]).then(([samplesRes, flowsRes, teamRes]) => {
      let html = '';

      if (samplesRes.success && samplesRes.data.length > 0) {
        html += '<div class="studio-gallery-section-title">Exemplos</div>';
        html += samplesRes.data.map(s => this.galleryCard({
          kind: 'sample', ref: s.file, name: s.name,
          meta: s.transacao || 'sem transação',
          desc: s.description || 'Grafo de exemplo empacotado com o app.',
          chipClass: 'brand', chipLabel: 'exemplo',
        })).join('');
      }

      if (flowsRes.success && flowsRes.data.length > 0) {
        html += '<div class="studio-gallery-section-title">Meus fluxos</div>';
        html += flowsRes.data.map(f => this.galleryCard({
          kind: 'flow', ref: f.flow_id, name: f.name,
          meta: f.transacao || f.group_name || 'Studio',
          desc: `Atualizado em ${f.updated_at || '—'}`,
          chipClass: f.is_published ? 'success' : 'warn',
          chipLabel: f.is_published ? 'publicado' : 'rascunho',
        })).join('');
      }

      html += `<div class="studio-gallery-section-title">Biblioteca da equipe
        <a href="javascript:void(0)" onclick="window.studioBridge.configureTeamLibrary(event)"
           style="font-weight:400;text-transform:none;letter-spacing:0;margin-left:10px;color:var(--brand-primary);cursor:pointer;">
          configurar pasta
        </a>
      </div>`;
      if (teamRes.success && teamRes.data.length > 0) {
        html += teamRes.data.map(f => this.galleryCard({
          kind: 'team', ref: f.file_path, name: f.name,
          meta: f.transacao || 'Studio',
          desc: f.summary.elimina_ou_exclui
            ? '⚠ elimina ou exclui dados no SAP'
            : (f.summary.grava ? 'Grava no SAP' : 'Só leitura'),
          chipClass: f.summary.elimina_ou_exclui ? 'danger' : 'info', chipLabel: 'equipe',
        })).join('');
      } else {
        html += '<div class="studio-source-empty">Nenhuma pasta configurada ainda, ou nenhum .mirflow.json nela.</div>';
      }

      container.innerHTML = html;
    });
  },

  galleryCard: function(opts) {
    const clickAction = opts.kind === 'team'
      ? `window.studioBridge.importFromTeamLibrary('${studioEscapeHtml(opts.ref)}')`
      : `window.studioBridge.openFromGallery('${opts.kind}', '${studioEscapeHtml(opts.ref)}')`;
    return `
      <div class="studio-gallery-card" onclick="${clickAction}">
        <div class="studio-gallery-card-head">
          <span class="studio-chip ${opts.chipClass}">${studioEscapeHtml(opts.chipLabel)}</span>
          <span class="mono" style="font-size:10.5px;color:var(--ink-muted);">${studioEscapeHtml(opts.meta)}</span>
        </div>
        <div class="studio-gallery-card-name">${studioEscapeHtml(opts.name)}</div>
        <div class="studio-gallery-card-desc">${studioEscapeHtml(opts.desc)}</div>
      </div>
    `;
  },

  configureTeamLibrary: function(evt) {
    if (evt) evt.stopPropagation();
    window.pywebview.api.studio_select_team_library_folder().then(res => {
      if (!res.success) {
        window.appBridge.appendLog('ERROR', `Falha ao selecionar a pasta: ${res.error.message}`);
        return;
      }
      if (!res.data) return; // cancelou o diálogo
      window.appBridge.appendLog('SUCCESS', `Pasta da biblioteca da equipe configurada: ${res.data}`);
      this.renderGallery();
    });
  },

  importFromTeamLibrary: function(filePath) {
    window.pywebview.api.studio_inspect_mirflow(filePath).then(res => {
      if (!res.success) {
        window.appBridge.appendLog('ERROR', `Falha ao ler o arquivo: ${res.error.message}`);
        return;
      }
      this._confirmImport(filePath, res.data);
    });
  },

  openFromGallery: function(kind, ref) {
    this.showEditor(); // primeiro garante o container visível e o editor criado
    this.selectSource(kind, ref);
  },

  // ---- carregar um fluxo no canvas ----

  selectSource: function(kind, ref) {
    if (kind === 'sample') {
      window.pywebview.api.studio_load_sample(ref).then(res => {
        if (!res.success) {
          window.appBridge.appendLog('ERROR', `Falha ao carregar exemplo: ${res.error.message}`);
          return;
        }
        this.currentSource = { kind: kind, ref: ref };
        this.currentFlowMeta = null; // exemplo ainda não foi salvo — sem status de publicação
        this.loadGraphIntoCanvas(res.data);
        this.renderPublishStatus();
      });
      return;
    }

    window.pywebview.api.studio_get_flow(ref).then(res => {
      if (!res.success) {
        window.appBridge.appendLog('ERROR', `Falha ao carregar fluxo: ${res.error.message}`);
        return;
      }
      this.currentSource = { kind: kind, ref: ref };
      this.currentFlowMeta = { is_published: !!res.data.is_published };
      this.loadGraphIntoCanvas(res.data.graph);
      this.renderPublishStatus();
    });
  },

  renderPublishStatus: function() {
    const el = document.getElementById('studio-publish-status');
    if (!el) return;
    if (!this.currentFlowMeta) {
      el.style.display = 'none';
      return;
    }
    el.style.display = 'inline-block';
    if (this.currentFlowMeta.is_published) {
      el.className = 'studio-chip success';
      el.innerText = 'publicado';
    } else {
      el.className = 'studio-chip warn';
      el.innerText = 'rascunho';
    }
  },

  loadGraphIntoCanvas: function(graph) {
    this.currentGraph = graph;
    this.idMap = {};
    this.reverseIdMap = {};
    this.selectedNodeId = null;
    this.showInspectorEmpty();
    this.clearTraceStates();

    const emptyEl = document.getElementById('studio-canvas-empty');
    if (emptyEl) emptyEl.style.display = 'none';

    const nameEl = document.getElementById('studio-flow-name');
    const idEl = document.getElementById('studio-flow-id');
    if (nameEl) nameEl.innerText = graph.name || graph.flow_id || 'Fluxo sem nome';
    if (idEl) idEl.innerText = graph.flow_id ? `· ${graph.flow_id}` : '';

    this.editor.clear();

    const nodesById = {};
    (graph.nodes || []).forEach(n => { nodesById[n.id] = n; });

    (graph.nodes || []).forEach(node => {
      const spec = this.catalog[node.type] || { ports: ['out'], category: 'Interação de tela', label: node.type };
      const ports = spec.ports || [];
      const inputsCount = node.type === 'flow.start' ? 0 : 1;
      const catSlug = STUDIO_CATEGORY_SLUG[spec.category] || 'tela';
      const cssClass = `df-node df-cat-${catSlug}`;
      const html = this.nodeHtml(node, spec);
      const pos = node.position || { x: 0, y: 0 };

      const dfId = this.editor.addNode(
        node.type, inputsCount, ports.length, pos.x, pos.y, cssClass, { mirId: node.id }, html, false
      );
      this.idMap[node.id] = dfId;
      this.reverseIdMap[dfId] = node.id;
    });

    (graph.edges || []).forEach(edge => {
      const fromNode = nodesById[edge.from];
      if (!fromNode) return;
      const spec = this.catalog[fromNode.type] || { ports: ['out'] };
      const ports = spec.ports && spec.ports.length ? spec.ports : ['out'];
      const portIdx = ports.indexOf(edge.port || 'out');
      const outputSlot = 'output_' + (portIdx >= 0 ? portIdx + 1 : 1);
      const fromDf = this.idMap[edge.from];
      const toDf = this.idMap[edge.to];
      if (fromDf === undefined || toDf === undefined) return;
      try {
        this.editor.addConnection(fromDf, toDf, outputSlot, 'input_1');
      } catch (e) {
        // aresta pra uma porta que o nó não tem no catálogo — não derruba o resto do render
      }
    });
  },

  nodeHtml: function(node, spec) {
    const label = studioEscapeHtml(node.label || spec.label || node.type);
    const typeLabel = studioEscapeHtml(spec.label || node.type);
    return `<div class="df-node-inner"><div class="df-node-type">${typeLabel}</div><div class="df-node-label">${label}</div></div>`;
  },

  // ---- inspetor (somente leitura, Etapa 3) ----

  onNodeSelected: function(dfId) {
    const nodeId = this.reverseIdMap[dfId];
    if (!nodeId || !this.currentGraph) return;
    this.selectedNodeId = nodeId;
    const node = (this.currentGraph.nodes || []).find(n => n.id === nodeId);
    if (node) this.renderInspector(node);
  },

  renderInspector: function(node) {
    const spec = this.catalog[node.type] || {};
    const container = document.getElementById('studio-inspector');
    if (!container) return;

    const paramsRows = Object.entries(node.params || {}).map(([key, value]) => {
      let displayVal;
      if (value && typeof value === 'object' && value.pack && value.ref) {
        displayVal = `<span class="studio-chip brand">${studioEscapeHtml(value.pack)}</span>&nbsp;.&nbsp;${studioEscapeHtml(value.ref)}`;
      } else if (typeof value === 'object') {
        displayVal = `<span class="studio-inspector-value mono">${studioEscapeHtml(JSON.stringify(value))}</span>`;
      } else {
        displayVal = studioEscapeHtml(String(value));
      }
      return `<tr><td>${studioEscapeHtml(key)}</td><td>${displayVal}</td></tr>`;
    }).join('');

    const onErrorClass = STUDIO_ON_ERROR_CHIP[node.on_error] || 'brand';
    const onErrorHtml = node.on_error
      ? `<span class="studio-chip ${onErrorClass}">${studioEscapeHtml(node.on_error)}</span>`
      : '<span class="studio-inspector-value">—</span>';

    container.innerHTML = `
      <div class="studio-inspector">
        <div class="studio-inspector-row">
          <div class="studio-inspector-label">Rótulo</div>
          <div class="studio-inspector-value">${studioEscapeHtml(node.label || '—')}</div>
        </div>
        <div class="studio-inspector-row">
          <div class="studio-inspector-label">Tipo</div>
          <div class="studio-inspector-value mono">${studioEscapeHtml(spec.label || node.type)}</div>
        </div>
        <div class="studio-inspector-row">
          <div class="studio-inspector-label">Categoria</div>
          <div class="studio-inspector-value">${studioEscapeHtml(spec.category || '—')}</div>
        </div>
        <div class="studio-inspector-row">
          <div class="studio-inspector-label">on_error</div>
          <div class="studio-inspector-value">${onErrorHtml}</div>
        </div>
        ${paramsRows ? `
        <div class="studio-inspector-row">
          <div class="studio-inspector-label">Parâmetros</div>
          <table class="studio-param-table">${paramsRows}</table>
        </div>` : ''}
        ${node.needs_review ? '<div class="studio-inspector-row"><span class="studio-chip warn">pendente de revisão</span></div>' : ''}
      </div>
    `;
  },

  showInspectorEmpty: function() {
    const container = document.getElementById('studio-inspector');
    if (container) container.innerHTML = '<div class="studio-inspector-empty">Clique num bloco do canvas para ver os detalhes.</div>';
  },

  // ---- validar / salvar / executar ----

  validateCurrentFlow: function() {
    if (!this.currentGraph) { this._noFlowWarning(); return; }
    window.pywebview.api.studio_validate_flow(this.currentGraph).then(res => {
      if (!res.success) {
        window.appBridge.appendLog('ERROR', `Falha ao validar: ${res.error.message}`);
        return;
      }
      const ok = res.data.ok;
      const issues = res.data.issues || [];

      if (ok && issues.length === 0) {
        window.appBridge.appendLog('SUCCESS', 'Validação: grafo sem problemas.');
        if (typeof Swal !== 'undefined') {
          Swal.fire({ icon: 'success', title: 'Grafo válido', text: 'Nenhum problema encontrado.', confirmButtonColor: '#7A70BA' });
        }
        return;
      }

      issues.forEach(i => {
        const level = i.severity === 'error' ? 'ERROR' : 'WARNING';
        window.appBridge.appendLog(level, `[${i.node_id || '—'}] ${i.message}`);
      });

      if (typeof Swal !== 'undefined') {
        const html = issues.map(i => {
          const color = i.severity === 'error' ? '#C6164F' : '#B67A1E';
          const nodeTag = i.node_id ? `[${studioEscapeHtml(i.node_id)}] ` : '';
          return `<div style="text-align:left;margin-bottom:6px;font-size:13px;"><b style="color:${color}">${i.severity.toUpperCase()}</b> ${nodeTag}${studioEscapeHtml(i.message)}</div>`;
        }).join('');
        Swal.fire({ icon: ok ? 'warning' : 'error', title: ok ? 'Avisos encontrados' : 'Grafo inválido', html: html, confirmButtonColor: '#7A70BA' });
      }
    });
  },

  saveCurrentFlow: function() {
    if (!this.currentGraph) { this._noFlowWarning(); return; }
    window.pywebview.api.studio_save_flow(this.currentGraph).then(res => {
      if (!res.success) {
        window.appBridge.appendLog('ERROR', `Falha ao salvar: ${res.error.message}`);
        if (typeof Swal !== 'undefined') Swal.fire('Não foi possível salvar', res.error.message || '', 'error');
        return;
      }
      window.appBridge.appendLog('SUCCESS', `Fluxo salvo: ${this.currentGraph.flow_id}`);
      this.renderGallery();
    });
  },

  publishCurrentFlow: function() {
    if (!this.currentGraph) { this._noFlowWarning(); return; }
    const flowId = this.currentGraph.flow_id;

    // Publicar sempre salva primeiro — garante que o que vira código executável é
    // exatamente o que está no canvas neste momento, não uma versão anterior no banco.
    window.pywebview.api.studio_save_flow(this.currentGraph).then(saveRes => {
      if (!saveRes.success) {
        window.appBridge.appendLog('ERROR', `Falha ao salvar antes de publicar: ${saveRes.error.message}`);
        return;
      }
      window.pywebview.api.studio_publish_flow(flowId, true).then(res => {
        if (!res.success) {
          window.appBridge.appendLog('ERROR', `Não foi possível publicar: ${res.error.message}`);
          if (typeof Swal !== 'undefined') {
            Swal.fire('Não foi possível publicar', res.error.message || 'O fluxo tem problemas de validação.', 'error');
          }
          return;
        }
        window.appBridge.appendLog('SUCCESS', `Fluxo publicado: ${flowId} — já aparece na Central de Robôs.`);
        this.currentSource = { kind: 'flow', ref: flowId };
        this.currentFlowMeta = { is_published: true };
        this.renderPublishStatus();
        this.renderGallery();
        if (typeof Swal !== 'undefined') {
          Swal.fire({ icon: 'success', title: 'Publicado!', text: 'O fluxo já aparece na Central de Robôs RPA.', confirmButtonColor: '#7A70BA' });
        }
      });
    });
  },

  runCurrentFlow: function() {
    if (!this.currentGraph) { this._noFlowWarning(); return; }

    const needsFile = (this.currentGraph.nodes || []).some(n => n.type === 'data.excel_read');
    const hasPath = this.currentGraph.variables && this.currentGraph.variables.spreadsheet_path;

    if (needsFile && !hasPath) {
      window.pywebview.api.select_file().then(res => {
        if (!res.success || !res.data) {
          window.appBridge.appendLog('WARNING', 'Execução cancelada: nenhuma planilha selecionada.');
          return;
        }
        this._executeFlow({ spreadsheet_path: res.data });
      });
      return;
    }

    this._executeFlow({});
  },

  _executeFlow: function(params) {
    this.clearTraceStates();
    const btn = document.getElementById('studio-run-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<i class="ri-loader-4-line ri-spin"></i> Executando...'; }

    window.appBridge.appendLog('INFO', `Executando fluxo do Studio: ${this.currentGraph.name || this.currentGraph.flow_id}...`);

    window.pywebview.api.studio_run_flow(this.currentGraph, params).then(res => {
      this._resetRunButton(btn);

      if (!res.success) {
        window.appBridge.appendLog('ERROR', `Falha na execução: ${res.error.message}`);
        if (typeof Swal !== 'undefined') Swal.fire('Falha na execução', res.error.message || '', 'error');
        return;
      }

      const data = res.data;
      const icon = data.status === 'SUCCESS' ? 'success' : (data.status === 'CANCELLED' ? 'warning' : 'error');
      const level = data.status === 'SUCCESS' ? 'SUCCESS' : 'WARNING';
      window.appBridge.appendLog(level, `Fluxo finalizado: ${data.status} — ${data.processed} processado(s), ${data.errors} erro(s) em ${data.duration_seconds}s.`);

      if (typeof Swal !== 'undefined') {
        Swal.fire({
          icon: icon, title: `Fluxo ${data.status}`,
          text: `${data.processed} processado(s) · ${data.errors} erro(s) · ${data.duration_seconds}s`,
          confirmButtonColor: '#7A70BA'
        });
      }

      if (window.appBridge.loadHistoryFromBackend) window.appBridge.loadHistoryFromBackend();
      if (window.appBridge.loadDashboardKPIs) window.appBridge.loadDashboardKPIs();
    }).catch(err => {
      this._resetRunButton(btn);
      window.appBridge.appendLog('ERROR', `Exceção de comunicação: ${err}`);
    });
  },

  _resetRunButton: function(btn) {
    if (btn) { btn.disabled = false; btn.innerHTML = '<i class="ri-play-circle-line"></i> Executar'; }
    const track = document.getElementById('studio-progress-track');
    if (track) track.style.display = 'none';
  },

  _noFlowWarning: function() {
    if (typeof Swal !== 'undefined') {
      Swal.fire('Nenhum fluxo carregado', 'Escolha um exemplo ou um fluxo salvo à esquerda primeiro.', 'warning');
    }
  },

  clearConsole: function() {
    const box = document.getElementById('studio-console-output');
    if (box) box.innerHTML = '';
  },

  // ---- compartilhar (Etapa 6) ----

  exportCurrentFlow: function() {
    if (!this.currentGraph) { this._noFlowWarning(); return; }
    window.pywebview.api.studio_export_flow(this.currentGraph).then(res => {
      if (!res.success) {
        window.appBridge.appendLog('ERROR', `Falha ao exportar: ${res.error.message}`);
        return;
      }
      if (res.data.cancelled) return; // usuário fechou o diálogo de salvar

      const packs = res.data.packs_incluidos || [];
      const packsMsg = packs.length ? `Packs incluídos: ${packs.join(', ')}.` : 'Nenhum pack de tela referenciado.';
      window.appBridge.appendLog('SUCCESS', `Fluxo exportado para: ${res.data.file_path}. ${packsMsg}`);
      if (typeof Swal !== 'undefined') {
        Swal.fire({
          icon: 'success', title: 'Fluxo exportado',
          html: `Salvo em:<br><code style="font-size:11px;">${studioEscapeHtml(res.data.file_path)}</code><br><br>${studioEscapeHtml(packsMsg)}`,
          confirmButtonColor: '#7A70BA',
        });
      }
    });
  },

  importFlow: function() {
    window.pywebview.api.studio_select_import_file().then(selRes => {
      if (!selRes.success || !selRes.data) return; // cancelou o diálogo
      const filePath = selRes.data;

      window.pywebview.api.studio_inspect_mirflow(filePath).then(res => {
        if (!res.success) {
          window.appBridge.appendLog('ERROR', `Falha ao ler o arquivo: ${res.error.message}`);
          if (typeof Swal !== 'undefined') Swal.fire('Não foi possível ler o arquivo', res.error.message || '', 'error');
          return;
        }
        this._confirmImport(filePath, res.data);
      });
    });
  },

  _confirmImport: function(filePath, inspection) {
    const s = inspection.summary;
    const errors = (inspection.validation.issues || []).filter(i => i.severity === 'error');

    const rows = [];
    rows.push(`<div><b>Transações:</b> ${s.transacoes.length ? studioEscapeHtml(s.transacoes.join(', ')) : '—'}</div>`);
    rows.push(`<div><b>Grava no SAP:</b> ${s.grava ? '<span style="color:#B67A1E;">sim</span>' : 'não'}</div>`);
    rows.push(`<div><b>Elimina / exclui:</b> ${s.elimina_ou_exclui ? '<span style="color:#C6164F;font-weight:600;">sim — confira com atenção</span>' : 'não'}</div>`);
    if (s.insumos && s.insumos.length) {
      s.insumos.forEach(i => rows.push(`<div><b>Planilha exigida:</b> colunas ${studioEscapeHtml((i.colunas || []).join(', '))}</div>`));
    }
    if (inspection.packs_faltando_localmente && inspection.packs_faltando_localmente.length) {
      rows.push(`<div><b>Packs a instalar:</b> ${studioEscapeHtml(inspection.packs_faltando_localmente.join(', '))}</div>`);
    }
    if (s.needs_review_node_ids && s.needs_review_node_ids.length) {
      rows.push(`<div style="color:#B67A1E;"><b>${s.needs_review_node_ids.length} bloco(s)</b> pendente(s) de revisão.</div>`);
    }
    if (errors.length) {
      rows.push(`<div style="color:#C6164F;"><b>${errors.length} problema(s) de validação</b> — o fluxo chega como rascunho mesmo assim, mas não poderá ser publicado até corrigir.</div>`);
    }
    if (inspection.flow_id_ja_existe) {
      rows.push(`<div style="color:#B67A1E;"><b>Atenção:</b> já existe um fluxo salvo com este id — importar substitui o rascunho local (a versão anterior fica no histórico) e derruba a publicação, se estava publicado.</div>`);
    }

    const html = `
      <div style="text-align:left;font-size:13px;line-height:1.7;">
        <div style="margin-bottom:8px;"><b>${studioEscapeHtml(inspection.graph.name || inspection.graph.flow_id)}</b></div>
        ${rows.join('')}
        <div style="margin-top:10px;color:#8E8D9A;font-size:11.5px;">O fluxo importado chega sempre como rascunho — nunca publicado automaticamente.</div>
      </div>
    `;

    if (typeof Swal === 'undefined') {
      // Sem SweetAlert2 disponível: importa direto, sem a confirmação visual.
      this._doImport(filePath);
      return;
    }

    Swal.fire({
      title: 'Importar este fluxo?',
      html: html,
      icon: s.elimina_ou_exclui ? 'warning' : 'info',
      showCancelButton: true,
      confirmButtonText: 'Importar',
      cancelButtonText: 'Cancelar',
      confirmButtonColor: '#7A70BA',
    }).then(result => {
      if (result.isConfirmed) this._doImport(filePath);
    });
  },

  _doImport: function(filePath) {
    window.pywebview.api.studio_import_mirflow(filePath).then(res => {
      if (!res.success) {
        window.appBridge.appendLog('ERROR', `Falha ao importar: ${res.error.message}`);
        if (typeof Swal !== 'undefined') Swal.fire('Não foi possível importar', res.error.message || '', 'error');
        return;
      }
      const installed = res.data.packs_instalados || [];
      const installedMsg = installed.length ? ` Packs instalados: ${installed.join(', ')}.` : '';
      window.appBridge.appendLog('SUCCESS', `Fluxo importado como rascunho: ${res.data.flow_id}.${installedMsg}`);
      this.renderGallery();
      if (typeof Swal !== 'undefined') {
        Swal.fire({ icon: 'success', title: 'Importado!', text: 'O fluxo já aparece em "Meus fluxos", como rascunho.', confirmButtonColor: '#7A70BA' });
      }
    });
  },

  // ---- trace ao vivo ----

  onTraceEvent: function(event) {
    if (event.type === 'node') {
      this.applyNodeTraceState(event.node_id, event.status);
    }
    this.updateItemCounter(event);
  },

  applyNodeTraceState: function(nodeId, status) {
    const dfId = this.idMap[nodeId];
    if (dfId === undefined) return;
    const el = document.getElementById('node-' + dfId);
    if (!el) return;
    el.classList.remove('trace-running', 'trace-done', 'trace-error');
    if (status === 'running') el.classList.add('trace-running');
    else if (status === 'done') el.classList.add('trace-done');
    else if (status === 'error') el.classList.add('trace-error');
  },

  updateItemCounter: function(event) {
    const el = document.getElementById('studio-item-counter');
    if (!el || event.total === undefined || event.total === null) return;
    el.style.display = 'inline-block';
    el.innerText = `Item ${event.item_index} / ${event.total}`;
  },

  clearTraceStates: function() {
    document.querySelectorAll('#studio-drawflow .drawflow-node').forEach(el => {
      el.classList.remove('trace-running', 'trace-done', 'trace-error');
    });
    const counter = document.getElementById('studio-item-counter');
    if (counter) counter.style.display = 'none';
  }
};
