---
name: studio
description: >-
  Referência normativa completa do módulo Studio — o editor visual no-code de automações SAP do Mirandinha (grafo de nós executado pelo GraphTask sobre o RPARunner). Contém as decisões-âncora inegociáveis, o modelo de dados do grafo, o catálogo completo dos 24 tipos de bloco, o formato da Biblioteca de Telas, a semântica de execução (laço, condicional e as 4 políticas de on_error), o contrato dos 17 métodos studio_* da bridge, o portão de publicação, o formato .mirflow.json de compartilhamento, receitas passo a passo (adicionar bloco, adicionar pack, criar fluxo, depurar) e o catálogo de armadilhas já descobertas. Use SEMPRE que for mexer em qualquer coisa dentro de core/studio/, core/rpa/tasks/graph_task.py, os métodos studio_* da bridge, web/assets/js/studio.js ou os grafos de exemplo — e antes de propor qualquer atalho arquitetural no módulo.
---

# Skill: Módulo Studio — Editor Visual No-Code de Automações

Este documento é a **fonte normativa** do módulo Studio do Mirandinha. O Studio permite que um
analista de materiais monte, veja rodando, publique e compartilhe uma automação de SAP **sem
escrever uma linha de código** — e que essa automação seja indistinguível de um robô nativo em
todo o resto do aplicativo.

> [!IMPORTANT]
> Antes de propor qualquer mudança estrutural no módulo, leia a seção **§0**. Ela lista as duas
> decisões que sustentam o desenho inteiro e os atalhos que **devem ser recusados**, mesmo que
> pareçam mais rápidos no momento.

---

## §0. As duas decisões-âncora (inegociáveis)

> **1. O grafo é _dado_, não código gerado.**
> **2. O interpretador do grafo é apenas mais uma task do `RPARunner`.**

Toda vez que a implementação oferecer um atalho que quebre uma dessas duas frases, o atalho é o
caminho errado. Estas duas frases são o que fez o Studio custar semanas em vez de meses.

### Atalhos que devem ser recusados

| Atalho tentador | Por que recusar |
| :--- | :--- |
| **Gerar Python a partir do canvas** | Vira duas implementações da mesma semântica (interpretador + gerador). Elas divergem, e você acaba depurando bug que só existe no script gerado. Se um dia for necessário, o gerador nasce do mesmo `NODE_CATALOG`. |
| **Criar um executor paralelo ao `RPARunner`** | Perde de graça: console em tempo real, barra de progresso, cancelamento gracioso, isolamento de falha por item, `peps_com_falha`, cálculo de ROI, gravação em `job_history`, KPIs e gráficos do dashboard. Tudo isso já existe e é herdado. |
| **Usar `eval()` / `exec()` na condição do `flow.if`** | Põe execução arbitrária de Python dentro de um JSON gravado em banco — e, com compartilhamento, dentro de um JSON que veio de outra pessoa. A condição é **sempre** três campos estruturados com operadores em dict fechado. |
| **Guardar o fluxo fora do SQLite** | O histórico de versões (`studio_flow_versions`) e a integração com `job_history` dependem de estar tudo no mesmo banco. |
| **O frontend interpretar `params`** (validar, converter, preencher default) | As duas pontas divergem e o fluxo passa a rodar diferente de como aparece na tela. **O canvas edita e desenha; o Python valida e executa.** `studio_node_catalog()` é a única fonte da forma dos parâmetros. |
| **Deixar um id cru do SAP GUI aparecer no grafo** | Mata o "no-code". Alvo de tela **sempre** vem da Biblioteca de Telas (`{"pack": ..., "ref": ...}`). Ver §4. |
| **Publicar um fluxo sem validar** | Um fluxo publicado vira código executável contra o SAP produtivo por um clique na Central de Robôs. O portão fica no publish (§8). |
| **Confiar no `is_published` de um arquivo importado** | Fluxo que veio de fora **sempre** chega como rascunho. Ver §9. |

---

## §1. Mapa de arquivos do módulo

### Backend

| Arquivo | Responsabilidade |
| :--- | :--- |
| `core/studio/node_catalog.py` | **Autoridade única** sobre os tipos de bloco: rótulo, categoria, parâmetros, portas, se exige `on_error`, e o flag `implemented`. Nada no frontend declara tipo por conta própria. |
| `core/studio/validator.py` | `validate_graph(graph) -> {"ok": bool, "issues": [...]}`. Nunca lança exceção sozinho — quem chama decide o que fazer com `ok=False`. |
| `core/studio/execution_context.py` | `ExecutionContext`: sessão SAP, variáveis do fluxo, item corrente do laço, e a resolução de `{{variavel}}` / `{{item.campo}}`. |
| `core/studio/screen_library.py` | A **Biblioteca de Telas**: carrega packs, resolve `{pack, ref}` → lista de ids candidatos, e (Etapa 6) empacota/instala packs no `.mirflow.json`. |
| `core/studio/summary.py` | `summarize_flow(graph)`: resumo heurístico de risco (transações, grava, elimina, insumos, `needs_review`) usado no portão de importação. |
| `core/studio/team_library.py` | Biblioteca da equipe: pasta de rede configurável, sem servidor. Config local por máquina. |
| `core/studio/screens/*.json` | Os packs da Biblioteca de Telas — hoje `cn52n`, `cj20n`, `me52n`, `mb22`. |
| `core/studio/samples/*.json` | Grafos de exemplo empacotados com o app. |
| `core/rpa/tasks/graph_task.py` | **`GraphTask(RPAJobBase)`** — o interpretador. Toda a semântica de execução mora aqui. |
| `core/rpa/runner.py` | `execute_graph_sync()` (rodar um grafo direto do canvas) e `_execute_published_flow()` (rodar um fluxo publicado pela Central). `get_catalog()` mescla `AVAILABLE_JOBS + list_published_flows()`. |
| `core/storage.py` | Tabelas `studio_flows` e `studio_flow_versions` + `save/get/list_studio_flow`, `set_studio_flow_published`, `list_published_flows`. |
| `core/bridge.py` | Os 17 métodos `studio_*` e `_emit_trace()`. |
| `scripts/run_flow.py` | Harness de CLI: `--seed`, `--validate`, `--list`, ou executar um grafo. **Roda sem UI nenhuma** — é o caminho mais rápido pra testar runtime. |

### Frontend

| Arquivo | Responsabilidade |
| :--- | :--- |
| `web/assets/js/studio.js` | `window.studioBridge` — galeria, canvas (Drawflow), inspetor, trace ao vivo, exportar/importar. |
| `web/assets/css/studio.css` | Estilos da galeria, do canvas, das cores por categoria de bloco e dos estados de trace. |
| `web/assets/vendor/drawflow/` | Drawflow 0.0.60 **vendorizado** (~46 KB). Sem CDN, sem `package.json`, sem build step. |
| `web/index.html` | `<section id="view-studio">` com duas telas: `#studio-gallery-view` e `#studio-editor-view`. |

### Testes

| Arquivo | Cobre |
| :--- | :--- |
| `tests/_fake_sap.py` | `FakeElement` / `FakeSapGuiSession` — sessão SAP falsa compartilhada. **Não é arquivo de teste** (prefixo `_` evita coleta pelo pytest). |
| `tests/test_studio_graph.py` | Validador, `ExecutionContext`, ciclo de vida do `GraphTask`. |
| `tests/test_screen_library.py` | Biblioteca de Telas + regressão dos ids contra o código nativo. |
| `tests/test_graph_task_handlers.py` | Os executores de nó, um a um, contra SAP falso. |
| `tests/test_graph_task_loop.py` | Laço, `flow.if`, as 4 políticas de `on_error`, e os dois grafos reais ponta a ponta. |
| `tests/test_graph_task_trace.py` | Trace ao vivo e a regra de limite de eventos. |
| `tests/test_runner_execute_graph.py` | `execute_graph_sync()`. |
| `tests/test_bridge_studio.py` | Contrato `{success, data, error}` dos métodos da bridge. |
| `tests/test_studio_publish.py` | Portão de publicação + catálogo mesclado. |
| `tests/test_studio_sharing.py` | `.mirflow.json`, bundle, portão de importação. |
| `tests/test_studio_team_library.py` | Biblioteca da equipe. |
| `tests/test_studio_samples.py` | Os grafos de exemplo (inclusive a asserção de "zero id cru"). |

---

## §2. Modelo de dados do grafo

### Envelope do fluxo

```json
{
  "schema_version": 1,
  "flow_id": "flow_cn52n_zerar_compromisso",
  "name": "Zerar Compromisso (CN52N)",
  "group": "Materiais",
  "transacao": "CN52N",
  "description": "Texto livre — vira a descrição no catálogo de robôs quando publicado.",
  "usage_steps": ["Passo 1...", "Passo 2..."],
  "variables": { "local_descarga": "." },
  "groups": [
    { "id": "g_preencher", "label": "Preencher tela", "collapsed": false }
  ],
  "nodes": [ /* ... */ ],
  "edges": [ /* ... */ ]
}
```

| Campo | Obrigatório | Observação |
| :--- | :--- | :--- |
| `flow_id` | **Sim** para salvar/publicar | Prefixo `flow_` é **semântico e obrigatório**: `execute_job_sync()` roteia por `job_id.startswith("flow_")`. |
| `name` | Sim na prática | Vira o nome na Central de Robôs. |
| `group` | Não | Agrupa na Central (acordeão). Default `"Studio"`. |
| `transacao` | Não | Vai pro `metadata.transacao` do histórico. Default `"AUTO"`. |
| `variables` | Não | Valores iniciais do contexto. **`params` passados na construção sobrescrevem estes.** |
| `groups` | Não | Só visual (agrupamento no canvas). Não afeta execução. |

### Nó (bloco)

```json
{
  "id": "n_014",
  "type": "sap.set_text",
  "label": "Quantidade = 0",
  "group_id": "g_preencher",
  "position": { "x": 340, "y": 372 },
  "params": {
    "target": { "pack": "cn52n", "ref": "campo_quantidade" },
    "value": "0"
  },
  "on_error": "skip_item",
  "error_label": "Item bloqueado ou somente leitura.",
  "retry": { "attempts": 0, "delay_ms": 500 },
  "timeout_ms": 5000,
  "needs_review": false
}
```

**Regras do nó:**

1. **`id` é estável e único.** É o que permite gravar em `job_history.metadata` qual bloco falhou e repintar o percurso depois. Nunca renomeie um `id` de um fluxo já publicado.
2. **`on_error` é obrigatório em todo bloco de ação** — sem default silencioso. Isentos: `flow.start`, `flow.end`, `flow.foreach`, `flow.if`, `flow.escape` (constante `_NO_ON_ERROR_TYPES` em `validator.py`).
3. **`label` é o que o operador lê.** Escreva como atividade ("Gravar"), não como mecânica ("pressionar btn[11]").
4. **`needs_review: true` bloqueia a publicação.** É o marcador de "isto aqui ainda precisa de decisão humana".
5. `retry` e `timeout_ms` estão no schema mas **`retry` ainda não é interpretado pelo runtime** — só `timeout_ms` do `sap.wait_for` é.

### Aresta

```json
{ "id": "e_031", "from": "n_013", "to": "n_014", "port": "out" }
```

**Portas válidas** (constante `VALID_PORTS`): `out` · `true` · `false` · `loop` · `done` · `error`

A porta é sempre do lado **de origem** (`from`). O destino tem uma entrada só.

---

## §3. Catálogo completo dos 24 blocos

> A tabela abaixo é gerada a partir de `core/studio/node_catalog.py`. **Se divergir, o Python
> está certo e este documento está desatualizado.** `?` = parâmetro opcional.

### Sessão & fluxo (cor: roxo / `df-cat-sessao`)

| Tipo | Rótulo | Parâmetros | Portas | `on_error` |
| :--- | :--- | :--- | :--- | :--- |
| `flow.start` | Início | — | `out` | isento |
| `sap.connect` | Conectar ao SAP | — | `out` | exige (default `abort`) |
| `sap.transaction` | Abrir transação | `tcode` | `out` | exige (default `abort`) |
| `flow.end` | Fim | — | — | isento |

### Interação de tela (cor: azul / `df-cat-tela`)

| Tipo | Rótulo | Parâmetros | Portas | Observação |
| :--- | :--- | :--- | :--- | :--- |
| `sap.set_text` | Escrever num campo | `target`, `value` | `out` | `value` aceita literal ou `{{variavel}}` |
| `sap.press` | Pressionar botão | `target` | `out` | |
| `sap.select` | Selecionar | `target`, `node?` | `out` | Sem `node` chama `.select()`; com `node` define `.selectedNode` |
| `sap.set_checkbox` | Marcar caixa | `target`, `checked` | `out` | |
| `sap.toolbar_press` | Acionar barra de ferramentas | `target`, `button` | `out` | O `pressButton("COMP_OVW")` da CJ20N |
| `sap.save` | Gravar | — | `out` | **Universal** — `wnd[0]/tbar[0]/btn[11]`, sem pack |
| `sap.back` | Voltar | — | `out` | **Universal** — `sendVKey(3)`, sem pack |

### Grid / ALV (cor: azul / `df-cat-grid`)

| Tipo | Rótulo | Parâmetros | Portas | Observação |
| :--- | :--- | :--- | :--- | :--- |
| `sap.grid_read` | Ler a grade | `target`, `columns`, `output_var?=linhas` | `out` | Cada linha ganha `_row` (índice). Cada coluna aceita `fallbacks` |
| `sap.grid_double_click` | Abrir detalhe (duplo clique) | `target`, `row`, `column` | `out` | `row` costuma ser `{{item._row}}` |

### Robustez (cor: âmbar / `df-cat-robustez`)

| Tipo | Rótulo | Parâmetros | Portas | Observação |
| :--- | :--- | :--- | :--- | :--- |
| `sap.wait_for` | Esperar elemento existir | `target`, `timeout_ms?=5000` | `out` · `error` | **Substitui `time.sleep()`.** Espera o elemento existir, não o relógio passar |
| `sap.handle_popup` | Tratar popup | `window?=wnd[1]`, `action`, `optional?=true` | `out` | `action` é **simbólica**: `ok`\|`yes`\|`no`\|`cancel` |
| `flow.assert_absent` | Conferir que fechou | `target`, `message` | `out` · `error` | Verificação **positiva** de sucesso |
| `flow.escape` | Rotina de escape | `sequence?`, `attempts?=3` | `out` | Chama `SapSession.safe_recover_state()` N vezes. `sequence` ainda não é interpretada |

### Lógica & dados (cor: verde / `df-cat-logica`)

| Tipo | Rótulo | Parâmetros | Portas | Observação |
| :--- | :--- | :--- | :--- | :--- |
| `flow.foreach` | Para cada | `source`, `item_var?=item` | `loop` · `done` | Define a unidade de progresso e de `skip_item`. **A porta `done` precisa apontar direto pra um `flow.end`** |
| `flow.if` | Se | `left`, `operator`, `right` | `true` · `false` | Operadores: `==` `!=` `>` `>=` `<` `<=` `contains` `empty` `not_empty` |

### Dados (cor: verde / `df-cat-dados`)

| Tipo | Rótulo | Parâmetros | Portas | Observação |
| :--- | :--- | :--- | :--- | :--- |
| `data.excel_read` | Ler planilha | `path`, `sheet?`, `columns`, `output_var?=linhas` | `out` | Cada coluna aceita `as` (apelido sem espaço). Cada linha ganha `_row` |
| `data.distinct` | Valores únicos | `source`, `field`, `output_var` | `out` | Os diagramas únicos da CJ20N |
| `data.first_match` | Localizar linha | `source`, `field`, `value`, `output_var` | `out` | O `df[df.Diagrama==x].iloc[0]` do robô nativo, como bloco |
| `data.format_date` | Formatar e validar data | `value`, `min_days?=-60`, `max_days?=730`, `output_var` | `out` · `error` | Guarda-corpo contra erro de ano. Saída `DD.MM.AAAA` |
| `data.log` | Registrar no console | `level?=INFO`, `message` | `out` | Os cinco níveis do design system |

### O mapa `categoria → cor` (frontend)

`studio.js` traduz a categoria do catálogo para a classe CSS. **Se você criar uma categoria
nova no `node_catalog.py`, precisa adicionar a entrada correspondente em
`STUDIO_CATEGORY_SLUG` (`studio.js`) e a regra `.drawflow-node.df-cat-<slug>` (`studio.css`)**,
senão o bloco renderiza com a cor de fallback (`tela`).

```javascript
const STUDIO_CATEGORY_SLUG = {
  'Sessão & fluxo': 'sessao',
  'Interação de tela': 'tela',
  'Grid / ALV': 'grid',
  'Robustez': 'robustez',
  'Lógica & dados': 'logica',
  'Dados': 'dados'
};
```

---

## §4. Biblioteca de Telas — o que torna o módulo no-code

### O problema que ela resolve

Um bloco que pede isto **não é no-code**:

```
wnd[0]/usr/subDETAIL_AREA:SAPLCNPB_M:1010/subVIEW_AREA:SAPLCOMD:2800
  /tabsTABSTRIP_2700/tabpMKAG/ssubSUBSCR_2700:SAPLCOMD:2701/txtRESBD-MENGE
```

É a mesma dificuldade de antes com uma borda arredondada em volta. Nenhum analista monta um robô
se o primeiro campo do formulário for esse.

### As duas camadas

- **Camada 1 — primitivas**: `sap.set_text`, `sap.press`... É o vocabulário do runtime. Aparece
  só no modo avançado.
- **Camada 2 — Biblioteca de Telas**: por transação, um catálogo de campos e botões com nome de
  gente. **É o que o usuário vê.**

> **Regra de ouro:** preencher a biblioteca é **tarefa técnica**. Montar o fluxo com o que ela
> expõe é **tarefa do analista**. Essa separação é o módulo inteiro.

### Formato do pack (`core/studio/screens/<pack>.json`)

```json
{
  "pack": "cj20n",
  "transacao": "CJ20N",
  "nome": "Project Builder (CJ20N)",
  "origem": "promovido de core/rpa/selectors/cj20n.json",
  "elementos": {
    "input_bdter": {
      "rotulo": "Data de necessidade",
      "tela": "Alteração em massa",
      "tipo": "campo_data",
      "id": "wnd[1]/usr/ctxtRESBD-BDTER",
      "fallbacks": []
    }
  }
}
```

### Vocabulário de `tipo`

| `tipo` | Usado por | Exemplo |
| :--- | :--- | :--- |
| `campo_texto` | `sap.set_text` | Quantidade (MENGE) |
| `campo_data` | `sap.set_text` | Data de necessidade (BDTER) |
| `botao` | `sap.press` | Confirmar busca |
| `checkbox` | `sap.set_checkbox` | Marcar eliminação (XLOEK) |
| `arvore` | `sap.select` | Árvore do projeto |
| `grid` | `sap.grid_read`, `sap.grid_double_click` | Grade ALV da CN52N |
| `painel` | `sap.wait_for`, `flow.assert_absent` | Área de detalhe do item |
| `janela_container` | `sap.toolbar_press` | Barra da visão geral de componentes |

O `tipo` é o que faz o formulário do inspetor se montar sozinho: um bloco *Escrever num campo* só
oferece elementos `campo_*`; um bloco *Marcar caixa* só oferece `checkbox`. **O usuário não
consegue montar uma combinação inválida porque ela não aparece na lista.**

### O que NÃO vai para um pack

| Não vai | Por quê |
| :--- | :--- |
| **Gravar / Voltar** (`btn[11]`, F3) | São universais em qualquer transação → viraram os blocos parameterless `sap.save` / `sap.back` |
| **Botões de popup** (`tbar[0]/btn[0]`, `SPOP-OPTION1/2`) | Universais → viraram a `action` simbólica de `sap.handle_popup` |
| **Barra de status** (`wnd[0]/sbar`) | Já é `SapSession.get_statusbar_text()` |

### Resolução de alvo em tempo de execução

```python
# GraphTask._resolve_target() devolve a LISTA de candidatos, em ordem
target = {"pack": "cn52n", "ref": "grid_alv"}   # → ["wnd[0]/usr/cntlALVCONTAINER/..."]
target = "wnd[0]/usr/txtX"                       # → ["wnd[0]/usr/txtX"]  (modo avançado)

# E SapSession.find_element_any() tenta cada um até achar
```

`fallbacks` existe porque a mesma tela varia entre variantes do SAP. **Um id que precise de
fallback deve ganhá-lo no pack, nunca um `try/except` espalhado no runtime.**

---

## §5. Semântica de execução

### O mapeamento sobre o `RPAJobBase`

`GraphTask` **herda** `RPAJobBase` — e o grafo se parte naturalmente nos quatro métodos abstratos:

| Método do `RPAJobBase` | Parte do grafo | Semântica de erro |
| :--- | :--- | :--- |
| `validate_input()` | Valida o grafo e **localiza** o `flow.foreach` (sem executar nada) | Levanta `ValueError` → job falha antes de começar |
| `prepare()` | Os nós **antes** do `foreach`: conectar, ler grade/planilha | **Falha aqui aborta o job inteiro** — sem isolamento por item, igual a qualquer task nativa |
| `get_work_items()` | Resolve o `source` do `foreach` para a lista real de itens | Levanta se não resolver para lista |
| `process_item()` | O **corpo do laço**, para UM item | **Falha aqui é isolada por item** pelo próprio `RPAJobBase.run()` |

### Dois modos de execução

| Modo | Quando | Como roda |
| :--- | :--- | :--- |
| **Linear** | Grafo **sem** `flow.foreach` | `prepare()` não faz nada. `get_work_items()` devolve `[1]`. `process_item()` percorre do `flow.start` ao `flow.end` como uma única "execução". |
| **Laço** | Grafo **com** `flow.foreach` | `prepare()` roda até o `foreach` (exclusive). Itens = `source` resolvido. `process_item()` roda o corpo (porta `loop`) por item. |

> [!WARNING]
> A `porta done` do `flow.foreach` **precisa apontar direto para um `flow.end`**. Nós depois do
> laço ainda não são suportados — `validate_input()` recusa com mensagem clara. Isso é uma
> limitação consciente, não um bug.

### As 4 políticas de `on_error`

| Política | Dentro do laço (`process_item`) | Na fase de preparo (`prepare`) |
| :--- | :--- | :--- |
| `abort` | Liga o flag interno `_abort_requested` **e** propaga → o laço para inteiro, status final vira `CANCELLED` | Propaga → job inteiro falha (`FAILED`) |
| `skip_item` | Propaga → `RPAJobBase` conta o erro, chama `recover_item_state()` e **vai para o próximo item** | **Comporta-se como `abort`** — não há "item" para pular. O runtime loga um aviso |
| `continue` | Engole o erro, loga `WARNING`, **segue para o próximo nó** pela porta `out` | Idem |
| `route` | Engole o erro e **desvia pela porta `error`** do nó | Idem |

**O truque do `abort` dentro do laço** (documentar antes de mexer): `RPAJobBase.run()` só
reconhece dois motivos para parar tudo — sessão SAP desconectada ou `cancel_check()` virar
`True`. Não existe um terceiro caminho nativo para "este nó específico deve derrubar o job, não
só pular o item". Por isso `GraphTask.__init__` **embrulha** o `cancel_check` externo:

```python
self._external_cancel_check = cancel_check or (lambda: False)
self._abort_requested = False
super().__init__(..., cancel_check=self._is_cancelled)

def _is_cancelled(self) -> bool:
    return self._abort_requested or self._external_cancel_check()
```

Consequência aceita: o status final vira `CANCELLED` (não `FAILED`). O log deixa claro o motivo
real.

### `flow.if` — nunca uma expressão avaliada

```python
_IF_OPERATORS = {
    "==": lambda a, b: a == b,          "!=": lambda a, b: a != b,
    ">":  lambda a, b: a > b,           ">=": lambda a, b: a >= b,
    "<":  lambda a, b: a < b,           "<=": lambda a, b: a <= b,
    "contains":  lambda a, b: b in a,
    "empty":     lambda a, b: not a,    "not_empty": lambda a, b: bool(a),
}
```

Dispatch em dict fechado. **Sem `eval`, sem `exec`, sem parser de expressão.** Operador fora
dessa lista levanta `ValueError`.

### Resolução de `{{variavel}}`

`ExecutionContext.resolve_value()`:

- `"{{linhas}}"` (placeholder sozinho) → devolve o **tipo original** (lista, dict, int...)
- `"Transação: {{nome}}"` (embutido em texto) → devolve **string interpolada**
- `"{{item.material}}"` → caminho pontilhado dentro do item corrente do laço
- Valor não-string (`42`, `True`, lista) → devolvido literal
- Variável inexistente → `KeyError` com nome da variável

> [!CAUTION]
> O regex de placeholder é `[a-zA-Z_][a-zA-Z0-9_.]*` — **não aceita espaços**. Uma coluna de
> Excel chamada `"Data Necessidade"` **não pode** ser referenciada como `{{linha.Data Necessidade}}`.
> Use o apelido `as` do `data.excel_read` (ver §10.3).

### Precedência de variáveis

```
graph["variables"]  →  sobrescrito por  →  params passados na construção do GraphTask
```

É assim que a Central de Robôs injeta `spreadsheet_path` do modal de execução num fluxo publicado.

---

## §6. Trace ao vivo

### Formato do evento

```json
{ "type": "node", "node_id": "n_014", "status": "running|done|error",
  "item_index": 37, "total": 500, "ms": 1240, "message": "Item bloqueado..." }

{ "type": "item", "item_index": 37, "total": 500,
  "status": "done|error", "ms": 4300, "message": "..." }
```

### A regra de limite (não remova)

> **Detalhe nó a nó apenas nos 3 primeiros itens. Do 4º em diante, um resumo por item — mais
> TODO erro, não importa o item.**

Motivo: 500 linhas × 8 blocos = **4.000 chamadas de `evaluate_js`** dentro do laço do SAP. Isso
deixa a execução mais lenta que o robô nativo e derruba o argumento do módulo inteiro. Os 3
primeiros itens são justamente quando o operador está conferindo se montou certo.

`self._current_item_index = 0` cobre a fase de preparo (`0 <= 3` é sempre verdadeiro), então ela
sempre traceia — e roda uma vez só, sem custo.

### Contrato com o frontend

```
GraphTask.trace_callback  →  RPARunner.trace_callback  →  MirandinhaBridge._emit_trace()
  →  evaluate_js("window.studioBridge.onTraceEvent({...})")  →  pinta o nó no canvas
```

`_emit_trace()` usa `json.dumps()` (mais seguro que a escapagem manual de string do `_emit_log`).
**Um callback de trace que quebra nunca pode derrubar uma execução contra o SAP** — por isso
`GraphTask._emit_trace()` engole exceções.

### Estados visuais

| Status | Classe CSS | Visual |
| :--- | :--- | :--- |
| `running` | `.trace-running` | Borda âmbar pulsante (respeita `prefers-reduced-motion`) |
| `done` | `.trace-done` | Borda verde |
| `error` | `.trace-error` | Borda vermelha (persiste) |

---

## §7. Contrato da bridge — os 17 métodos `studio_*`

Todos obedecem ao contrato normativo `{success, data, error}` do `mapa_sistema`.

| Método | `data` no sucesso | Códigos de erro |
| :--- | :--- | :--- |
| `studio_node_catalog()` | O `NODE_CATALOG` completo | `STUDIO_CATALOG_ERROR` |
| `studio_screen_packs()` | Resumo dos packs | `STUDIO_PACKS_ERROR` |
| `studio_list_flows()` | Fluxos salvos (sem o grafo) | `STUDIO_LIST_ERROR` |
| `studio_get_flow(flow_id)` | Fluxo + `graph` desserializado | `FLOW_NOT_FOUND`, `STUDIO_GET_ERROR` |
| `studio_validate_flow(graph)` | `{ok, issues[]}` | `STUDIO_VALIDATE_ERROR` |
| `studio_save_flow(graph, note?)` | `{flow_id, updated_at, version_id}` | `RPA_BUSY`, `FLOW_INVALID`, `STUDIO_SAVE_ERROR` |
| `studio_publish_flow(flow_id, publish)` | `{flow_id, is_published, updated_at}` | `RPA_BUSY`, `FLOW_NOT_FOUND`, `FLOW_INVALID`, `STUDIO_PUBLISH_ERROR` |
| `studio_list_samples()` | Exemplos empacotados | `STUDIO_SAMPLES_ERROR` |
| `studio_load_sample(filename)` | O grafo do exemplo | `SAMPLE_NOT_FOUND`, `STUDIO_SAMPLE_LOAD_ERROR` |
| `studio_run_flow(graph, params?)` | Mesmo shape de `run_rpa_job` | `STUDIO_EXECUTION_ERROR` |
| `studio_export_flow(graph)` | `{file_path, packs_incluidos}` ou `{cancelled: true}` | `WINDOW_NOT_READY`, `STUDIO_EXPORT_ERROR` |
| `studio_select_import_file()` | Caminho escolhido ou `None` | `DIALOG_ERROR` |
| `studio_inspect_mirflow(path)` | `{graph, summary, validation, packs_*, flow_id_ja_existe}` | `FILE_NOT_FOUND`, `MIRFLOW_INVALID` |
| `studio_import_mirflow(path)` | `{flow_id, packs_instalados, updated_at}` | `RPA_BUSY`, `MIRFLOW_INVALID`, `FLOW_INVALID` |
| `studio_get_team_library_path()` | Caminho ou `None` | `TEAM_LIBRARY_ERROR` |
| `studio_select_team_library_folder()` | Caminho escolhido (já gravado) | `DIALOG_ERROR` |
| `studio_list_team_library()` | Arquivos da pasta, com `summary` | `TEAM_LIBRARY_ERROR` |

### Regras de guarda

1. **`RPA_BUSY`**: `studio_save_flow`, `studio_publish_flow` e `studio_import_mirflow` recusam
   enquanto `rpa_runner._is_running` for `True` — mesma razão pela qual a Central já recusa
   disparar dois robôs de uma vez.
2. **`studio_validate_flow` nunca vira `error_response` por um grafo ruim.** `ok=False` é um
   **resultado válido** da chamada, não uma falha da bridge.
3. **`studio_load_sample` passa o nome por `os.path.basename()`** — sem travessia de diretório.

---

## §8. Publicação e o portão

### O que acontece ao publicar

```
studio_publish_flow(flow_id, True)
  → recusa se _is_running                          (RPA_BUSY)
  → recusa se o fluxo não existe                   (FLOW_NOT_FOUND)
  → validate_graph(): recusa se houver QUALQUER erro
  → recusa se houver QUALQUER nó com needs_review   (FLOW_INVALID + details com os ids)
  → set_studio_flow_published(flow_id, True)
```

**Despublicar (`publish=False`) não passa por nenhuma validação** — tirar de circulação é sempre
seguro.

### Como um fluxo publicado chega na Central

```python
# runner.py
def get_catalog(self):
    for job in AVAILABLE_JOBS + list_published_flows():   # ← o merge
        ...

def execute_job_sync(self, job_id, params=None):
    if job_id.startswith("flow_"):                        # ← o desvio
        return self._execute_published_flow(job_id, params)
    ...
```

`list_published_flows()` devolve **o mesmo shape de `AVAILABLE_JOBS`** (`id`, `group`, `name`,
`type`, `requires_file`, `description`, `usage_steps`, `last_run`, `status`) — por isso a Central
de Robôs não mudou uma linha. `requires_file` é **inferido** de haver ou não um nó
`data.excel_read` no grafo.

> [!IMPORTANT]
> `_execute_published_flow()` **recusa rodar um rascunho**. Um fluxo não publicado não pode ficar
> a um clique de mexer no SAP produtivo pela Central. Para testar um rascunho, o caminho é o
> botão **[Executar]** do próprio Studio (`studio_run_flow`), que não passa por ali.

---

## §9. Compartilhamento — `.mirflow.json`

### Formato do bundle

```json
{
  "mirflow_version": 1,
  "exported_at": "05/09/2026 12:00:00",
  "graph": { /* o grafo completo */ },
  "packs": { "cn52n": { /* o pack INTEIRO */ } }
}
```

**Auto-contido é o ponto.** Quem recebe pode não ter o pack (alguém de compras nunca instalou o
`cn52n`). Sem empacotar junto, o fluxo chega quebrado e a experiência morre na primeira tentativa.

`list_referenced_packs()` percorre **recursivamente** os `params` de cada nó procurando dicts com
`pack` **e** `ref` (ambos strings) — então um `{"pack": 123}` qualquer não vira falso positivo.

### Instalação de packs na importação

```python
# import_bundle_packs(): só instala o que FALTA
if path.exists():
    continue   # nunca sobrescreve
```

> **O pack local é sempre a autoridade.** Ele pode ter sido corrigido ou ganho `fallbacks` depois
> da versão que foi exportada. Sobrescrever regrediria a correção.

### O portão de importação

O resumo (`summarize_flow`) é mostrado **antes** do usuário confirmar:

| O resumo declara | Como é detectado |
| :--- | :--- |
| Transações que toca | `graph.transacao` + os `tcode` literais dos nós `sap.transaction` |
| Se **grava** | Existe algum nó de tipo em `_WRITE_TYPES` |
| Se **elimina/exclui** | **Heurística** por palavras-chave no rótulo+params: `elimina`, `exclu`, `delet`, `cancela`, `estorn`, `xloek`, `encerr`, `conclu` |
| Insumos que exige | Colunas declaradas nos nós `data.excel_read` |
| Blocos sem revisão | `needs_review: true` |

> [!NOTE]
> A detecção de "elimina" é **heurística, não prova formal**. É um sinal para o operador olhar
> com atenção. Um fluxo com nome de campo fora do vocabulário conhecido pode escapar.

**Regras invioláveis da importação:**

1. **Um fluxo importado NUNCA chega publicado.** Vale inclusive quando se reimporta por cima de
   um fluxo que já estava publicado localmente — a publicação cai. Republicar é decisão de quem
   importa, não de quem compartilhou.
2. Isso é forçado explicitamente com `set_studio_flow_published(flow_id, False)` **depois** do
   save, porque o `UPDATE` de `save_studio_flow` **não toca** a coluna `is_published`.
3. `origem` do fluxo vira `"importado"` no banco.

### Biblioteca da equipe

Uma **pasta de rede**, sem servidor. O caminho fica em `core/studio/team_library.json` — config
**local por máquina** (cada analista aponta pra sua unidade mapeada), por isso está no
`.gitignore`. A galeria lista os `.mirflow.json` de lá já com o `summary` embutido no card
(chip **vermelho** quando elimina/exclui, **azul** quando só grava).

---

## §10. Receitas passo a passo

### §10.1 Adicionar um novo tipo de bloco

Checklist completo — **pular um passo gera erro só em tempo de execução**:

1. **`core/studio/node_catalog.py`** — adicionar a entrada:
   ```python
   "sap.scroll_grid": {
       "label": "Rolar a grade",
       "category": "Grid / ALV",
       "params": [
           {"name": "target", "kind": "target", "required": True},
           {"name": "rows", "kind": "number", "required": False, "default": 10},
       ],
       "ports": ["out"],
       "needs_on_error": True,
       "implemented": True,          # ← False até o executor existir
       "description": "Rola N linhas na grade ALV.",
   },
   ```
2. **`core/rpa/tasks/graph_task.py`** — escrever o executor:
   ```python
   def _h_sap_scroll_grid(self, node: Dict[str, Any]):
       params = node.get("params", {})
       candidates = self._resolve_target(params["target"])
       rows = int(self.ctx.resolve_value(params.get("rows", 10)))
       grid = self.sap.find_element_any(candidates)
       grid.firstVisibleRow = grid.firstVisibleRow + rows
   ```
3. **`core/rpa/tasks/graph_task.py`** — registrar no dict `self._handlers`:
   ```python
   "sap.scroll_grid": self._h_sap_scroll_grid,
   ```
4. **Se a categoria for nova**: adicionar em `STUDIO_CATEGORY_SLUG` (`studio.js`) e a regra
   `.drawflow-node.df-cat-<slug>` (`studio.css`).
5. **Teste** em `tests/test_graph_task_handlers.py`, com `FakeElement`.
6. **Verificar a consistência** catálogo ↔ executores:
   ```bash
   python -c "
   from core.studio.node_catalog import NODE_CATALOG
   from core.rpa.tasks.graph_task import GraphTask
   impl = {k for k,v in NODE_CATALOG.items() if v['implemented']} - {'flow.start','flow.end','flow.foreach','flow.if'}
   h = set(GraphTask(graph={'nodes':[],'edges':[]}, cancel_check=lambda: False)._handlers)
   print('sem handler:', impl - h); print('sem implemented:', h - impl)
   "
   ```
   **Ambos os conjuntos devem sair vazios.**

> `flow.start`, `flow.end`, `flow.foreach` e `flow.if` **não têm entrada em `_handlers`** de
> propósito — são tratados diretamente pelo caminhador (`_run_chain`), nunca por `_execute_node_in_chain`.

### §10.2 Adicionar um pack (nova transação)

1. Criar `core/studio/screens/<tcode>.json` no formato do §4.
2. Para cada elemento: `rotulo` (nome de gente), `tela` (onde aparece), `tipo` (do vocabulário),
   `id` (o caminho cru) e `fallbacks` (se houver variação conhecida).
3. **Não incluir** Gravar/Voltar/botões de popup/barra de status (ver §4).
4. Teste de regressão em `tests/test_screen_library.py` comparando o `id` contra a string literal
   do robô nativo equivalente, se existir:
   ```python
   def test_mb52_campo_x_bate_com_o_codigo_original(self):
       self.assertEqual(resolve_candidates("mb52", "campo_x"), ["wnd[0]/usr/ctxtRM07M-XYZ"])
   ```
   Isso trava o pack contra a fonte da verdade: se alguém editar e divergir, o teste quebra.

### §10.3 Criar um fluxo guiado por planilha

O padrão do Data Necessidade — **decorar este esqueleto**:

```json
{
  "nodes": [
    { "id": "n_start",  "type": "flow.start", "params": {} },
    { "id": "n_connect","type": "sap.connect","params": {}, "on_error": "abort" },
    { "id": "n_read", "type": "data.excel_read", "on_error": "abort",
      "params": {
        "path": "{{spreadsheet_path}}",
        "columns": [
          { "name": "PEP",              "as": "pep" },
          { "name": "Diagrama",         "as": "diagrama" },
          { "name": "Data Necessidade", "as": "data_necessidade" }
        ],
        "output_var": "linhas"
      }
    },
    { "id": "n_distinct", "type": "data.distinct", "on_error": "abort",
      "params": { "source": "{{linhas}}", "field": "diagrama", "output_var": "diagramas" } },
    { "id": "n_foreach", "type": "flow.foreach",
      "params": { "source": "{{diagramas}}", "item_var": "diagrama" } },

    { "id": "n_lookup", "type": "data.first_match", "on_error": "skip_item",
      "params": { "source": "{{linhas}}", "field": "diagrama",
                  "value": "{{diagrama}}", "output_var": "linha" } },
    { "id": "n_data", "type": "data.format_date", "on_error": "skip_item",
      "params": { "value": "{{linha.data_necessidade}}", "output_var": "data_formatada" } },

    { "id": "n_end", "type": "flow.end", "params": {} }
  ],
  "edges": [
    { "id": "e4", "from": "n_foreach", "to": "n_lookup", "port": "loop" },
    { "id": "e9", "from": "n_foreach", "to": "n_end",    "port": "done" }
  ]
}
```

**Os três detalhes que sempre esquecem:**

1. O `as` das colunas — **coluna com espaço não é referenciável em template** (§5).
2. `data.first_match` existe porque `data.distinct` devolve **strings soltas**, perdendo o
   vínculo com a linha original. É o `df[df.Diagrama==x].iloc[0]` do robô nativo.
3. A porta `done` do `foreach` vai **direto** pro `flow.end`.

### §10.4 Testar sem SAP e sem pywebview

```bash
# 1. Validar um grafo (nunca toca no SAP)
python scripts/run_flow.py --validate core/studio/samples/cn52n_zerar_compromisso.json

# 2. Rodar um grafo de verdade (precisa do SAP aberto)
python scripts/run_flow.py core/studio/samples/cn52n_grid_read.json

# 3. Listar os fluxos salvos no banco
python scripts/run_flow.py --list

# 4. Suíte completa
python -m pytest tests/ -q
```

**Para testar o frontend sem o pywebview**: subir `python -m http.server` dentro de `web/` e
abrir no navegador — `file://` vira snapshot estático e não executa JS. A API não existirá; o
`studioBridge.init()` mostra um aviso. Para exercitar de verdade, injete um stub:

```javascript
window.pywebview = { api: {
  studio_node_catalog: () => Promise.resolve({success: true, data: {/* catálogo */}}),
  studio_list_samples: () => Promise.resolve({success: true, data: []}),
  studio_list_flows:   () => Promise.resolve({success: true, data: []}),
  studio_list_team_library: () => Promise.resolve({success: true, data: []}),
}};
window.studioBridge.init();
```

---

## §11. Regras de engenharia (o que sempre / nunca fazer)

### Sempre

1. **Todo bloco de ação declara `on_error`.** Sem default silencioso.
2. **Todo alvo de tela vem da Biblioteca de Telas.** Id cru só no modo avançado/migração.
3. **`escapeHtml()` em todo dado do grafo antes de `innerHTML`.** Rótulo de nó, nome de fluxo,
   caminho de arquivo — tudo pode ter sido escrito por outra pessoa e chegado por importação.
4. **Espera é `sap.wait_for`, nunca `time.sleep()`.** Esperar o elemento existir, não o relógio
   passar.
5. **Sucesso é verificado positivamente** com `flow.assert_absent` (ou equivalente) — "a tela de
   detalhe continuou aberta" significa que a gravação falhou.
6. **Rodar a suíte inteira antes de commitar.** `python -m pytest tests/ -q`.
7. **Commit + push ao fim de cada etapa.** O módulo já foi perdido uma vez inteiro por não estar
   versionado.

### Nunca

1. **Nunca `eval`/`exec`** para condição, expressão ou qualquer coisa vinda do grafo.
2. **Nunca sobrescrever um pack local** na importação.
3. **Nunca publicar sem validar**, nem confiar em `is_published` de arquivo externo.
4. **Nunca deixar o canvas interpretar `params`.** O Python é a autoridade.
5. **Nunca instanciar o Drawflow com o container invisível** (`display:none`) — ele mede
   dimensões erradas. Criar só quando o editor de fato aparece.
6. **Nunca deixar um callback de UI derrubar execução contra o SAP.** `_emit_trace` engole
   exceções por isso.
7. **Nunca renomear o `id` de um nó de fluxo publicado** — quebra a rastreabilidade no histórico.

---

## §12. Convenções de teste

### O banco é isolado — e precisa continuar sendo

`tests/conftest.py` tem uma fixture **autouse, escopo de sessão** que aponta
`core.storage.DB_PATH` para um SQLite temporário durante toda a suíte:

```python
@pytest.fixture(autouse=True, scope="session")
def banco_de_testes_isolado():
    ...
    storage.DB_PATH = str(tmp_db)
    yield str(tmp_db)
    storage.DB_PATH = original_db_path
```

Isso existe porque **já aconteceu o contrário**: a suíte gravou 19 fluxos e 30 execuções no
`mirandinha_history.db` real do desenvolvedor. Quatro deles ficaram **publicados** — ou seja,
apareceram na Central de Robôs como robôs executáveis de verdade, e as execuções falsas
inflaram os KPIs do dashboard.

> [!WARNING]
> Nunca escreva um teste que chame `save_studio_flow()`, `set_studio_flow_published()` ou
> `record_job_execution()` contando com o banco real. Se precisar de um `DB_PATH` diferente
> num teste específico, sobreponha localmente — mas **não remova a fixture global**.

Funciona porque `DB_PATH` só é lido **dentro** de `core/storage.py`, sempre como global em
tempo de chamada. Se algum módulo passar a fazer `from core.storage import DB_PATH`, esse
binding escapa da fixture e o isolamento quebra silenciosamente.

### A sessão SAP falsa

`tests/_fake_sap.py` implementa **só o que os executores realmente chamam**:

```python
from tests._fake_sap import FakeElement, FakeSapGuiSession

task = GraphTask(graph=graph, cancel_check=lambda: False)
task.sap.session = FakeSapGuiSession({"wnd[0]/usr/txtX": FakeElement()})
task.sap.connect = lambda: task.sap.session         # não tocar win32com real
task.sap.start_transaction = lambda tcode: None
task.ctx.sap = task.sap
```

Para simular comportamento dinâmico (painel que abre no duplo clique e fecha ao gravar),
**subclasse o `FakeElement`** — ver `_GridComAberturaDeDetalhe` e `_FecharPainelAoSalvar` em
`tests/test_graph_task_loop.py`.

### Mock de `record_job_execution`

```python
@patch("core.rpa.runner.record_job_execution")   # ✅ o nome LIGADO no módulo runner
@patch("core.storage.record_job_execution")      # ❌ não tem efeito
```

`runner.py` faz `from core.storage import record_job_execution` no topo — o nome já está ligado
no namespace do `runner` quando o teste roda.

---

## §13. Armadilhas conhecidas (todas já custaram tempo)

| Armadilha | Realidade |
| :--- | :--- |
| **"O job falhou porque o item falhou"** | **Não.** `RPAJobBase.run()` isola falha por item: o job termina `SUCCESS` com `errors > 0` e os itens em `peps_com_falha`. Só vira `FAILED` se a exceção escapar do laço inteiro (ex.: sessão SAP caiu). Escrever teste esperando `FAILED` para um item que falhou é erro. |
| **`skip_item` numa fase de preparo** | Não existe "item" antes do `foreach` — comporta-se como `abort`. |
| **Coluna de Excel com espaço em template** | `{{linha.Data Necessidade}}` **não funciona** — o regex não aceita espaço. Use `"as": "data_necessidade"`. |
| **Drawflow com container escondido** | Instanciar com `display:none` mede dimensões zeradas. Criar só em `showEditor()`. |
| **Console do Studio vazio durante execução** | `_emit_log`/`_emit_progress` são **compartilhados** entre robôs nativos e fluxos do Studio — `appendLog` espelha nos dois consoles de propósito. |
| **`save_studio_flow` não reseta `is_published`** | O `UPDATE` não toca a coluna. Import força `set_studio_flow_published(flow_id, False)` explicitamente. |
| **`renderJobsTable` usava `innerHTML` sem escapar** | Era inofensivo com `AVAILABLE_JOBS` estático; virou vetor real quando fluxos do Studio (nome escrito pelo usuário) entraram no catálogo. Corrigido com `escapeHtml()` global em `app.js`. |
| **Popup precisa de pack?** | **Não.** `action` é simbólica (`ok`/`yes`/`no`/`cancel`) → ids universais. |
| **Trace lento** | Se a execução ficar arrastada, confira se alguém removeu o limite dos 3 primeiros itens (§6). |
| **Teste gravando no banco real** | `save_studio_flow`/`record_job_execution` usam `DB_PATH` global. Sem a fixture de `tests/conftest.py`, a suíte polui o `mirandinha_history.db` do desenvolvedor — inclusive publicando fluxos de teste na Central de Robôs. Ver §12. |
| **Pack de teste sobrando em `screens/`** | `import_bundle_packs()` escreve arquivo de verdade. Teste que exercita importação de pack **precisa** de `addCleanup(lambda: path.unlink(missing_ok=True))`. |

---

## §14. O que ainda NÃO existe

Ser explícito aqui evita prometer o que não há:

| Não existe | Situação |
| :--- | :--- |
| **Canvas editável** | O inspetor é **somente leitura**. Não há arrastar bloco da paleta nem editar parâmetro pela interface. Um fluxo novo hoje nasce editando JSON ou clonando um exemplo. |
| **Validação com SAP real** | Tudo que foi testado é Python puro contra SAP falso, ou navegador com `pywebview.api` simulado. A integração real de ponta a ponta **nunca foi executada**. |
| **Importador de VBScript** | Estava no plano v1 como acelerador (`vbs_parser.py`). Saiu do caminho crítico e não foi implementado. |
| **Nós depois do laço** | A porta `done` do `foreach` precisa ir direto pro `flow.end`. |
| **`retry` por nó** | Está no schema, não é interpretado. |
| **`sequence` do `flow.escape`** | Está no schema; o runtime usa `SapSession.safe_recover_state()` fixo. |
| **Execução passo a passo / breakpoint** | Fora de escopo — o trace ao vivo cobre "ver onde quebrou". |
| **Múltiplas sessões SAP em paralelo** | Serialização é decisão deliberada do sistema, não limitação a corrigir. |

---

## §15. Glossário

| Termo | Significado |
| :--- | :--- |
| **Grafo / fluxo** | O JSON que descreve a automação. É dado, nunca código. |
| **Bloco / nó** | Uma entrada de `nodes[]`. Tipo vem do `NODE_CATALOG`. |
| **Porta** | O ponto de saída de um nó (`out`, `loop`, `done`, `true`, `false`, `error`). |
| **Pack** | Um arquivo da Biblioteca de Telas, por transação. |
| **Ref** | A chave de um elemento dentro de um pack (`input_bdter`). |
| **Bundle / `.mirflow.json`** | Grafo + packs referenciados, auto-contido, para compartilhar. |
| **Portão** | A validação obrigatória antes de publicar (§8) ou ao importar (§9). |
| **Trace** | O fluxo de eventos que pinta os blocos ao vivo durante a execução (§6). |
| **Rascunho vs publicado** | Rascunho só roda pelo Studio; publicado aparece e roda pela Central de Robôs. |
