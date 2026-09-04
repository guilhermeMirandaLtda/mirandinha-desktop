-- Protótipo do Módulo de Orçamento de Obra — DDL
-- Modelado a partir da aba "LISTA TÉC" da planilha: um KIT (COD_ERP) é uma estrutura;
-- suas linhas são os componentes (material COD_MATERIAL / serviço COD_SERVICO).
--
-- IMPORTANTE: ao mudar QUALQUER tabela, incremente PRAGMA user_version.
-- Bancos salvos no localStorage com versão diferente são descartados e recriados.
PRAGMA user_version = 4;
PRAGMA foreign_keys = ON;

-- ─────────────────────────────────────────────────────────────
-- Cadastros de apoio
-- ─────────────────────────────────────────────────────────────
CREATE TABLE tab_empresa (
  id   INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL UNIQUE
);

-- Preço de material: GLOBAL. Atualiza 1x e reflete em todas as estruturas.
CREATE TABLE tab_preco_material (
  codigo        TEXT PRIMARY KEY,     -- COD_MATERIAL
  texto         TEXT,                 -- DESC_MATERIAL
  un            TEXT,
  preco         REAL NOT NULL DEFAULT 0,
  peso_kg       REAL NOT NULL DEFAULT 0,
  atualizado_em TEXT DEFAULT (datetime('now'))
);

-- Preço de serviço: POR EMPRESA (varia conforme a empreiteira/contrato).
CREATE TABLE tab_preco_servico (
  codigo        TEXT NOT NULL,        -- COD_SERVICO
  empresa_id    INTEGER NOT NULL REFERENCES tab_empresa(id) ON DELETE CASCADE,
  texto         TEXT,
  un            TEXT,
  preco         REAL NOT NULL DEFAULT 0,
  atualizado_em TEXT DEFAULT (datetime('now')),
  PRIMARY KEY (codigo, empresa_id)
);

CREATE TABLE tab_km (
  municipio TEXT PRIMARY KEY,
  origem    TEXT,
  km        REAL NOT NULL DEFAULT 0
);

CREATE TABLE tab_param (
  chave     TEXT PRIMARY KEY,
  valor     REAL NOT NULL,
  descricao TEXT
);

-- ─────────────────────────────────────────────────────────────
-- Catálogo de estruturas (KITs) — reutilizável entre projetos
-- ─────────────────────────────────────────────────────────────
-- COD_ERP = <letra do perfil> + <família>.  Ex.: IEBT106 (ODI) e DEBT106 (ODD)
-- são a MESMA família 'EBT106'. O usuário escolhe a variante ODI; a coluna de
-- quantidade (ODI/ODD/ODM) resolve automaticamente o COD_ERP da mesma família.
CREATE TABLE tab_estrutura (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo_kit         TEXT NOT NULL DEFAULT 'PRINCIPAL'
                     CHECK (tipo_kit IN ('PRINCIPAL','CONEXAO','FIXACAO')),
  grupo_componente TEXT,                -- GRUPO_COMPONENTE (ESTRUT MT, POSTE, CONEX MT, FIX CB MT…)
  cod_erp          TEXT,                -- COD_ERP
  familia          TEXT,                -- COD_ERP sem a 1ª letra (chave que liga as variantes)
  perfil           TEXT,                -- ODI | ODD | ODM  (da 1ª letra: I/D/M)
  descricao        TEXT,                -- DESC_ERP
  un               TEXT DEFAULT 'KIT'
);
CREATE INDEX idx_estr_familia ON tab_estrutura(familia, tipo_kit, perfil);

CREATE TABLE tab_estrutura_componente (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  estrutura_id   INTEGER NOT NULL REFERENCES tab_estrutura(id) ON DELETE CASCADE,
  ind_principal  INTEGER NOT NULL DEFAULT 0,   -- IND_PRINCIPAL
  tipo           TEXT NOT NULL CHECK (tipo IN ('M','S')),
  codigo         TEXT NOT NULL,   -- COD_MATERIAL | COD_SERVICO
  texto          TEXT,            -- DESC_MATERIAL | DESC_SERVICO
  un             TEXT,            -- UND_MATERIAL
  quantidade     REAL NOT NULL DEFAULT 0,
  tipo_aplicacao TEXT             -- TIPO_APLICACAO (ODI/ODD/ODS/ODM) — informativo
);

-- ─────────────────────────────────────────────────────────────
-- Projeto e lançamentos (a "aba Controle")
-- Cada lançamento = 1 estrutura PRINCIPAL + Conexão (opc.) + Fixação (opc.)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE tab_projeto (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  nome            TEXT NOT NULL,
  municipio       TEXT,
  regional        TEXT,
  pep             TEXT,
  cliente         TEXT,
  cpf_cnpj        TEXT,
  endereco        TEXT,
  empresa_id      INTEGER REFERENCES tab_empresa(id),
  pct_engenharia  REAL DEFAULT 0.536,
  erd             REAL DEFAULT 0,
  valor_salvado   REAL DEFAULT 0,
  valor_adiantado REAL DEFAULT 0,
  status          TEXT DEFAULT 'rascunho',
  criado_em       TEXT DEFAULT (datetime('now'))
);

-- estrutura_id/conexao_id/fixacao_id guardam a variante escolhida (normalmente ODI).
-- As quantidades por perfil resolvem, no cálculo, o COD_ERP irmão de cada família.
CREATE TABLE tab_projeto_estrutura (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  projeto_id   INTEGER NOT NULL REFERENCES tab_projeto(id) ON DELETE CASCADE,
  estrutura_id INTEGER NOT NULL REFERENCES tab_estrutura(id),   -- PRINCIPAL (variante escolhida)
  conexao_id   INTEGER REFERENCES tab_estrutura(id),            -- CONEXAO  (nullable)
  fixacao_id   INTEGER REFERENCES tab_estrutura(id),            -- FIXACAO  (nullable)
  qtd_odi      REAL NOT NULL DEFAULT 0,
  qtd_odd      REAL NOT NULL DEFAULT 0,
  qtd_odm      REAL NOT NULL DEFAULT 0
);

CREATE INDEX idx_comp_estrutura ON tab_estrutura_componente(estrutura_id);
CREATE INDEX idx_pe_projeto      ON tab_projeto_estrutura(projeto_id);
