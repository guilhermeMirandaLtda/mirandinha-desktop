# Protótipo — Módulo de Orçamento de Obra

Protótipo isolado para validar o modelo de dados, o fluxo de uso e o motor de cálculo
**antes** de implementar no Mirandinha. Roda no navegador com SQLite real (`sql.js`/WASM).

## Como rodar

**Abra `index.html`** (duplo-clique). O WASM do SQLite e o schema+seed ficam embutidos
em `js/sql-wasm-inline.js` e `js/data.js` — não há `fetch()`, não precisa de servidor.

Opcional, para desenvolvimento: `python -m http.server 8777` → <http://127.0.0.1:8777>.

## Vínculo por FAMÍLIA (ODI ↔ ODD ↔ ODM)

`COD_ERP = <letra de perfil> + <família>`:

| 1ª letra | perfil | significado |
|---|---|---|
| `I` | **ODI** | obra de investimento — instalação nova (todos os materiais) |
| `D` | **ODD** | obra por demanda — retirada da estrutura antiga (amarração + mão de obra) |
| `M` | **ODM** | obra de manutenção (rara na LISTA TÉC — geralmente não existe) |

`IEMT015` e `DEMT015` são a **mesma família `EMT015`**. O usuário escolhe **uma vez**
(a variante ODI, que representa a família) + Conexão + Fixação, e digita quantidade em
**ODI / ODD / ODM**. No cálculo, cada coluna resolve automaticamente o `COD_ERP` da
mesma família para aquele perfil (`ODI → IEMT015`, `ODD → DEMT015`) e explode os
componentes daquela variante no bucket do perfil. Se a família não tem variante para
o perfil digitado, a quantidade é ignorada com aviso.

O badge `ODI ODD ODM` em cada linha do catálogo mostra quais perfis a família cobre.

## Fluxo — wizard de 3 passos

**1 · Estruturas** — catálogo de famílias PRINCIPAL agrupado por `GRUPO_COMPONENTE`
(`ESTRUT MT`, `POSTE`…). Em cada linha: **Conexão** e **Fixação** em select
(famílias CONEX MT / FIX CB MT), quantidade em **ODI / ODD / ODM**, botão **+**.
Carrinho lateral com subtotal. Clicar na **família** abre o slide-over com os
componentes reais do kit (colunas da LISTA TÉC).

**2 · Projeto** — identificação da obra, **município** (`tab_km` → km do transporte)
e **empresa executora** (`tab_empresa` → preços de serviço), custos indiretos, recursos.

**3 · Resumo** — a `capa`: KPIs, resumo ODI/ODD/LV/Total, origem dos recursos,
materiais e serviços agregados, memória de cálculo (com a coluna KIT) e CSV.

## Modelo (tabelas `tab_*`) — alinhado à aba **LISTA TÉC**

| Tabela | Papel | Colunas da LISTA TÉC |
|---|---|---|
| `tab_estrutura` | catálogo de KITs | `GRUPO_COMPONENTE`, `COD_ERP`, `DESC_ERP` + `familia`, `perfil` (I/D/M → ODI/ODD/ODM) + `tipo_kit` (PRINCIPAL/CONEXAO/FIXACAO) |
| `tab_estrutura_componente` | itens do kit (material E serviço) | `IND_PRINCIPAL`, `COD_MATERIAL`/`COD_SERVICO`, `DESC_*`, `QTD_*`, `UND_MATERIAL`, `TIPO_APLICACAO` |
| `tab_projeto_estrutura` | lançamentos | qtd ODI/ODD/ODM **+ `conexao_id` + `fixacao_id`** (guardam a variante escolhida; os irmãos são resolvidos no cálculo) |
| `tab_projeto` | cabeçalho + empresa + município + % engenharia + recursos | — |
| `tab_preco_material` | preço **global**, com `peso_kg` | — (vem de PREÇO-MATERIAL no sistema real) |
| `tab_preco_servico` | preço **por empresa** (PK `codigo + empresa_id`) | — (vem de CONTRATO) |
| `tab_km`, `tab_param`, `tab_empresa` | apoio | KM |

`tipo_kit` sai do `GRUPO_COMPONENTE`: `CONEX *` → CONEXAO, `FIX CB *` → FIXACAO,
resto → PRINCIPAL. Por lançamento e por perfil com quantidade, o motor resolve a
variante (`Cache.variante`), explode `PRINCIPAL + CONEXAO + FIXACAO` daquela variante,
agrega por `(tipo, codigo, perfil)` e precifica. (`FIX ESTRUT MT`, fixação da cruzeta
no poste, ainda entra como PRINCIPAL — vira 3º select quando decidirmos.)

## Desempenho

Todos os preços, componentes e parâmetros são carregados **uma vez** em `Map`s
(`Cache` em `engine.js`) e invalidados a cada escrita. Sem isso o cálculo fazia
uma query por componente (N+1). Medições com **305 lançamentos**:

| Operação | Tempo |
|---|---|
| montar o cache | ~3 ms |
| `calcular()` completo | ~15 ms |
| render do resumo | ~43 ms |
| abrir um bloco da memória (lazy) | ~0,6 ms |

Outras decisões: catálogo renderizado uma vez com **eventos delegados**; filtro por
busca/grupo só alterna `hidden` (sem re-render); persistência no `localStorage`
com **debounce** de 250 ms; memória de cálculo montada só ao abrir o bloco.

## Arquivos

```
index.html             UI + design system
js/app.js              wizard, catálogo, carrinho, telas
js/engine.js           Cache + custoCombo() + calcular()
js/db.js               sql.js, versionamento, persistência debounced, export/import
sql/schema.sql         DDL canônico (portável ~1:1 para o Mirandinha)
sql/seed.sql           GERADO por build_seed.py
build_seed.py          LÊ a aba LISTA TÉC da planilha e extrai KITs curados + preços sintéticos
build_data.py          embute schema+seed+wasm nos .js (rodar após editar os .sql)
```

Editou `sql/schema.sql`? → **incremente `PRAGMA user_version`** no topo,
depois `python build_seed.py && python build_data.py` e recarregue.
`build_seed.py` precisa da planilha em `E:\NOVO TOMBAMENTO MA 2022-09-21.xlsx`
(ou passe o caminho: `python build_seed.py "D:\...\arquivo.xlsx"`).
`build_data.py` só precisa dos `.sql` já gerados.

### Versionamento do banco

O banco fica salvo no `localStorage`. Ao abrir, o app compara o `user_version` do
banco salvo com o do `schema.sql`: se forem diferentes (ou o banco estiver ilegível),
ele **descarta e recria** a partir do schema + seed, avisando por toast. Sem isso, uma
mudança de coluna quebrava o app com erros do tipo `no such column: e.un`.

Para não perder um orçamento antes de mudar o schema, use **Exportar .sqlite**.

## Ainda em aberto

1. **ODM**: nesta LISTA TÉC quase não há `MEBT*/MEMT*` — a classificação ODM/ODS aparece
   só no `TIPO_APLICACAO` de componentes dentro dos kits `I`. Decidir se ODM continua
   como coluna de quantidade (resolvendo `M...` quando existir) ou some.
2. **FIX ESTRUT MT** (fixação da cruzeta no poste, varia por poste) — 3º select ao lado
   de Conexão/Fixação, ou embutido no kit PRINCIPAL?
3. Regra real de **transporte** (faixas de km, truck × carreta).
4. Origem da **% de engenharia** (fixa / faixa / tabela).
5. **ETL completo** da LISTA TÉC (3.294 COD_ERP) + preços reais de PREÇO-MATERIAL / CONTRATO.
6. Cadastro de **novos componentes** pelo slide-over (hoje lista e exclui).
7. Exportação **.xlsx/PDF** no layout da capa.
