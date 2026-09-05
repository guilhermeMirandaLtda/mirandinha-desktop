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
  _initialized: false,

  // ---- ciclo de vida da view ----

  init: function() {
    if (!window.pywebview || !window.pywebview.api) {
      const empty = document.getElementById('studio-canvas-empty');
      if (empty) empty.innerHTML = '<i class="ri-error-warning-line"></i><span>O Studio precisa do aplicativo desktop rodando (pywebview) — não funciona numa aba de navegador solta.</span>';
      return;
    }

    if (!this._initialized) {
      this._initialized = true;
      const container = document.getElementById('studio-drawflow');
      this.editor = new Drawflow(container);
      this.editor.reroute = true;
      this.editor.start();
      this.editor.on('nodeSelected', (id) => this.onNodeSelected(id));
      this.editor.on('nodeUnselected', () => this.showInspectorEmpty());
      this.loadCatalog();
    }

    this.loadSources();
  },

  loadCatalog: function() {
    window.pywebview.api.studio_node_catalog().then(res => {
      if (res.success) this.catalog = res.data;
    });
  },

  loadSources: function() {
    window.pywebview.api.studio_list_samples().then(res => {
      const container = document.getElementById('studio-samples-list');
      if (!container) return;
      if (!res.success || !res.data || res.data.length === 0) {
        container.innerHTML = '<div class="studio-source-empty">Nenhum exemplo encontrado.</div>';
        return;
      }
      container.innerHTML = res.data.map(s => `
        <div class="studio-source-item" data-kind="sample" data-ref="${studioEscapeHtml(s.file)}"
             onclick="window.studioBridge.selectSource('sample', '${studioEscapeHtml(s.file)}')">
          <span class="name">${studioEscapeHtml(s.name)}</span>
          <span class="meta">${studioEscapeHtml(s.transacao || 'sem transação')}</span>
        </div>
      `).join('');
    });

    window.pywebview.api.studio_list_flows().then(res => {
      const container = document.getElementById('studio-flows-list');
      if (!container) return;
      if (!res.success || !res.data || res.data.length === 0) {
        container.innerHTML = '<div class="studio-source-empty">Nenhum fluxo salvo ainda.</div>';
        return;
      }
      container.innerHTML = res.data.map(f => `
        <div class="studio-source-item" data-kind="flow" data-ref="${studioEscapeHtml(f.flow_id)}"
             onclick="window.studioBridge.selectSource('flow', '${studioEscapeHtml(f.flow_id)}')">
          <span class="name">${studioEscapeHtml(f.name)}</span>
          <span class="meta">${f.is_published ? 'publicado' : 'rascunho'} · ${studioEscapeHtml(f.updated_at || '')}</span>
        </div>
      `).join('');
    });
  },

  // ---- carregar um fluxo no canvas ----

  selectSource: function(kind, ref) {
    document.querySelectorAll('.studio-source-item').forEach(el => el.classList.remove('active'));
    document.querySelectorAll(`.studio-source-item[data-kind="${kind}"]`).forEach(el => {
      if (el.getAttribute('data-ref') === ref) el.classList.add('active');
    });

    const loadPromise = kind === 'sample'
      ? window.pywebview.api.studio_load_sample(ref)
      : window.pywebview.api.studio_get_flow(ref).then(res => res.success ? { success: true, data: res.data.graph } : res);

    loadPromise.then(res => {
      if (!res.success) {
        window.appBridge.appendLog('ERROR', `Falha ao carregar fluxo: ${res.error ? res.error.message : 'erro desconhecido'}`);
        return;
      }
      this.currentSource = { kind: kind, ref: ref };
      this.loadGraphIntoCanvas(res.data);
    });
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
      this.loadSources();
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
