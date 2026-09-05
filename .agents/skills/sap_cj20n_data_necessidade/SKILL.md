---
name: sap_cj20n_data_necessidade
description: >-
  Especialista na automação SAP GUI CJ20N (Data Necessidade / Reprogramação de Componentes de Diagramas de Rede). Contém mapa de controles do SAP Scripting, validação de planilha de insumos, rotina de alteração em massa (Mass Change), cálculo de ROI/tempo economizado, telemetria de métricas para o dashboard do Mirandinha e procedimentos de contingência. Use sempre que for modificar a automação Data Necessidade, ajustar tempos de execução manual vs robô, calibrar regras de parsing de datas ou auditar indicadores de produtividade.
---

# Skill: Automação SAP CJ20N — Data Necessidade

Este documento é a referência técnica especializada e fonte normativa para a automação da transação **CJ20N** (Project Builder) no ecossistema **Mirandinha**, com foco na reprogramação em lote das datas de necessidade de componentes de diagramas de rede e na captura de telemetria para os dashboards executivos.

---

## 1. Contexto de Negócio & Missão do Robô

No planejamento e suprimentos de obras e manutenção, a data de necessidade dos componentes atrelados aos diagramas de rede frequentemente sofre reprogramações em razão de prazos logísticos, reprogramação de cronogramas de projetos ou realocação de frentes de serviço.

Manualmente, a reprogramação de diagramas na transação **CJ20N** é um processo altamente moroso: o analista precisa abrir a transação, buscar o diagrama de rede pelo número de ordem, expandir a árvore de projeto, acessar a visão geral de componentes (`COMP_OVW`), acionar a alteração em massa, selecionar o campo `RESBD-BDTER`, preencher a nova data, executar a alteração, confirmar na barra de ferramentas, salvar e confirmar eventuais popups de advertência para cada diagrama.

O robô **1.1. Data Necessidade** automatiza integralmente essa cadeia operacional diretamente a partir de uma planilha Excel de insumos, processando dezenas de diagramas de forma consistente, com validação de formato e gravação segura no ERP.

---

## 2. Requisitos e Estrutura da Planilha de Insumos

A automação requer obrigatoriamente um arquivo Excel (`.xlsx` ou `.xls`) contendo as seguintes colunas de cabeçalho:

| Coluna | Tipo / Formato | Obrigatória | Finalidade |
| :--- | :--- | :--- | :--- |
| **`PEP`** | Texto / Código PEP | Sim | Elemento PEP de referência para auditoria e rastreabilidade (ex: `01-0001-24.01.01`) |
| **`Diagrama`** | Número / Texto (AUFNR) | Sim | Número do Diagrama de Rede / Ordem no SAP (ex: `40001234`) |
| **`Data Necessidade`** | Data (`DD/MM/AAAA` ou `AAAA-MM-DD`) | Sim | Nova data a ser atribuída a todos os componentes do diagrama |

> [!NOTE]
> A aplicação oferece download direto da planilha modelo contendo 3 exemplos práticos pelo botão **"Baixar Planilha Modelo (Exemplos)"** no modal de execução do robô.

---

## 3. Mapa Técnico de Controles do SAP GUI Scripting (CJ20N)

| Etapa / Ação | ID do Controle SAP GUI | Descrição Técnica |
| :--- | :--- | :--- |
| **Transação** | `/ncj20n` | Início limpo da transação Project Builder |
| **Abrir Projeto/Diagrama** | `wnd[0]/shellcont/shellcont/shell/shellcont[0]/shell/shellcont[0]/shell` (Button `"OPEN"`) | Botão de busca e abertura de objetos na barra lateral da árvore |
| **Filtro PEP / Projeto** | `wnd[1]/usr/ctxtCNPB_W_ADD_OBJ_DYN-PROJ_EXT` / `...-PRPS_EXT` | Limpos com string vazia para evitar conflito na busca |
| **Campo Diagrama** | `wnd[1]/usr/ctxtCNPB_W_ADD_OBJ_DYN-AUFNR` | Preenchido com o número do diagrama |
| **Confirmar Abertura** | `wnd[1]/tbar[0]/btn[0]` | Confirmação de seleção do diagrama |
| **Árvore de Projeto** | `wnd[0]/shellcont/shellcont/shell/shellcont[0]/shell/shellcont[1]/shell` | Seleção do nó (`selectedNode = "000002"` ou fallback `"000001"`) |
| **Visão Componentes** | `wnd[0]/usr/subDETAIL_AREA:SAPLCNPB_M:1010/cntlTOOLBAR_CONTAINER_OVERVIEW/shellcont/shell` (Button `"COMP_OVW"`) | Abre a lista/grid de componentes do diagrama |
| **Alteração em Massa** | `.../tabsTABSTRIP_2700/tabpALLE/ssubSUBSCR_2000:SAPLCOMK:2701/btnICON_SYSTEM_COPY` | Aciona a função de alteração em massa dos componentes |
| **Desmarcar Todos** | `wnd[1]/usr/btnMALO_F` | Desmarca flags preexistentes |
| **Flag Data Necessidade**| `wnd[1]/usr/chkFLG_MARK_RESBD-MARK_BDTER` | Marcado como `True` (`selected = True`) |
| **Campo Data Necessidade**| `wnd[1]/usr/ctxtRESBD-BDTER` | Preenchido com a data formatada no padrão do SAP (`DD.MM.AAAA`) |
| **Marcar Todas Linhas**| `wnd[1]/usr/btnMAAL` | Propaga o valor para todas as posições dos componentes |
| **Confirmar Alteração** | `wnd[1]/tbar[0]/btn[13]` (ou `btn[0]`) | Confirmação da alteração em massa na modal |
| **Salvar Alterações** | `wnd[0]/tbar[0]/btn[11]` | Grava o diagrama atualizado no SAP |
| **Popup Confirmação** | `wnd[1]/usr/btnSPOP-OPTION1` (ou `btn[0]`) | Confirmação de gravação em caso de popups de validação |
| **Contingência / Escape**| `wnd[1].close()` -> `btn[3]` (F3) -> `btnSPOP-OPTION2` (Não Salvar) | Descarta telas abertas e recupera o estado em caso de falha |

---

## 4. Modelo de Telemetria & Cálculo de ROI Defensável

A transação CJ20N possui complexidade operacional consideravelmente superior a transações de modificação direta em grade (como CN52N):

### 4.1 Metodologia de Aferição e Cronometria
Para assegurar a defensabilidade dos números em auditorias executivas e de controladoria, os parâmetros foram medidos com base em cronometria direta de amostragem operacional (10 execuções manuais típicas realizadas por analistas de suprimentos/projetos):

| Etapa Operacional Manual | Duração Cronometrada | Descrição da Atividade do Analista |
| :--- | :--- | :--- |
| **1. Inicialização e Busca** | ~20 segundos | Digitação de `/ncj20n`, acionamento do botão OPEN e busca pelo número do diagrama (`AUFNR`). |
| **2. Navegação na Estrutura** | ~15 segundos | Expansão da árvore do projeto e seleção do nó de operações de rede com componentes. |
| **3. Acesso à Visão de Componentes** | ~25 segundos | Abertura do container `COMP_OVW`, carregamento da lista e acionamento da alteração em massa (`ICON_SYSTEM_COPY`). |
| **4. Alteração em Massa e Aplicação** | ~30 segundos | Desmarcação de campos anteriores, marcação do flag `RESBD-BDTER`, inserção manual da data, propagação (`btnMAAL`) e confirmação (`btn[13]`/`btn[0]`). |
| **5. Gravação e Tratamento de Popups** | ~30 segundos | Comando Salvar (`btn[11]`), espera pelo commit no banco do SAP e confirmação de avisos de advertência orçamentária/calendário. |
| **Total Manual por Diagrama Concluído** | **120 segundos (2,0 min)** | Soma representativa do ciclo completo sem retrabalho. |
| **Tempo de Triagem de Exceção / Falha** | **60 segundos (1,0 min)** | Tempo gasto pelo analista tentando acessar diagrama bloqueado por terceiros, verificando bloqueio em `SM12` e registrando a inconsistência em planilha de controle. |

- **Tempo Médio do Robô Mirandinha**: **~6 a 9 segundos por diagrama**.
- **Preservação de Ganho em Falha/Cancelamento**: Em caso de cancelamento pelo operador ou queda de sessão, as horas poupadas dos diagramas já concluídos ou diagnosticados são mantidas no banco de dados.

### 4.2 Fórmula Ponderada de Cálculo (Correção Aritmética)
Para evitar a sobrestimação de ganhos com itens que falharam, adota-se a fórmula ponderada e defensável:

$$\text{Tempo Manual Estimado} = (\text{Diagramas com Sucesso} \times 120\text{ s}) + (\text{Diagramas com Exceção/Falha} \times 60\text{ s})$$
$$\text{Tempo Economizado Líquido} = \max\left(0.0,\, \text{Tempo Manual Estimado} - \text{Duração Robô}\right)$$

*(Caso a execução seja interrompida logo no início e a duração do robô supere o tempo manual estimado, adota-se como piso de auditoria o esforço parcial: $\text{sucessos} \times 60\text{ s} + \text{erros} \times 60\text{ s}$).*

---

## 5. Metadados Gravados para Auditoria no Histórico (`mirandinha_history.db`)

Exemplo auditado com base na fórmula ponderada (35 sucessos $\times$ 120s + 2 erros $\times$ 60s = 4.200s + 120s = 4.320s estimados manuais):

```json
{
  "job_id": "job_mat_data_necessidade",
  "transacao": "CJ20N",
  "modulo": "Materiais",
  "tipo": "SAP / Gestão de Materiais",
  "data_inicio": "04/09/2026 15:20:10",
  "data_fim": "04/09/2026 15:23:45",
  "motivo_finalizacao": "Concluído com Sucesso",
  "itens_concluidos": 35,
  "erros_contagem": 2,
  "total_itens_triados": 37,
  "tempo_manual_estimado_segundos": 4320.0,
  "tempo_robo_segundos": 215.3,
  "horas_poupadas": 1.14,
  "peps_com_falha": [
    {
      "linha": 4,
      "pep": "01-0004-24.01.02",
      "material": "Diagrama 40001299",
      "motivo": "Diagrama 40001299 bloqueado pelo usuário U9999 no SAP."
    }
  ]
}
```

---

## 6. Procedimentos de Contingência, Governança e Blindagem de Riscos

### 6.1 Guard-rails de Sanidade de Data
O robô intercepta erros de digitação grosseiros antes do envio ao SAP:
- **Janela Permitida**: Apenas datas entre **-60 dias** (passado recente) e **+24 meses** (horizonte padrão de planejamento de projetos).
- **Tratamento de Inconsistências**: Anos invertidos (ex.: `2062`) ou datas fora da janela disparam `ValueError`, abortando a linha e registrando o diagnóstico na planilha de falhas para correção humana.

### 6.2 Prevenção de Gravação Indevida no Escape
O acionamento de `btnSPOP-OPTION2` na rotina `_recover_state` é precedido pela inspeção semântica do texto da janela modal (`wnd[1]`). Caso a modal não represente uma confirmação de descarte ("Deseja salvar antes de sair?", "Save data first?"), o robô aciona a tecla de cancelamento `btn[12]` (F12) e F3 sem forçar cliques cegos em botões de confirmação.

### 6.3 Documentação dos Fallbacks de Interface
- **Nós da Árvore (`000002` vs `000001`)**:
  - `000002`: Padrão do Project Builder quando o diagrama de rede possui o nível superior de elemento PEP de projeto aberto na árvore.
  - `000001`: Diagrama autônomo sem vinculação hierárquica na raiz do browser.
- **Botões de Confirmação (`btn[13]` vs `btn[0]`)**:
  - `btn[13]`: Botão padrão de aceite da tela modal de Mass Change em versões SAP GUI 7.70+.
  - `btn[0]`: Enter clássico de confirmação utilizado em instâncias SAP com parametrização de tela reduzida.

### 6.4 Versão de Homologação do SAP GUI
- **Ambiente Homologado**: **SAP GUI for Windows 7.70 / 8.00 (Patch Level 4+)**, tema **Quartz** ou **Belize**, com SAP GUI Scripting habilitado no servidor (`sapgui/user_scripting = TRUE`) e sem bloqueio de popups no cliente.

### 6.5 Compliance de Credenciais e Rastreabilidade
- Toda execução é realizada estritamente sob a **sessão ativa do usuário logado** no SAP Logon.
- As gravações em lote no SAP ficam vinculadas ao login de rede (`SY-UNAME`) do analista operador.
- O campo `PEP` da planilha de insumos garante a rastreabilidade cruzada entre o lote automatizado e a autorização de trabalho emitida pela gerência.

### 6.6 Procedimento Formal de Rollback
O SAP não dispõe de funcionalidade "desfazer" nativa para alterações de componentes da CJ20N. Em caso de execução com datas incorretas, seguir o protocolo de reversão:
1. **Identificação do Lote**: Consultar a view **Histórico de Tarefas** do Mirandinha e abrir os Detalhes da execução afetada para recuperar os diagramas processados.
2. **Re-execução com Planilha Corretiva**: Gerar uma nova planilha contendo a mesma lista de diagramas e a data correta anterior (ou a data reprogramada), executando novamente a automação.
3. **Auditoria de Histórico SAP**: Caso seja necessário resgatar a data original que existia antes da automação, o analista deve consultar as tabelas de documentos de modificação do SAP (`CDHDR` e `CDPOS` para o objeto de rede/ordem) para extrair o valor anterior do campo `RESBD-BDTER`.
