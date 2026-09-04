# Mirandinha — RPA & Análises Avançadas

Aplicativo desktop para automação de rotinas no SAP e análise de dados operacionais,
construído com **pywebview** (janela nativa) + **SPA em Vanilla JS**.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![pywebview](https://img.shields.io/badge/pywebview-5.x-7A70BA)
![SQLite](https://img.shields.io/badge/storage-SQLite-003B57)

---

## O que faz

| Módulo | Descrição |
|---|---|
| **Central de Robôs RPA** | Catálogo de automações com execução, barra de progresso, cancelamento gracioso, console de logs em tempo real e relatório de execução. A rotina **Zerar Compromisso** automatiza a transação SAP **CN52N** via SAP GUI Scripting. |
| **Análises Avançadas** | Importa CSV/Excel e extrai estatísticas (média, mediana, desvio-padrão) e **detecção de anomalias por IQR** (Tukey fences). |
| **Histórico & Auditoria** | Toda execução é persistida em SQLite com duração, itens processados, status e metadados da transação. |
| **Dashboard** | KPIs consolidados e gráficos alimentados por dados reais — sem números de exemplo. |

## Arquitetura

```
app.py                      janela pywebview + ciclo de vida
core/
  bridge.py                 API Python ↔ JS (contrato { success, data, error })
  rpa/runner.py             motor de execução, catálogo de robôs, cancelamento
  rpa/tasks/                automações (ex.: SAP CN52N via win32com)
  analytics/engine.py       Pandas/NumPy — estatística e outliers (IQR)
  storage.py                SQLite: histórico, KPIs e séries do dashboard
web/                        SPA (HTML + CSS tokens + Vanilla JS + Chart.js)
prototipo_orcamento/        protótipo isolado do módulo de Orçamento de Obra
.agents/skills/             mapa arquitetural e contratos (fonte da verdade)
```

**Contrato da bridge** — todo método exposto ao frontend retorna:

```python
{ "success": bool, "data": Any | None, "error": {"code", "message", "details"} | None }
```

## Como rodar

```bash
pip install -r requirements.txt
python app.py
```

> A automação SAP exige **Windows**, `pywin32`, o SAP Logon aberto e o *SAP GUI Scripting*
> habilitado no cliente e no servidor.

## Protótipo — Módulo de Orçamento de Obra

Em [`prototipo_orcamento/`](prototipo_orcamento/) há um protótipo isolado (roda no navegador,
sem servidor, com **SQLite real via sql.js/WASM**) que valida o modelo de dados e o motor de
cálculo de orçamentos de obras de distribuição elétrica antes de integrar ao app.

Wizard de 3 passos: **Estruturas → Projeto → Resumo**, reproduzindo a capa de orçamento
(materiais + serviços + transporte + engenharia, rateados por ODI/ODD/ODM).

Detalhes e decisões de modelagem: [`prototipo_orcamento/README.md`](prototipo_orcamento/README.md).

## Convenções

- Robôs são registrados **apenas** em `core/rpa/runner.py` — o Python é a fonte única da verdade.
- Robôs sem automação real rodam em modo simulação e são gravados com `is_simulated = 1`,
  ficando **fora** dos indicadores.
- Execução serializada: nunca duas automações na mesma sessão do SAP GUI.
- Todo dado dinâmico no frontend passa por `escapeHtml()` antes de ir para `innerHTML`.

---

© Guilherme Miranda
