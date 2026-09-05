---
name: mapa_sistema
description: >-
  Guia arquitetural, mapa de rotas, contratos de dados, tratamento de erros e diretrizes de desenvolvimento do ecossistema Mirandinha Desktop (pywebview + RPA + Análises Avançadas). Use sempre que for criar novas funcionalidades, adicionar robôs de RPA, expandir módulos analíticos, modificar a interface ou consultar as rotas e contratos da aplicação.
---

# Mapa do Sistema — Mirandinha v3.0.4 (RPA & Análises Avançadas)

Este documento serve como mapa de bordo, fonte única de verdade arquitetural e catálogo de rotas/contratos normativos para o desenvolvimento no ecossistema do **Mirandinha v3.0.4**.

---

## 1. Visão Geral da Arquitetura e Comunicação

O aplicativo adota a arquitetura **Hybrid Desktop (pywebview + SPA Moderno)**:
- **Backend (Python 3.13+)**:
  - `app.py`: Inicializador da janela desktop nativa (1280x820) e do loop de eventos do `pywebview`. Título oficial: `Mirandinha v3.0.4 — RPA & Análises Avançadas`.
  - `core/bridge.py`: Fachada (API Bridge) de comunicação segura entre JavaScript e Python (`window.pywebview.api`). Centraliza tratamento de exceções e filtros de período.
  - `core/rpa/runner.py`: Motor de execução de rotinas robóticas assíncronas (execução isolada em `threading.Thread(daemon=True)`) com emissão de logs estruturados em tempo real, preservação de métricas parciais em caso de falha/cancelamento e registro de início e fim.
  - `core/analytics/engine.py`: Motor de processamento estatístico, detecção de outliers e diagnósticos com Pandas/NumPy.
  - `core/storage.py`: Camada de persistência local SQLite (`mirandinha_history.db`) com suporte a auditoria detalhada de itens, tempo poupado de triagem e consultas agregadas por período (`start_date` e `end_date`).
- **Frontend (Web SPA / Vanilla JS + CSS Tokens)**:
  - `web/index.html`: Shell da aplicação contendo as seções de visão (Views SPA), badge `v3.0.4` na sidebar, barra de filtro de período com inputs de data e modais operacionais.
  - `web/assets/css/tokens.css`: Variáveis globais baseadas no design system **Mofi** (`#7A70BA`, `#48A3D7`).
  - `web/assets/css/style.css`: Estilização dos componentes (cards KPI, tabelas, terminal console, sidebar, modais).
  - `web/assets/js/app.js`: Gerenciador de estado client-side, rotas de visualização, consumo da bridge, exportação Excel e filtro padrão por mês atual.
  - `web/assets/js/charts.js`: Gerenciamento e renderização dos gráficos com Chart.js e plugin ChartDataLabels com rótulos de dados nos pontos.

---

## 2. Mapa de Rotas e Navegação (Frontend Views)

A aplicação utiliza navegação client-side controlada pela função `window.appBridge.switchView(viewId)`.

| ID da View | Título da Página | Finalidade & Componentes Principais |
| :--- | :--- | :--- |
| `view-dashboard` | **Visão Geral do Sistema** | Banner de boas-vindas com Mirandinha 3D, **Barra de Filtro de Período** (De/Até por data com padrão Mês Atual, botões Filtrar/Mês Atual/Limpar), 4 KPIs executivos dinâmicos (Automações, Tempo Economizado, Taxa de Sucesso, Itens Processados), gráfico temporal (`chart-activity`) com rótulos de dados e donut de categorias (`chart-distribution`). |
| `view-rpa` | **Central de Robôs RPA** | Catálogo com status e data da última execução (`last_run`). Ao executar: botão pulsante (`.btn-running-pulse`), **Barra de Progresso** dinâmica (`#rpa-progress-panel`) com percentual e contagem em tempo real, botão **`[Parar / Cancelar]`** (`cancel_rpa_job`). Ao finalizar ou interromper, exibe **Card de Relatório** detalhado com Status Final, Início/Fim, Tempo Total, Itens Processados, Exceções e Tempo Economizado (ROI), além de tabela de PEPs com falha e botão de exportar para Excel. Console de logs com streaming (`#rpa-console-output`). |
| `view-analytics` | **Análises Avançadas** | Botões de geração demonstrativa e upload de CSV/Excel nativo (`select_file`), gráficos de tendências (`chart-analytics-trend`) e dispersão (`chart-analytics-scatter`). |
| `view-history` | **Histórico de Tarefas** | Auditoria completa com data/hora, processo, duração formatada (horas/min/seg), total de itens e botão **Detalhes**. Ao clicar em Detalhes, abre modal rica com: Início, Fim, Motivo/Tipo de Finalização, Balanço detalhado (sucessos vs falhas), tabela de PEPs com exceção com exportação Excel (.xlsx) e payload de telemetria. |
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

2. `run_rpa_job(job_id: str, params: dict = None) -> StandardResponse`
   - **Entrada**: Identificador do robô (`job_id`) e parâmetros opcionais (`params`, ex: `spreadsheet_path`).
   - **Retorno (`data`)**: Objeto rico de telemetria contendo:
     ```python
     {
         "job_id": str,
         "job_name": str,
         "processed": int,
         "errors": int,
         "duration_seconds": float,
         "status": "SUCCESS" | "CANCELLED" | "FAILED",
         "metadata": {
             "transacao": str,
             "modulo": str,
             "tipo": str,
             "data_inicio": str,
             "data_fim": str,
             "motivo_finalizacao": str,
             "tempo_manual_estimado_segundos": float,
             "tempo_robo_segundos": float,
             "horas_poupadas": float,
             "itens_concluidos": int,
             "erros_contagem": int,
             "total_itens_triados": int,
             "peps_com_falha": list[dict]
         },
         "peps_com_falha": list[dict]
     }
     ```
   - **Garantia de Threading**: Disparado em thread dedicada (`threading.Thread(daemon=True)`).
   - **Persistência**: Grava automaticamente a auditoria e telemetria no banco local SQLite (`mirandinha_history.db`).

3. `get_job_history(limit: int = 50) -> StandardResponse`
   - **Entrada**: Quantidade máxima de registros de auditoria a retornar.
   - **Fonte**: Tabela `job_history` do SQLite (`mirandinha_history.db`).
   - **Retorno (`data`)**: Lista ordenada dos últimos jobs executados (timestamp, nome, duração, itens, status, erro_resumo, metadata).

4. `export_peps_to_excel(peps_list: list, job_name: str = "PEPs_Falha") -> StandardResponse`
   - **Finalidade**: Exportação de itens/PEPs com exceção para arquivo `.xlsx` via seletor nativo do Windows.

5. `download_template_excel(template_type: str = "data_necessidade") -> StandardResponse`
   - **Finalidade**: Geração e download de planilha modelo com 3 exemplos práticos pré-preenchidos.

6. `get_system_kpis(start_date: str = None, end_date: str = None) -> StandardResponse`
   - **Entrada**: Período opcional em formato ISO (`YYYY-MM-DD`).
   - **Retorno (`data`)**: `{"total_jobs": int, "total_items": int, "time_saved_hours": float, "success_rate": float}`.

7. `get_dashboard_chart_data(start_date: str = None, end_date: str = None) -> StandardResponse`
   - **Entrada**: Período opcional em formato ISO (`YYYY-MM-DD`).
   - **Retorno (`data`)**: `{"activity": {"labels": [...], "jobs": [...], "items": [...]}, "distribution": {"labels": [...], "data": [...]}}`.

8. `cancel_rpa_job() -> StandardResponse`
   - **Finalidade**: Interrupção graciosa imediata da rotina em execução preservando dados já processados no banco.

9. `get_sample_analytics() -> StandardResponse`
   - **Retorno (`data`)**: Estatísticas agregadas e séries numéricas prontas para visualização gráfica.

10. `analyze_file(file_path: str) -> StandardResponse`
    - **Entrada**: Caminho absoluto para arquivo `.csv` ou `.xlsx`.
    - **Retorno (`data`)**: Resumo estatístico do dataset selecionado.

11. `select_file() -> StandardResponse`
    - **Retorno (`data`)**: Caminho absoluto selecionado pelo usuário via caixa nativa do Windows, ou `None` se cancelado.

12. `select_folder() -> StandardResponse`
    - **Retorno (`data`)**: Diretório absoluto selecionado pelo usuário, ou `None` se cancelado.

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

## 5. Regras de Engenharia para Robôs RPA (Framework RPAJobBase)

1. **Herança Obrigatória**: Todo robô RPA herda de `RPAJobBase` (`core/rpa/base.py`) e utiliza `SapSession` (`core/rpa/sap_session.py`), implementando os métodos abstratos `validate_input()`, `prepare()`, `get_work_items()` e `process_item()`.
2. **Catálogo Oficial (4 Robôs Integrados)**:
   - `1.1 Data Necessidade` (`job_mat_data_necessidade`): CJ20N, $120\text{ s}$/$60\text{ s}$, planilha `PEP`, `Diagrama`, `Data Necessidade`.
   - `1.2 Zerar Compromisso` (`job_mat_zerar_compromisso`): CN52N, $45\text{ s}$/$25\text{ s}$, direto em grade ALV.
   - `1.3 Concluir Requisições` (`job_mat_concluir_requisicoes`): ME52N, $45\text{ s}$/$25\text{ s}$, planilha `Requisicao`, `Item`.
   - `1.4 Eliminar Reserva` (`job_mat_eliminar_reserva`): MB22, $40\text{ s}$/$20\text{ s}$, planilha `Reserva`, `Item`.
3. **Seletores Declarativos**: IDs de telas SAP residem em arquivos JSON externos em `core/rpa/selectors/*.json` (ex: `cj20n.json`, `me52n.json`, `mb22.json`).
4. **Garantia de Thread-Safety**:
   - Todo job roda em uma thread dedicada para não travar a janela desktop (`pywebview`).
   - Emissões de telemetria chamam `self.log(level, msg)`. O dispatcher sanitiza strings antes de passar para `evaluate_js`.
5. **Persistência de Auditoria com Versionamento**: Ao concluir ou falhar, o status do job, `job_version` e `engine_version` são obrigatoriamente persistidos no SQLite (`mirandinha_history.db`).

---

## 6. Diretrizes de Tratamento de Erros, Resiliência e Contingência

Esta seção estabelece o protocolo padrão de detecção, tratamento, isolamento e diagnóstico de falhas em todas as camadas do Mirandinha:

### 6.1 Matriz de Erros por Camada e Padrão de Resposta

| Camada | Tipo de Erro Comum | Protocolo de Tratamento | Impacto na Aplicação |
| :--- | :--- | :--- | :--- |
| **SAP GUI Scripting** | Queda de rede / Sessão fechada (`-2147417848`, `RPC server unavailable`) | Interrupção imediata via `RuntimeError`, preservando contadores em `self.sucessos`, `self.erros` e gravando no banco com status `FAILED`. | Robô é suspenso com segurança; métricas parciais são salvas; usuário é notificado. |
| **SAP GUI Scripting** | Item bloqueado / Erro de tela transiente | Acionamento da **rotina de escape** (`btn[12]`, `btn[3]`, confirmação de descarte), adição do item à lista `peps_com_falha` e avanço para a próxima linha da grade. | O lote continua normalmente; o item problemático vai para o relatório de exceções exportável. |
| **Python / RPA Runner** | Falha interna de execução (ex: `NameError`, bug de lógica) | Captura no bloco `except Exception as exc` do `execute_job_sync`: coleta métricas parciais de `task_instance`, calcula tempo poupado de triagem, persiste no SQLite e repassa erro à bridge. | A aplicação desktop permanece 100% responsiva; histórico registra o erro com diagnóstico. |
| **Bridge (`core/bridge.py`)** | Exceções de I/O, banco ou parâmetros | Captura com `try...except`, retornando `error_response(code, message, details)` com formato JSON padronizado. | O frontend recebe a resposta estruturada e exibe alerta visual sem quebrar o JavaScript. |
| **Frontend / UI Desktop** | Tentativa de fechar janela com robô rodando | Interceptação em `app.py` (`on_closing`) e no navegador (`beforeunload`): dispara modal de confirmação SweetAlert2. | Impede que o usuário feche a janela por acidente e interrompa gravações no SAP. |

### 6.2 Princípios Obrigatórios para Tratamento de Erros

1. **Nunca Zerar Trabalho Realizado (Preservação de ROI)**:
   - Em caso de falha no item $N$, todos os itens processados de $1$ a $N-1$ devem ser computados.
   - O tempo de triagem manual economizado deve ser registrado no banco mesmo para execuções com status `FAILED` ou `CANCELLED`.
2. **Diagnóstico Legível para o Analista**:
   - Falhas em itens do SAP devem registrar: `linha`, `pep`, `material` e `motivo` claro da recusa.
   - Toda exceção crítica deve conter mensagem amigável no topo e detalhes técnicos preservados no payload `metadata`.
3. **Contingência de Queda de Conexão**:
   - É terminantemente proibido deixar o robô executando em loop infinito tentando interagir com uma janela do SAP que foi desconectada. A verificação de COM desconectado deve provocar a interrupção imediata da rotina.
4. **Resiliência do Banco SQLite**:
   - Toda operação de persistência deve utilizar gerenciador de contexto `with sqlite3.connect(...)` com `conn.commit()` explícito para evitar *database locked* ou arquivos corrompidos.
