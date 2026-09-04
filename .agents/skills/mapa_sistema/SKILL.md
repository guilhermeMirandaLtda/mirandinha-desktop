---
name: mapa_sistema
description: >-
  Guia arquitetural, mapa de rotas, contratos de dados, tratamento de erros e diretrizes de desenvolvimento do ecossistema Mirandinha Desktop (pywebview + RPA + Análises Avançadas). Use sempre que for criar novas funcionalidades, adicionar robôs de RPA, expandir módulos analíticos, modificar a interface ou consultar as rotas e contratos da aplicação.
---

# Mapa do Sistema — Mirandinha (RPA & Análises Avançadas)

Este documento serve como mapa de bordo, fonte única de verdade arquitetural e catálogo de rotas/contratos normativos para o desenvolvimento no ecossistema do **Mirandinha**.

---

## 1. Visão Geral da Arquitetura e Comunicação

O aplicativo adota a arquitetura **Hybrid Desktop (pywebview + SPA Moderno)**:
- **Backend (Python 3.13+)**:
  - `app.py`: Inicializador da janela desktop nativa (1280x820) e do loop de eventos do `pywebview`.
  - `core/bridge.py`: Fachada (API Bridge) de comunicação segura entre JavaScript e Python (`window.pywebview.api`). Centraliza tratamento de exceções.
  - `core/rpa/runner.py`: Motor de execução de rotinas robóticas. Cada chamada `run_rpa_job` do frontend é despachada pelo pywebview em uma worker thread própria; `execute_job_sync` roda o robô nessa thread e emite logs/telemetria em tempo real via `window.evaluate_js`. **Execução serializada**: recusa iniciar (`RPA_BUSY` / `RuntimeError`) se já houver um robô ativo — nunca duas automações na mesma sessão SAP GUI.
  - `core/analytics/engine.py`: Motor de processamento estatístico. Detecção de anomalias por **IQR (Tukey fences)** — ponto fora de `Q1 - 1.5*IQR` ou `Q3 + 1.5*IQR`. Retorna média, mediana e desvio-padrão reais.
  - `core/storage.py`: Persistência local SQLite. `timestamp` em ISO 8601. Coluna `is_simulated`: execuções de robôs ainda não implementados são registradas para auditoria mas **excluídas** de `get_accumulated_kpis` e `get_dashboard_series`.
- **Frontend (Web SPA / Vanilla JS + CSS Tokens)**:
  - `web/index.html`: Shell da aplicação contendo as seções de visão (Views SPA).
  - `web/assets/css/tokens.css`: Variáveis globais baseadas no design system **Mofi** (`#7A70BA`, `#48A3D7`).
  - `web/assets/css/style.css`: Estilização dos componentes (cards KPI, tabelas, terminal console, sidebar).
  - `web/assets/js/app.js`: Gerenciador de estado client-side, rotas de visualização, consumo dos contratos da bridge.
  - `web/assets/js/charts.js`: Gerenciamento e renderização dos gráficos com Chart.js.

---

## 2. Mapa de Rotas e Navegação (Frontend Views)

A aplicação utiliza navegação client-side controlada pela função `window.appBridge.switchView(viewId)`.

| ID da View | Título da Página | Finalidade & Componentes Principais |
| :--- | :--- | :--- |
| `view-dashboard` | **Visão Geral do Sistema** | Banner com mascote Mirandinha, 4 KPIs executivos, gráfico semanal de execuções (`chart-activity`) e donut de categorias (`chart-distribution`). |
| `view-rpa` | **Central de Robôs RPA** | Catálogo organizado por grupos (ex: **1 Grupo: Materiais**). Ao executar: botão ganha cor de alerta pulsante (`.btn-running-pulse`), surge **Barra de Progresso** dinâmica (`#rpa-progress-panel`) com percentual e contagem em tempo real, acompanhada de botão **`[Parar / Cancelar]`** (`cancel_rpa_job`). Ao finalizar ou interromper, exibe **Card de Relatório** detalhado com Status, Tempo Total, Itens Processados e Falhas/Exceções. Console de logs com streaming (`#rpa-console-output`). |
| `view-analytics` | **Análises Avançadas** | Botões de geração demonstrativa e upload de CSV/Excel nativo (`select_file`), gráficos de tendências (`chart-analytics-trend`) e dispersão (`chart-analytics-scatter`). |
| `view-history` | **Histórico de Tarefas** | Auditoria e tabela de logs carregadas dinamicamente via `get_job_history()` com data/hora, processo, duração e quantidade de registros. |
| `view-settings` | **Configurações** | Parâmetros operacionais, seleção de diretório nativo (`select_folder`), níveis de log e preferências locais. |



---

## 3. Contrato Normativo da API Bridge (`Python <-> JavaScript`)

### 3.1 Padrão Único de Resposta (Caminho Feliz e Tratamento de Erro)
**TODO** método exposto na bridge (`core/bridge.py`) deve obrigatoriamente retornar a seguinte estrutura JSON:

```python
{
    "success": bool,
    "data": Any | None,
    "error": {
        "code": str,      # Ex: "TIMEOUT", "ELEMENT_NOT_FOUND", "FILE_NOT_FOUND", "DB_ERROR"
        "message": str,   # Mensagem clara para exibição ao usuário
        "details": str    # Traceback ou detalhe técnico resumido
    } | None
}
```

### 3.2 Métodos Disponíveis na Bridge

1. `get_available_jobs() -> StandardResponse`
   - **Autoridade**: O Python é a **única fonte da verdade** sobre os robôs disponíveis.
   - **Retorno (`data`)**: Lista de robôs registrados com `id`, `name`, `type`, `description`, `last_run`, `status`.

2. `run_rpa_job(job_id: str) -> StandardResponse`
   - **Entrada**: Identificador do robô (`job_id`).
   - **Retorno (`data`)**: `{"job_id", "job_name", "processed", "errors", "duration_seconds", "status", "is_simulated", "metadata"}`.
   - **Concorrência**: retorna `error.code = "RPA_BUSY"` se já houver automação em execução. A bridge verifica `rpa_runner._is_running` antes de delegar.
   - **Threading**: roda na worker thread que o pywebview cria para a chamada JS-API; não abrir threads adicionais.

3. `cancel_rpa_job() -> StandardResponse`
   - Sinaliza cancelamento cooperativo (`request_cancel`). O robô checa a flag entre itens e encerra com `status = "CANCELLED"`.

4. `is_rpa_running() -> StandardResponse`
   - **Retorno (`data`)**: `{"is_running": bool}`. Usado por `app.py::on_closing` para bloquear o fechamento durante execução.

5. `force_close_app() -> StandardResponse`
   - Destrói a janela pywebview de forma limpa (chamado pelo SweetAlert2 de confirmação de saída).

6. `get_system_kpis() -> StandardResponse`
   - **Retorno (`data`)**: `{"total_jobs", "total_items", "time_saved_hours", "success_rate" (None se sem dados), "has_data"}`. Apenas execuções reais.

7. `get_dashboard_series() -> StandardResponse`
   - **Retorno (`data`)**: `{"has_data", "week": {labels, executions, items}, "distribution": {labels, values}}` — últimos 7 dias, execuções reais. Alimenta os gráficos do dashboard.

8. `get_job_history(limit: int = 50) -> StandardResponse`
   - **Retorno (`data`)**: Últimos registros (inclui `timestamp` ISO, `timestamp_fmt` para exibição, `is_simulated`, `metadata` já desserializado).

9. `get_sample_analytics() -> StandardResponse`
   - **Retorno (`data`)**: Base sintética submetida à mesma análise de arquivos reais (`total_anomalies` via IQR, `mean_value`, `median_value`, `std_dev`, `trend`, `scatter`).

10. `analyze_file(file_path: str) -> StandardResponse`
   - **Entrada**: Caminho absoluto para `.csv`, `.xlsx` ou `.xls` (outros formatos → erro).
   - **Retorno (`data`)**: `{file_name, total_rows, numeric_columns, analyzed_column, total_anomalies (IQR), mean_value, median_value, std_dev, trend, scatter}`.

11. `select_file() -> StandardResponse`
   - **Retorno (`data`)**: Caminho absoluto selecionado via caixa nativa do Windows, ou `None` se cancelado.

12. `select_folder() -> StandardResponse`
   - **Retorno (`data`)**: Diretório absoluto selecionado, ou `None` se cancelado.

---

## 4. Diretrizes de Design System & Governança de Tokens

### 4.1 Mapeamento Estrito: Níveis de Log e Papéis Semânticos
Para manter conformidade com o Design System Mofi, nenhum componente pode usar cores arbitrárias. Todo log, status de badge ou alerta segue rigorosamente a matriz:

| Nível de Log | Papel Semântico | Variável CSS Token | Hex | Uso / Aplicação na Interface |
| :--- | :--- | :--- | :--- | :--- |
| `INFO` | Info / Secondary | `--color-info` | `#48A3D7` | Fluxo operacional normal e etapas concluídas |
| `SUCCESS` | Success | `--color-success` | `#2E8A5C` | Conclusão bem-sucedida de robôs e rotinas |
| `WARNING` | Warning | `--color-warning` | `#B67A1E` | Alertas, retentativas ou inconsistências brandas |
| `ERROR` | Danger | `--color-danger` | `#C6164F` | Falhas críticas, timeouts, interrupção de robôs |
| `DEBUG` | Tertiary / Muted | `--ink-muted` | `#8E8D9A` | Rastreamento técnico e detalhamento de chamadas |

### 4.2 Tipografia e Identidade Visual
- **Mascote Mirandinha**: Presente no cabeçalho e footer da sidebar como guardião do sistema.
- **Tipografia UI**: `Outfit` para toda a interface de usuário (títulos, cards, botões, modais).
- **Tipografia Técnica**: `JetBrains Mono` **exclusivamente** para logs de terminal, códigos e payloads JSON.

---

## 5. Regras de Engenharia para Novos Robôs RPA

1. **Catálogo Único**: Todo novo robô deve ser registrado em `AVAILABLE_JOBS` (`core/rpa/runner.py`). Nunca adicione robôs direto no JavaScript. O fallback de browser em `app.js` (usado só fora do pywebview) deve espelhar as descrições do catálogo Python.
2. **Robô real vs. simulado**: adicione o `job_id` a `RPARunner.REAL_JOBS` quando a automação de fato existir. Enquanto não existir, o job roda em modo simulação, é logado como tal e persiste com `is_simulated=1` (fora dos KPIs).
3. **Execução serializada**: nunca dispare um robô sem antes checar `_is_running`. A bridge já barra com `RPA_BUSY`; o frontend também barra via `activeRunningJobId`.
4. **Telemetria**: emita via `self.log(level, msg)`. A bridge serializa o payload com `json.dumps` antes de `evaluate_js` — não montar strings JS na mão.
5. **Tratamento de Exceções**: bloco crítico com `try...except Exception as e`, emitindo `log("ERROR", str(e))` e gravando o registro de falha (`status="FAILED"`, mesmo `is_simulated`) antes de propagar para a bridge.
6. **Persistência de Auditoria**: ao concluir, cancelar ou falhar, o status é obrigatoriamente persistido em `job_history`.

## 6. Frontend — regras de renderização

- Todo dado dinâmico inserido via `innerHTML` (nome de robô, `job_name`, caminho de arquivo, mensagem de log) passa por `escapeHtml()`.
- Os KPIs e gráficos do dashboard **nunca** exibem valores fixos de exemplo: sem dados reais, mostram `—` / vazio.
- `refreshData` não recarrega o catálogo de robôs enquanto `activeRunningJobId` estiver setado (evita resetar a UI de uma execução em andamento).
