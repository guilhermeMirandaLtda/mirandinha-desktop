// Motor de cálculo + cache em memória.
//
// Um lançamento = 1 estrutura PRINCIPAL + Conexão (opc.) + Fixação (opc.).
// O custo explode os componentes dos 3 KITs, agrega por (tipo,codigo,perfil) e precifica.
//
// Desempenho: preços/componentes/params carregados 1x em Maps; invalidado a cada
// escrita (DB.run chama window.CacheBump).

const PERFIS = ['odi', 'odd', 'odm'];

const Cache = {
  _version: 0, _built: -1,
  mat: null, serv: null, comps: null,
  estruturas: null, estruturaById: null,
  principais: null, conexoes: null, fixacoes: null,
  km: null, empresas: null, params: null,

  bump() { this._version++; },

  build() {
    if (this._built === this._version) return this;
    const t0 = performance.now();

    this.mat = new Map();
    for (const r of DB.all('SELECT codigo,texto,un,preco,peso_kg FROM tab_preco_material')) {
      this.mat.set(r.codigo, r);
    }
    this.serv = new Map();
    for (const r of DB.all('SELECT codigo,empresa_id,texto,un,preco FROM tab_preco_servico')) {
      this.serv.set(r.codigo + '|' + r.empresa_id, r);
    }
    this.comps = new Map();
    for (const r of DB.all('SELECT * FROM tab_estrutura_componente')) {
      let a = this.comps.get(r.estrutura_id);
      if (!a) this.comps.set(r.estrutura_id, a = []);
      a.push(r);
    }
    this.estruturas = DB.all('SELECT * FROM tab_estrutura ORDER BY grupo_componente, id');
    this.estruturaById = new Map(this.estruturas.map(e => [e.id, e]));
    // face = variante que representa a família no catálogo (ODI; senão a 1ª que houver)
    this.principais = this.estruturas.filter(e => e.tipo_kit === 'PRINCIPAL' && (e.perfil === 'ODI' || !e.familia));
    this.conexoes = this.estruturas.filter(e => e.tipo_kit === 'CONEXAO' && (e.perfil === 'ODI' || !e.familia));
    this.fixacoes = this.estruturas.filter(e => e.tipo_kit === 'FIXACAO' && (e.perfil === 'ODI' || !e.familia));
    // resolução de variante: familia|tipo_kit|perfil -> estrutura
    this.varMap = new Map();
    this.familiaPerfis = new Map();   // familia|tipo_kit -> Set(perfis)
    for (const e of this.estruturas) {
      if (!e.familia) continue;
      this.varMap.set(e.familia + '|' + e.tipo_kit + '|' + e.perfil, e);
      const fk = e.familia + '|' + e.tipo_kit;
      (this.familiaPerfis.get(fk) || this.familiaPerfis.set(fk, new Set()).get(fk)).add(e.perfil);
    }

    this.km = new Map(DB.all('SELECT * FROM tab_km ORDER BY municipio').map(r => [r.municipio, r]));
    this.empresas = DB.all('SELECT * FROM tab_empresa ORDER BY nome');
    this.params = new Map(DB.all('SELECT chave,valor FROM tab_param').map(r => [r.chave, r.valor]));

    this._built = this._version;
    this.buildMs = performance.now() - t0;
    return this;
  },

  param(k, d) { const v = this.build().params.get(k); return v == null ? d : v; },
  precoMat(c) { return this.build().mat.get(c) || null; },
  precoServ(c, e) { return this.build().serv.get(c + '|' + e) || null; },
  componentes(id) { return this.build().comps.get(id) || []; },

  // Resolve o id da variante `perfilAlvo` (ODI/ODD/ODM) da mesma família/tipo_kit.
  // Devolve o próprio id se já for o perfil certo ou se não tiver família;
  // null se a família não tem variante para aquele perfil.
  variante(estruturaId, perfilAlvo) {
    const e = this.estruturaById.get(estruturaId);
    if (!e) return null;
    if (!e.familia || e.perfil === perfilAlvo) return e.id;
    const v = this.build().varMap.get(e.familia + '|' + e.tipo_kit + '|' + perfilAlvo);
    return v ? v.id : null;
  },
  perfisDaFamilia(estruturaId) {
    const e = this.estruturaById.get(estruturaId);
    if (!e || !e.familia) return e ? [e.perfil].filter(Boolean) : [];
    return [...(this.build().familiaPerfis.get(e.familia + '|' + e.tipo_kit) || [])];
  }
};
window.CacheBump = () => Cache.bump();

// Componentes de um combo PRINCIPAL + CONEXAO + FIXACAO, cada um marcado com a origem.
function explodirCombo(estruturaId, conexaoId, fixacaoId) {
  const out = [];
  const push = (id, origem) => {
    if (!id) return;
    for (const c of Cache.componentes(id)) out.push({ ...c, origem });
  };
  push(estruturaId, 'PRINCIPAL');
  push(conexaoId, 'CONEXAO');
  push(fixacaoId, 'FIXACAO');
  return out;
}

// Custo unitário (1 unidade) de um combo.
function custoCombo(estruturaId, conexaoId, fixacaoId, empresaId) {
  let material = 0, servico = 0, peso = 0, semPreco = 0, nM = 0, nS = 0;
  for (const c of explodirCombo(estruturaId, conexaoId, fixacaoId)) {
    if (c.tipo === 'M') {
      nM++;
      const p = Cache.precoMat(c.codigo);
      if (!p) { semPreco++; continue; }
      material += p.preco * c.quantidade;
      peso += p.peso_kg * c.quantidade;
    } else {
      nS++;
      const p = Cache.precoServ(c.codigo, empresaId);
      if (!p) { semPreco++; continue; }
      servico += p.preco * c.quantidade;
    }
  }
  return { material, servico, total: material + servico, peso, semPreco, nM, nS };
}

// Custo de UM lançamento (todos os perfis), resolvendo a variante de cada perfil.
function custoLancamento(L, empresaId) {
  let material = 0, servico = 0, peso = 0;
  for (const p of PERFIS) {
    const mult = L['qtd_' + p] || 0;
    if (!mult) continue;
    const P = p.toUpperCase();
    const eId = Cache.variante(L.estrutura_id, P);
    if (!eId) continue;
    const cId = L.conexao_id ? Cache.variante(L.conexao_id, P) : null;
    const fId = L.fixacao_id ? Cache.variante(L.fixacao_id, P) : null;
    const c = custoCombo(eId, cId, fId, empresaId);
    material += c.material * mult;
    servico += c.servico * mult;
    peso += c.peso * mult;
  }
  return { material, servico, peso, total: material + servico };
}

// ─────────────────────────────────────────────────────────────
function calcular(projetoId) {
  Cache.build();
  const proj = DB.one('SELECT * FROM tab_projeto WHERE id = ?', [projetoId]);
  if (!proj) throw new Error('Projeto não encontrado');
  const empresaId = proj.empresa_id;

  const lancs = DB.all(
    'SELECT * FROM tab_projeto_estrutura WHERE projeto_id = ? ORDER BY id', [projetoId]);

  const agg = new Map();
  const memoria = [];
  const faltaVariante = [];
  const codErp = id => { const e = Cache.estruturaById.get(id); return e ? e.cod_erp : null; };

  for (const L of lancs) {
    const est = Cache.estruturaById.get(L.estrutura_id);
    if (!est) continue;
    const memComps = [];
    const variantes = {};   // perfil -> {estrutura, conexao, fixacao} (cod_erp)

    for (const p of PERFIS) {
      const mult = L['qtd_' + p] || 0;
      if (!mult) continue;
      const P = p.toUpperCase();
      const eId = Cache.variante(L.estrutura_id, P);
      if (!eId) {
        faltaVariante.push({ familia: est.familia, cod_erp: est.cod_erp, perfil: P });
        continue;
      }
      const cId = L.conexao_id ? Cache.variante(L.conexao_id, P) : null;
      const fId = L.fixacao_id ? Cache.variante(L.fixacao_id, P) : null;
      variantes[p] = { estrutura: codErp(eId), conexao: codErp(cId), fixacao: codErp(fId) };

      for (const c of explodirCombo(eId, cId, fId)) {
        const qv = mult * c.quantidade;
        const k = c.tipo + '|' + c.codigo + '|' + p;
        agg.set(k, (agg.get(k) || 0) + qv);
        memComps.push({ perfil: p, origem: c.origem, tipo: c.tipo, ind_principal: c.ind_principal,
                        codigo: c.codigo, texto: c.texto, un: c.un,
                        tipo_aplicacao: c.tipo_aplicacao, qtd_unit: c.quantidade, mult, qtd: qv });
      }
    }
    memoria.push({
      lancamento_id: L.id, estrutura: est.cod_erp, familia: est.familia, descricao: est.descricao,
      grupo: est.grupo_componente,
      conexao: codErp(L.conexao_id), fixacao: codErp(L.fixacao_id),
      qtd_odi: L.qtd_odi, qtd_odd: L.qtd_odd, qtd_odm: L.qtd_odm,
      variantes, componentes: memComps
    });
  }

  const resumo = {
    material: { odi: 0, odd: 0, odm: 0 }, servico: { odi: 0, odd: 0, odm: 0 },
    transporte: { odi: 0, odd: 0, odm: 0 }, engenharia: { odi: 0, odd: 0, odm: 0 }
  };
  const bomMap = new Map(), servMap = new Map(), semPreco = [];
  let pesoTotal = 0;

  for (const [k, qv] of agg) {
    const [tipo, codigo, perfil] = k.split('|');
    if (tipo === 'M') {
      const p = Cache.precoMat(codigo);
      if (!p) { semPreco.push({ tipo, codigo }); continue; }
      const total = p.preco * qv;
      pesoTotal += p.peso_kg * qv;
      resumo.material[perfil] += total;
      let row = bomMap.get(codigo);
      if (!row) bomMap.set(codigo, row = { codigo, texto: p.texto, un: p.un, preco: p.preco, qtd: 0, total: 0 });
      row.qtd += qv; row.total += total;
    } else {
      const p = Cache.precoServ(codigo, empresaId);
      if (!p) { semPreco.push({ tipo, codigo }); continue; }
      const total = p.preco * qv;
      resumo.servico[perfil] += total;
      let row = servMap.get(codigo);
      if (!row) servMap.set(codigo, row = { codigo, texto: p.texto, un: p.un, preco: p.preco, qtd: 0, total: 0 });
      row.qtd += qv; row.total += total;
    }
  }
  const bom = [...bomMap.values()].sort((a, b) => b.total - a.total);
  const servicos = [...servMap.values()].sort((a, b) => b.total - a.total);

  const capKg = Cache.param('capacidade_veiculo_kg', 27000);
  const custoKm = Cache.param('custo_km', 3.62);
  const kmRow = Cache.km.get(proj.municipio);
  const km = kmRow ? kmRow.km : 0;
  const nVeiculos = pesoTotal > 0 ? Math.max(1, Math.ceil(pesoTotal / capKg)) : 0;
  const transporteTotal = nVeiculos * km * custoKm;

  const pctEng = proj.pct_engenharia != null ? proj.pct_engenharia : Cache.param('pct_engenharia', 0.536);
  const matTotal = resumo.material.odi + resumo.material.odd + resumo.material.odm;
  const servTotal = resumo.servico.odi + resumo.servico.odd + resumo.servico.odm;
  for (const p of PERFIS) {
    const frac = matTotal > 0 ? resumo.material[p] / matTotal : (p === 'odi' ? 1 : 0);
    resumo.transporte[p] = transporteTotal * frac;
    resumo.engenharia[p] = (resumo.material[p] + resumo.servico[p]) * (pctEng / 100);
  }
  const linhaTotais = {};
  for (const p of PERFIS) {
    linhaTotais[p] = resumo.material[p] + resumo.servico[p] + resumo.transporte[p] + resumo.engenharia[p];
  }
  const totalObra = linhaTotais.odi + linhaTotais.odd + linhaTotais.odm;

  return {
    projeto: proj, resumo, linhaTotais, totalObra,
    origem: {
      valor_total: totalObra, erd: proj.erd || 0,
      valor_salvado: proj.valor_salvado || 0, valor_adiantado: proj.valor_adiantado || 0,
      valor_a_pagar: totalObra - (proj.erd || 0) - (proj.valor_salvado || 0) - (proj.valor_adiantado || 0)
    },
    transporte_detalhe: { peso_total_kg: pesoTotal, capacidade_kg: capKg, n_veiculos: nVeiculos,
                          km, custo_km: custoKm, total: transporteTotal },
    engenharia_detalhe: { pct: pctEng, base: matTotal + servTotal,
                          total: resumo.engenharia.odi + resumo.engenharia.odd + resumo.engenharia.odm },
    bom, servicos, memoria, sem_preco: semPreco, falta_variante: faltaVariante, n_lancamentos: lancs.length
  };
}
