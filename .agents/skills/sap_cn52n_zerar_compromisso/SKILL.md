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
- **Tempo Médio do Robô Mirandinha**: **~3,5 a 4,5 segundos por item**.
- **Ganho Líquido**: **~41 segundos economizados por item processado**.

### 3.2 Fórmulas de Cálculo para o Dashboard
$$\text{Tempo Economizado (horas)} = \frac{\text{Itens Concluídos com Sucesso} \times 45\text{ s}}{3600}$$

Exemplo prático:
- **100 itens processados** = 4.500 segundos economizados = **1,25 horas de trabalho analítico poupadas**.
- **1.000 itens processados** = 45.000 segundos = **12,5 horas de trabalho contínuo**.

---

## 4. Metadados Gravados para o Dashboard

Ao término da execução (ou cancelamento), os seguintes atributos devem ser registrados na auditoria local (`core/storage.py`):

```json
{
  "job_id": "job_mat_zerar_compromisso",
  "transacao_sap": "CN52N",
  "modulo": "Gestão de Materiais / Projetos",
  "total_grid": 180,
  "itens_sucesso": 178,
  "itens_excecao": 2,
  "tempo_execucao_robo_segundos": 623.4,
  "tempo_manual_estimado_segundos": 8010.0,
  "tempo_economizado_segundos": 7386.6,
  "tempo_economizado_horas": 2.05,
  "status": "SUCCESS"
}
```

---

## 5. Procedimentos de Contingência e Boas Práticas

1. **Janela Exclusiva**: O SAP GUI Scripting manipula a janela ativa. O operador não deve interagir com o mouse ou teclado dentro da janela do SAP durante o ciclo de automação.
2. **Tratamento de Itens Travados**: Se uma reserva estiver bloqueada por outro usuário, a rotina de escape descarta as alterações locais e retorna ao grid ALV, garantindo que os próximos 50 ou 100 itens continuem sendo processados normalmente.
