// UI do protótipo — wizard de 3 passos.
// Desempenho: catálogo renderizado UMA vez + eventos delegados; custos vêm do
// cache em memória (engine.js), não do banco, a cada interação.

const state = { step: 1, projetoId: null, grupo: '*', busca: '', editando: null, ultimo: null };

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const money = n => 'R$ ' + (n || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const qty = n => (+(+n || 0).toFixed(4)).toLocaleString('pt-BR', { maximumFractionDigits: 4 });
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function toast(msg, kind = '') {
  const el = document.createElement('div');
  el.className = 'toast ' + kind;
  el.textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), 2400);
}

// ═══════════════════════════════════ boot
window.addEventListener('DOMContentLoaded', async () => {
  await DB.init();
  Cache.build();
  if (DB.reseeded) {
    setTimeout(() => toast(`Banco recriado (${DB.reseeded}) — dados de exemplo restaurados`), 400);
  }

  let p = DB.one('SELECT id FROM tab_projeto ORDER BY id LIMIT 1');
  if (!p) {
    DB.run("INSERT INTO tab_projeto (nome,empresa_id,pct_engenharia) VALUES ('Novo orçamento',1,0.536)");
    p = { id: DB.lastId() };
  }
  state.projetoId = p.id;

  wireShell();
  wireCatalogo();
  wireProjeto();
  buildChips();
  buildCatalogo();
  renderProjetoForm();
  renderCart();
  $('#boot').remove();
});

// ═══════════════════════════════════ shell (topbar / stepper)
function wireShell() {
  $$('.step').forEach(b => b.addEventListener('click', () => irPara(+b.dataset.step)));
  document.body.addEventListener('click', e => {
    const g = e.target.closest('[data-goto]');
    if (g) irPara(+g.dataset.goto);
  });
  $('#go-2').addEventListener('click', () => irPara(2));
  $('#go-3').addEventListener('click', () => irPara(3));

  $('#b-new').addEventListener('click', () => {
    if (!confirm('Criar um novo orçamento em branco?')) return;
    DB.run("INSERT INTO tab_projeto (nome,empresa_id,pct_engenharia) VALUES ('Novo orçamento',1,0.536)");
    state.projetoId = DB.lastId();
    renderProjetoForm(); renderCart(); irPara(1);
    toast('Novo orçamento criado', 'ok');
  });
  $('#b-exp').addEventListener('click', () => DB.exportFile());
  $('#b-imp').addEventListener('click', () => $('#f-imp').click());
  $('#f-imp').addEventListener('change', async e => {
    if (e.target.files[0]) { await DB.importFile(e.target.files[0]); location.reload(); }
  });
  $('#b-reset').addEventListener('click', async () => {
    if (!confirm('Recriar o banco do zero? Suas alterações locais serão perdidas.')) return;
    await DB.init({ reseed: true }); location.reload();
  });
  $('#b-csv').addEventListener('click', exportCsv);
  $('#r-mem').addEventListener('toggle', e => {
    const d = e.target.closest('details[data-mem]');
    if (d && d.open) montarMemoria(d);
  }, true);

  // drawer
  $('#d-close').addEventListener('click', fecharDrawer);
  $('#bd').addEventListener('click', fecharDrawer);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') fecharDrawer(); });
  $('#f-estr').addEventListener('submit', e => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(e.target));
    DB.run('UPDATE tab_estrutura SET grupo_componente=?,cod_erp=?,descricao=?,un=? WHERE id=?',
      [d.grupo_componente, d.cod_erp, d.descricao, d.un, state.editando]);
    buildChips(); buildCatalogo(); renderCart();
    toast('Estrutura atualizada', 'ok');
    fecharDrawer();
  });
}

function irPara(n) {
  if (n === 3 && !salvarProjeto()) return;
  state.step = n;
  $$('.pane').forEach(p => p.classList.remove('active'));
  $('#pane-' + n).classList.add('active');
  $$('.step').forEach(b => {
    const s = +b.dataset.step;
    b.classList.toggle('active', s === n);
    b.classList.toggle('done', s < n);
  });
  window.scrollTo({ top: 0, behavior: 'smooth' });
  if (n === 2) renderResumoSelecao();
  if (n === 3) renderResumo();
}

// ═══════════════════════════════════ passo 1 — catálogo
// 'DFCMT201 — N1 OU B1 … CB 1/0AWG …' -> 'DFCMT201 · 1/0AWG'  (value = id)
function kitLabel(e) {
  const g = (e.descricao || '').match(/(\d+(?:\/\d+)?AWG|\d+(?:,\d+)?MCM)/);
  return e.cod_erp + (g ? ' · ' + g[1] : '');
}
function optsKit(lista, sel) {
  return '<option value="">(nenhuma)</option>' + lista.map(k =>
    `<option value="${k.id}" title="${esc(k.descricao || '')}"${+sel === k.id ? ' selected' : ''}>${esc(kitLabel(k))}</option>`
  ).join('');
}

function buildChips() {
  const grupos = [...new Set(Cache.build().principais.map(e => e.grupo_componente || 'SEM GRUPO'))];
  $('#chips').innerHTML =
    `<button class="chip on" data-g="*">Todos</button>` +
    grupos.map(g => `<button class="chip" data-g="${esc(g)}">${esc(g)}</button>`).join('');
}

function buildCatalogo() {
  const proj = DB.one('SELECT empresa_id FROM tab_projeto WHERE id=?', [state.projetoId]);
  const emp = proj ? proj.empresa_id : null;
  const grupos = {};
  for (const e of Cache.principais) (grupos[e.grupo_componente || 'SEM GRUPO'] ||= []).push(e);

  const head = `<div class="crow head">
    <div>Família</div><div>Estrutura</div><div>Conexão</div><div>Fixação</div>
    <div class="c-r">ODI</div><div class="c-r">ODD</div><div class="c-r">ODM</div><div></div></div>`;

  let html = '';
  for (const [g, list] of Object.entries(grupos)) {
    html += `<div class="grp-h" data-grp-h="${esc(g)}">${esc(g)}<span class="ln"></span>
      <span class="muted" style="font-weight:600;text-transform:none;letter-spacing:0">${list.length}</span></div>`;
    html += head;
    for (const e of list) {
      const cst = custoCombo(e.id, null, null, emp);
      const perfis = Cache.perfisDaFamilia(e.id);
      const badge = ['ODI', 'ODD', 'ODM']
        .map(p => `<span class="perf ${perfis.includes(p) ? 'on' : ''}">${p}</span>`).join('');
      html += `<div class="crow" data-id="${e.id}" data-grp="${esc(e.grupo_componente || 'SEM GRUPO')}"
          data-search="${esc(((e.familia || '') + ' ' + (e.cod_erp || '') + ' ' + (e.descricao || '')).toLowerCase())}">
        <div class="cod">${esc(e.familia || e.cod_erp || '')}</div>
        <div class="ttl">
          <div class="t1"><b title="Ver componentes">${esc(e.familia || e.cod_erp)}</b>
            <span class="perfs" title="perfis com variante nesta família">${badge}</span>
            <span class="desc">${esc(e.descricao || '')}</span></div>
          <div class="cst"><span data-cst>${money(cst.total)}</span> / un ODI · <span class="mono">${esc(e.cod_erp)}</span></div>
        </div>
        <select data-f="conexao" title="Conexão (CONEX MT)">${optsKit(Cache.conexoes)}</select>
        <select data-f="fixacao" title="Fixação de cabo (FIX CB MT)">${optsKit(Cache.fixacoes)}</select>
        <input type="number" min="0" step="1" data-f="odi" placeholder="0">
        <input type="number" min="0" step="1" data-f="odd" placeholder="0">
        <input type="number" min="0" step="1" data-f="odm" placeholder="0">
        <button class="add" data-act="add" title="Adicionar">+</button>
      </div>`;
    }
  }
  $('#catalog').innerHTML = html;
  aplicarFiltro();
}

function wireCatalogo() {
  const cat = $('#catalog');

  cat.addEventListener('change', e => {
    const f = e.target.dataset.f;
    if (f === 'conexao' || f === 'fixacao') atualizarCusto(e.target.closest('.crow'));
  });

  cat.addEventListener('click', e => {
    const row = e.target.closest('.crow');
    if (!row) return;
    if (e.target.closest('[data-act="add"]')) return adicionar(row);
    if (e.target.closest('.ttl b')) return abrirDrawer(+row.dataset.id);
  });

  cat.addEventListener('keydown', e => {
    if (e.key === 'Enter' && e.target.dataset.f) {
      e.preventDefault();
      adicionar(e.target.closest('.crow'));
    }
  });

  $('#q').addEventListener('input', e => { state.busca = e.target.value.trim().toLowerCase(); aplicarFiltro(); });
  $('#chips').addEventListener('click', e => {
    const c = e.target.closest('.chip'); if (!c) return;
    $$('#chips .chip').forEach(x => x.classList.toggle('on', x === c));
    state.grupo = c.dataset.g;
    aplicarFiltro();
  });
}

function valorLinha(row) {
  const g = f => row.querySelector(`[data-f="${f}"]`);
  return {
    conexao: +g('conexao').value || null,
    fixacao: +g('fixacao').value || null,
    odi: +g('odi').value || 0, odd: +g('odd').value || 0, odm: +g('odm').value || 0
  };
}

function atualizarCusto(row) {
  const v = valorLinha(row);
  const proj = DB.one('SELECT empresa_id FROM tab_projeto WHERE id=?', [state.projetoId]);
  const c = custoCombo(+row.dataset.id, v.conexao, v.fixacao, proj ? proj.empresa_id : null);
  row.querySelector('[data-cst]').textContent = money(c.total);
}

function adicionar(row) {
  const v = valorLinha(row);
  if (!(v.odi + v.odd + v.odm)) {
    toast('Informe a quantidade em ODI, ODD ou ODM', 'err');
    row.querySelector('[data-f="odi"]').focus();
    return;
  }
  DB.run(`INSERT INTO tab_projeto_estrutura
          (projeto_id,estrutura_id,qtd_odi,qtd_odd,qtd_odm,conexao_id,fixacao_id)
          VALUES (?,?,?,?,?,?,?)`,
    [state.projetoId, +row.dataset.id, v.odi, v.odd, v.odm, v.conexao, v.fixacao]);

  ['odi', 'odd', 'odm'].forEach(f => row.querySelector(`[data-f="${f}"]`).value = '');
  row.classList.add('added');
  setTimeout(() => row.classList.remove('added'), 700);
  renderCart();
  toast('Adicionado ao orçamento', 'ok');
}

function aplicarFiltro() {
  const q = state.busca, g = state.grupo;
  const visiveis = {};
  $$('#catalog .crow[data-id]').forEach(r => {
    const okG = g === '*' || r.dataset.grp === g;
    const okQ = !q || r.dataset.search.includes(q);
    const vis = okG && okQ;
    r.hidden = !vis;
    if (vis) visiveis[r.dataset.grp] = true;
  });
  // esconde cabeçalho + linha de títulos de grupos sem resultado
  $$('#catalog .grp-h').forEach(h => {
    const on = !!visiveis[h.dataset.grpH];
    h.hidden = !on;
    const head = h.nextElementSibling;
    if (head && head.classList.contains('head')) head.hidden = !on;
  });
}

// ═══════════════════════════════════ carrinho
function itensCarrinho() {
  const proj = DB.one('SELECT empresa_id FROM tab_projeto WHERE id=?', [state.projetoId]);
  const emp = proj ? proj.empresa_id : null;
  const rows = DB.all(`
    SELECT pe.*, e.cod_erp, e.familia, e.grupo_componente AS grupo, e.descricao, e.un,
           cx.familia AS conexao_fam, fx.familia AS fixacao_fam
    FROM tab_projeto_estrutura pe
    JOIN tab_estrutura e  ON e.id  = pe.estrutura_id
    LEFT JOIN tab_estrutura cx ON cx.id = pe.conexao_id
    LEFT JOIN tab_estrutura fx ON fx.id = pe.fixacao_id
    WHERE pe.projeto_id = ? ORDER BY pe.id DESC`, [state.projetoId]);
  let mat = 0, serv = 0;
  for (const r of rows) {
    const c = custoLancamento(r, emp);
    r.material = c.material; r.servico = c.servico; r.total = c.total;
    mat += c.material; serv += c.servico;
  }
  return { rows, mat, serv, total: mat + serv };
}

function cartHtml(rows, comRemover) {
  if (!rows.length) {
    return `<div class="empty"><span class="ic">📋</span>Nenhuma estrutura selecionada.<br>
      Informe a quantidade e clique em <b>+</b>.</div>`;
  }
  return rows.map(r => {
    const qs = [['ODI', r.qtd_odi], ['ODD', r.qtd_odd], ['ODM', r.qtd_odm]]
      .filter(([, v]) => v).map(([k, v]) => `<span class="q">${k} ${qty(v)}</span>`).join('');
    const meta = [
      r.conexao_fam && 'CX ' + r.conexao_fam,
      r.fixacao_fam && 'FIX ' + r.fixacao_fam
    ].filter(Boolean).join(' · ') || 'sem conexão/fixação';
    return `<div class="citem">
      <div class="top"><b>${esc(r.familia || r.cod_erp)}</b><span class="tag">${esc(r.un || 'KIT')}</span>
        ${comRemover ? `<button class="rm" data-rm="${r.id}" title="Remover">&times;</button>` : ''}</div>
      <div class="val num">${money(r.total)}</div>
      <div class="qs" style="grid-column:1/-1">${qs}</div>
      <div class="meta">${esc(r.descricao || '')} — ${esc(meta)}</div>
    </div>`;
  }).join('');
}

function renderCart() {
  const { rows, mat, serv, total } = itensCarrinho();
  $('#cart-list').innerHTML = cartHtml(rows, true);
  $('#cart-count').textContent = rows.length
    ? `${rows.length} lançamento${rows.length > 1 ? 's' : ''}` : 'nenhuma estrutura';
  $('#c-mat').textContent = money(mat);
  $('#c-serv').textContent = money(serv);
  $('#c-tot').textContent = money(total);
  $('#go-2').disabled = !rows.length;

  $$('#cart-list [data-rm]').forEach(b => b.addEventListener('click', () => {
    DB.run('DELETE FROM tab_projeto_estrutura WHERE id=?', [+b.dataset.rm]);
    renderCart(); toast('Removido');
  }));

  const p = DB.one('SELECT * FROM tab_projeto WHERE id=?', [state.projetoId]);
  $('#tb-name').textContent = p ? p.nome : '—';
  const km = p && Cache.km.get(p.municipio);
  const empNome = p && Cache.empresas.find(e => e.id === p.empresa_id);
  $('#tb-sub').textContent = [p && p.municipio, km && km.km + ' km', empNome && empNome.nome].filter(Boolean).join(' · ');
  try { $('#tb-total').textContent = money(calcular(state.projetoId).totalObra); }
  catch { $('#tb-total').textContent = money(total); }
}

function renderResumoSelecao() {
  const { rows, total } = itensCarrinho();
  $('#p2-list').innerHTML = cartHtml(rows, false);
  $('#p2-count').textContent = `${rows.length} lançamento${rows.length === 1 ? '' : 's'}`;
  $('#p2-tot').textContent = money(total);
}

// ═══════════════════════════════════ passo 2 — projeto
function wireProjeto() {
  $('#s-emp').innerHTML = Cache.empresas.map(e => `<option value="${e.id}">${esc(e.nome)}</option>`).join('');
  $('#s-mun').innerHTML = '<option value="">— selecione —</option>' +
    [...Cache.km.values()].map(k => `<option value="${esc(k.municipio)}">${esc(k.municipio)}</option>`).join('');
  $('#s-mun').addEventListener('change', kmHint);
  $('#s-emp').addEventListener('change', () => { salvarProjeto(); buildCatalogo(); renderCart(); });
}
function kmHint() {
  const k = Cache.km.get($('#s-mun').value);
  $('#km-hint').textContent = k ? `${k.km} km desde ${k.origem} — usado no cálculo de transporte.` : '';
}
function renderProjetoForm() {
  const p = DB.one('SELECT * FROM tab_projeto WHERE id=?', [state.projetoId]);
  if (!p) return;
  const f = $('#f-proj');
  for (const el of f.elements) if (el.name) el.value = p[el.name] == null ? '' : p[el.name];
  kmHint();
}
function salvarProjeto() {
  const f = $('#f-proj');
  const d = Object.fromEntries(new FormData(f));
  if (!d.nome || !d.nome.trim()) {
    toast('Informe o nome da obra', 'err');
    return false;
  }
  ['empresa_id', 'pct_engenharia', 'erd', 'valor_salvado', 'valor_adiantado']
    .forEach(k => d[k] = d[k] === '' ? null : +d[k]);
  DB.run(`UPDATE tab_projeto SET nome=?,municipio=?,regional=?,pep=?,cliente=?,cpf_cnpj=?,endereco=?,
          empresa_id=?,pct_engenharia=?,erd=?,valor_salvado=?,valor_adiantado=? WHERE id=?`,
    [d.nome, d.municipio, d.regional, d.pep, d.cliente, d.cpf_cnpj, d.endereco,
     d.empresa_id, d.pct_engenharia, d.erd, d.valor_salvado, d.valor_adiantado, state.projetoId]);
  renderCart();
  return true;
}

// ═══════════════════════════════════ passo 3 — resumo
function renderResumo() {
  let r;
  try { r = calcular(state.projetoId); }
  catch (e) { $('#r-alert').innerHTML = `<div class="card"><div class="card-b">${esc(e.message)}</div></div>`; return; }
  state.ultimo = r;

  const avisos = [];
  if (r.falta_variante.length) {
    const fam = [...new Set(r.falta_variante.map(x => `${x.familia} (${x.perfil})`))];
    avisos.push(`<span class="pill err">sem variante</span> ${fam.length} família(s) sem COD_ERP para o perfil lançado — essa quantidade foi ignorada:
      <span class="mono" style="font-size:11.5px">${fam.map(esc).join(', ')}</span>`);
  }
  if (r.sem_preco.length) {
    avisos.push(`<span class="pill warn">sem preço</span> ${r.sem_preco.length} código(s) sem preço cadastrado — contam como R$ 0,00:
      <span class="mono" style="font-size:11.5px">${r.sem_preco.map(x => esc(x.codigo)).join(', ')}</span>`);
  }
  $('#r-alert').innerHTML = avisos.length
    ? `<div class="card" style="border-color:var(--warn);margin-bottom:16px"><div class="card-b" style="display:flex;flex-direction:column;gap:8px">${avisos.map(a => `<div>${a}</div>`).join('')}</div></div>`
    : '';

  const R = r.resumo, T = r.linhaTotais;
  const s = o => o.odi + o.odd + o.odm;
  $('#r-kpis').innerHTML = `
    <div class="kpi"><div class="l">Materiais</div><div class="v num">${money(s(R.material))}</div>
      <div class="d">${r.bom.length} itens · ${qty(Math.round(r.transporte_detalhe.peso_total_kg))} kg</div></div>
    <div class="kpi"><div class="l">Serviços</div><div class="v num">${money(s(R.servico))}</div>
      <div class="d">${r.servicos.length} itens de contrato</div></div>
    <div class="kpi"><div class="l">Transporte + Engenharia</div>
      <div class="v num">${money(s(R.transporte) + s(R.engenharia))}</div>
      <div class="d">${r.transporte_detalhe.n_veiculos} veículo(s) · ${qty(r.transporte_detalhe.km)} km</div></div>
    <div class="kpi hero"><div class="l">Total da obra</div><div class="v num">${money(r.totalObra)}</div>
      <div class="d">${r.n_lancamentos} lançamentos</div></div>`;

  const p = r.projeto;
  $('#r-sub').textContent = [p.nome, p.municipio, p.pep].filter(Boolean).join(' · ');

  const ln = (nome, o) => `<tr><td>${nome}</td><td class="r">${money(o.odi)}</td><td class="r">${money(o.odd)}</td>
    <td class="r">${money(o.odm)}</td><td class="r">${money(s(o))}</td></tr>`;
  $('#r-res tbody').innerHTML = ln('Materiais', R.material) + ln('Serviços', R.servico) +
    ln('Transporte de materiais', R.transporte) + ln('Engenharia e supervisão', R.engenharia) +
    `<tr class="tot"><td>Total</td><td class="r">${money(T.odi)}</td><td class="r">${money(T.odd)}</td>
      <td class="r">${money(T.odm)}</td><td class="r">${money(r.totalObra)}</td></tr>`;

  const o = r.origem;
  $('#r-org tbody').innerHTML = `
    <tr><td>Valor total da obra</td><td class="r">${money(o.valor_total)}</td></tr>
    <tr><td>(–) ERD</td><td class="r">${money(o.erd)}</td></tr>
    <tr><td>(–) Valor salvado</td><td class="r">${money(o.valor_salvado)}</td></tr>
    <tr><td>(–) Adiantado pelo cliente</td><td class="r">${money(o.valor_adiantado)}</td></tr>
    <tr class="tot"><td>Valor a pagar</td><td class="r">${money(o.valor_a_pagar)}</td></tr>`;

  const td = r.transporte_detalhe, ed = r.engenharia_detalhe;
  $('#r-det').innerHTML =
    `<b>Transporte:</b> ${qty(Math.round(td.peso_total_kg))} kg ÷ ${qty(td.capacidade_kg)} kg = ${td.n_veiculos} veículo(s) × ${qty(td.km)} km × ${money(td.custo_km)}/km = <b>${money(td.total)}</b><br>` +
    `<b>Engenharia:</b> ${ed.pct}% sobre ${money(ed.base)} = <b>${money(ed.total)}</b>`;

  $('#s-bom').textContent = `Materiais (${r.bom.length})`;
  $('#s-srv').textContent = `Serviços (${r.servicos.length})`;
  const linhaItem = x => `<tr><td class="mono">${esc(x.codigo)}</td><td>${esc(x.texto || '')}</td>
    <td>${esc(x.un || '')}</td><td class="r">${qty(x.qtd)}</td><td class="r">${money(x.preco)}</td>
    <td class="r">${money(x.total)}</td></tr>`;
  $('#r-bom tbody').innerHTML = r.bom.map(linhaItem).join('') || '<tr><td colspan="6" class="muted">—</td></tr>';
  $('#r-srv tbody').innerHTML = r.servicos.map(linhaItem).join('') || '<tr><td colspan="6" class="muted">—</td></tr>';

  // Memória: só os cabeçalhos. O corpo de cada bloco é montado ao abrir (lazy),
  // senão 300+ lançamentos custariam ~200ms de DOM que quase nunca é lido.
  $('#r-mem').innerHTML = r.memoria.map((m, i) => `
    <details class="acc" data-mem="${i}"><summary>${esc(m.familia || m.estrutura)} — ODI ${qty(m.qtd_odi)} / ODD ${qty(m.qtd_odd)} / ODM ${qty(m.qtd_odm)}
      <span class="muted" style="font-weight:400"> · CX ${esc(m.conexao || '—')} · FIX ${esc(m.fixacao || '—')}</span></summary>
      <div class="inner scroll-x"></div></details>`).join('')
    || '<p class="muted">Nenhum lançamento.</p>';
}

function montarMemoria(det) {
  const inner = det.querySelector('.inner');
  if (inner.dataset.done) return;
  const m = state.ultimo.memoria[+det.dataset.mem];
  const varLinhas = Object.entries(m.variantes).map(([p, v]) =>
    `<span class="mono" style="font-size:10.5px">${p.toUpperCase()} → ${esc(v.estrutura)}${v.conexao ? ' + ' + esc(v.conexao) : ''}${v.fixacao ? ' + ' + esc(v.fixacao) : ''}</span>`
  ).join('<br>');
  inner.innerHTML = `<p class="muted" style="font-size:11px;margin:0 0 10px">Variantes resolvidas por perfil:<br>${varLinhas || '—'}</p>
    <table><thead><tr><th>KIT</th><th>Perfil</th><th>T</th><th>Código</th><th>Descrição</th>
    <th class="r">Qtd/un</th><th class="r">× Lanç.</th><th class="r">= Qtd</th></tr></thead><tbody>
    ${m.componentes.map(c => `<tr><td style="font-size:10.5px">${esc(c.origem)}</td>
      <td>${c.perfil.toUpperCase()}</td>
      <td><span class="pill ${c.tipo === 'M' ? 'n' : 'ok'}">${c.tipo}</span></td>
      <td class="mono">${esc(c.codigo)}</td><td>${esc(c.texto || '')}</td>
      <td class="r">${qty(c.qtd_unit)}</td><td class="r">${qty(c.mult)}</td><td class="r">${qty(c.qtd)}</td></tr>`).join('')}
    </tbody></table>`;
  inner.dataset.done = '1';
}

// ═══════════════════════════════════ drawer (ver/editar estrutura)
function abrirDrawer(id) {
  const e = Cache.estruturaById.get(id);
  if (!e) return;
  state.editando = id;
  const f = $('#f-estr');
  f.grupo_componente.value = e.grupo_componente || '';
  f.cod_erp.value = e.cod_erp || '';
  f.descricao.value = e.descricao || '';
  f.un.value = e.un || '';
  $('#d-title').textContent = `${e.cod_erp || ''} — ${e.tipo_kit}`;
  $('#d-comp tbody').innerHTML = Cache.componentes(id)
    .slice().sort((a, b) => (b.ind_principal - a.ind_principal) || (b.tipo > a.tipo ? 1 : -1) || a.codigo.localeCompare(b.codigo))
    .map(c => `<tr>
      <td>${c.ind_principal ? '<span class="pill n">principal</span>' : ''}
        <span class="pill ${c.tipo === 'M' ? 'n' : 'ok'}">${c.tipo}</span></td>
      <td class="mono">${esc(c.codigo)}</td><td>${esc(c.texto || '')}</td>
      <td class="r">${qty(c.quantidade)} ${esc(c.un || '')}</td>
      <td style="font-size:11px">${esc(c.tipo_aplicacao || '—')}</td>
      <td><button class="btn btn-g btn-sm" data-dc="${c.id}">excluir</button></td></tr>`).join('')
    || '<tr><td colspan="6" class="muted">Sem componentes.</td></tr>';
  $$('#d-comp [data-dc]').forEach(b => b.addEventListener('click', () => {
    DB.run('DELETE FROM tab_estrutura_componente WHERE id=?', [+b.dataset.dc]);
    abrirDrawer(id); buildCatalogo(); renderCart();
  }));
  $('#drawer').classList.add('open'); $('#drawer').setAttribute('aria-hidden', 'false');
  $('#bd').classList.add('open');
}
function fecharDrawer() {
  $('#drawer').classList.remove('open'); $('#drawer').setAttribute('aria-hidden', 'true');
  $('#bd').classList.remove('open'); state.editando = null;
}

// ═══════════════════════════════════ CSV
function exportCsv() {
  const r = state.ultimo || calcular(state.projetoId);
  const rows = [['secao', 'codigo', 'descricao', 'un', 'qtd', 'preco_unit', 'total']];
  r.bom.forEach(b => rows.push(['MATERIAL', b.codigo, b.texto, b.un, b.qtd, b.preco, b.total]));
  r.servicos.forEach(s => rows.push(['SERVICO', s.codigo, s.texto, s.un, s.qtd, s.preco, s.total]));
  const R = r.resumo, T = r.linhaTotais, sum = o => o.odi + o.odd + o.odm;
  rows.push([], ['RESUMO', 'linha', '', '', 'odi', 'odd', 'odm', 'total']);
  [['Materiais', R.material], ['Servicos', R.servico], ['Transporte', R.transporte], ['Engenharia', R.engenharia]]
    .forEach(([n, o]) => rows.push(['RESUMO', n, '', '', o.odi, o.odd, o.odm, sum(o)]));
  rows.push(['RESUMO', 'TOTAL', '', '', T.odi, T.odd, T.odm, r.totalObra]);
  const csv = rows.map(l => l.map(v => {
    const s = String(v == null ? '' : v);
    return /[",;\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }).join(';')).join('\n');
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }));
  a.download = 'orcamento.csv'; a.click(); URL.revokeObjectURL(a.href);
  toast('CSV baixado', 'ok');
}
