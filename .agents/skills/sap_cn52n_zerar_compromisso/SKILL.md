---
name: sap_cn52n_zerar_compromisso
description: >-
  Especialista na automação SAP GUI CN52N (Zerar Compromisso de Materiais). Contém mapa de campos do SAP Scripting, cálculo de ROI/tempo economizado, telemetria de métricas para o dashboard do Mirandinha e regras de contingência. Use sempre que for modificar a automação CN52N, calibrar tempos de execução manual vs robô ou extrair indicadores de produtividade.
---

# Skill: Automação SAP CN52N — Zerar Compromisso de Materiais

Este documento é a referência técnica especializada para a automação da transação **CN52N** no ecossistema **Mirandinha**, com foco em precisão operacional e captura de metadados de produtividade para os dashboards executivos.

---

## 1. Contexto de Negócio & Missão do Robô

Na gestão de suprimentos e projetos, reservas de materiais atreladas a elementos PEP e ordens canceladas continuam bloqueando saldo de estoque como "compromisso". A liquidação manual desses itens exige abrir ordem por ordem, navegar até a aba de componentes e alterar campos individualmente.

O robô **1.2. Zerar Compromisso** automatiza essa rotina diretamente na grade ALV da transação **CN52N**, devolvendo o saldo imediatamente ao estoque livre.

---

## 2. Mapa Técnico de Controles do SAP GUI Scripting

| Ação | ID do Controle SAP GUI | Descrição Técnica |
| :--- | :--- | :--- |
| **Grid ALV Principal** | `wnd[0]/usr/cntlALVCONTAINER/shellcont/shell` | Contêiner ALV com lista de reservas |
| **Coluna PEP** | `POSID` / `POSID_EDIT` | Identificador do Elemento PEP |
| **Coluna Material** | `MAKTX` / `MATXT` | Descrição do material |
| **Drill-down** | Coluna `FLMNG` (Double Click) | Abre a tela de detalhe do componente |
| **Aba Detalhes** | `wnd[0]/tbar[1]/btn[13]` (Node `26`) | Navegação interna para campos de quantidade |
| **Campo Quantidade** | `txtRESBD-MENGE` | Alterado para `"0"` |
| **Campo Descarga** | `txtRESBD-ABLAD` | Alterado para `"."` |
| **Salvar** | `wnd[0]/tbar[0]/btn[11]` | Grava as alterações |
| **Popup Orçamento** | `wnd[1]/tbar[0]/btn[0]` | Confirmação automática de avisos de orçamento |
| **Escape / Contingência** | `btn[12]` (F12) e `btn[3]` (F3) + `btnSPOP-OPTION2` | Retorno seguro à grade ALV em caso de erro |

---

## 3. Modelo de Telemetria & Cálculo de Tempo Economizado (ROI)

Para alimentar os KPIs do Dashboard (**Tempo Economizado** e **Registros Processados**), adota-se a seguinte calibração métrica:

### 3.1 Parâmetros de Produtividade
- **Tempo Médio de Processamento Manual**: **45 segundos por item**
  *(Tempo médio que um analista leva para dar duplo clique, aguardar a tela de detalhe abrir, limpar quantidade, preencher local de descarga, salvar, esperar validação do SAP e confirmar eventuais popups).*
- **Tempo Médio de Triagem/Diagnóstico Manual**: **25 segundos por item**
  *(Trabalho poupado ao analista mesmo quando o item é travado ou apresenta erro, pois o robô cataloga o PEP com falha e diagnóstico no relatório).*
- **Tempo Médio do Robô Mirandinha**: **~3,5 a 4,5 segundos por item**.
- **Preservação de Ganho em Falha/Cancelamento**: Se o processo for interrompido pelo operador ou por queda de sessão do SAP, **o tempo economizado pelas linhas já triadas NÃO é zerado**, garantindo o reconhecimento do ROI parcial no dashboard.

### 3.2 Fórmulas de Cálculo para o Dashboard
$$\text{Tempo Economizado} = \max\left(0.0,\, (\text{Itens Triados} \times 45\text{ s}) - \text{Duração Robô}\right)$$
*(Caso a duração líquida atinja zero por parada antecipada, adota-se piso de 25s por item triado para contabilizar o trabalho de auditoria já concluído).*

---

## 4. Metadados Gravados para Auditoria e Histórico

Ao término da execução, cancelamento ou falha, os seguintes atributos são gravados no SQLite (`mirandinha_history.db`):

```json
{
  "job_id": "job_mat_zerar_compromisso",
  "transacao": "CN52N",
  "modulo": "Materiais",
  "tipo": "SAP / Gestão de Materiais",
  "data_inicio": "04/09/2026 09:57:14",
  "data_fim": "04/09/2026 14:00:35",
  "motivo_finalizacao": "Concluído com Sucesso / Cancelado pelo Operador / Interrompido por Falha",
  "itens_concluidos": 1180,
  "erros_contagem": 23,
  "total_itens_triados": 1203,
  "total_grade": 1462,
  "tempo_manual_estimado_segundos": 54135.0,
  "tempo_robo_segundos": 14600.89,
  "horas_poupadas": 8.35,
  "peps_com_falha": [
    {
      "linha": 10,
      "pep": "MA-2601312UNI1.4.0109.I",
      "material": "Material",
      "motivo": "Item bloqueado ou somente leitura: Property '<unknown>.text' can not be set."
    }
  ]
}
```

---

## 5. Procedimentos de Contingência, Anti-Ociosidade e Boas Práticas

1. **Keep-Alive Anti-Ociosidade (Timeout do SAP)**:
   - Para evitar que o SAP feche a sessão por inatividade durante rotinas muito extensas ou esperas, o robô executa um keep-alive a cada 90 segundos lendo propriedades leves da janela ativa (`wnd[0].text`).
2. **Janela Exclusiva**:
   - O SAP GUI Scripting manipula a janela ativa. O operador não deve interagir com mouse/teclado no SAP enquanto a barra de progresso do Mirandinha estiver ativa.
3. **Tratamento de Itens Bloqueados (Rotina de Escape)**:
   - Se uma reserva estiver bloqueada por outro usuário, a rotina de escape descarta alterações locais (`btn[12]`, `btn[3]`, confirmação `btnSPOP-OPTION2`) e retorna ao ALV, registrando o PEP na lista de exceções e continuando o processamento do restante do lote.
4. **Detecção Imediata de Queda de Conexão**:
   - Se o servidor SAP cair ou o SAP Logon for fechado, o erro com códigos de desconexão (ex: `-2147417848`, `RPC server is unavailable`) é detectado no primeiro item afetado, paralisando a rotina com segurança e preservando todas as métricas dos itens já salvos.
5. **Exportação dos PEPs com Problema**:
   - Tanto no card de conclusão do RPA quanto na modal de detalhes do Histórico de Tarefas, há um botão de **Exportar para Excel (.xlsx)** que gera uma planilha pronta com a lista de PEPs e seus respectivos diagnósticos para saneamento pelo analista.
