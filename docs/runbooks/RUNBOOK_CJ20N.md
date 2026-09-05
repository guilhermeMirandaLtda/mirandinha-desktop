# Runbook Operacional: Automação SAP CJ20N — Data Necessidade

**Código do Robô**: `job_mat_data_necessidade`  
**Versão Atual**: `1.1.0`  
**Transação ERP**: `CJ20N` (Project Builder)  
**Criticidade**: Média-Alta (Modificação de datas de reserva de materiais de projetos)  
**Responsável Técnico**: Guilherme Miranda (Contato: `(99) 9.8121-6058`)

---

## 1. Checklist Pré-Execução (Operador / Analista)

Antes de iniciar o robô na interface do Mirandinha, verifique:
1. **SAP Logon Aberto e Conectado**: O operador deve estar autenticado no mandante de produção do SAP;
2. **SAP GUI Scripting Habilitado**:
   - No SAP GUI: `Opções > Acessibilidade e Scripting > Scripting > Habilitar Scripting` (marcado);
   - Notificações de script desmarcadas para evitar travamento da automação por popups do Windows;
3. **Planilha de Insumos Válida**:
   - Formato `.xlsx` contendo obrigatoriamente as colunas `PEP`, `Diagrama` e `Data Necessidade`;
   - Datas no formato `DD/MM/AAAA` compreendidas entre **-60 dias** e **+24 meses**;
4. **Sem Janelas Bloqueadas**: Feche quaisquer transações abertas na sessão para que o comando `/ncj20n` inicie em tela limpa.

---

## 2. Matriz de Erros Operacionais & Ações Recomendadas

| Sintoma / Mensagem no Console | Causa Raiz | Ação Recomendada |
| :--- | :--- | :--- |
| `Não foi possível obter o objeto SAPGUI` | O aplicativo SAP Logon não está aberto no Windows. | Abrir o SAP Logon, realizar login e tentar novamente. |
| `Scripting Engine do SAP desabilitado` | O parâmetro de scripting foi desativado no cliente ou no servidor (`sapgui/user_scripting`). | Ativar nas Opções do SAP GUI ou contatar a equipe Basis de TI. |
| `Diagrama XXXXXX bloqueado pelo usuário UXXXX` | Outro analista está com a ordem ou projeto aberto no SAP com trava de edição (`SM12`). | O robô catalogará a linha em `peps_com_falha` e continuará o lote. Ao final, exportar o Excel e processar o diagrama liberado. |
| `Data Necessidade está no passado remoto / excede 24 meses` | Erro de digitação humana no Excel (ex: `15/10/2020` ou ano `2062`). | Corrigir a data na planilha e re-executar. |
| `Sessão do SAP foi desconectada (-2147417848)` | Queda de VPN/rede corporativa ou encerramento forçado do SAP pelo usuário. | O robô preservará os dados já processados no SQLite. Reconectar o SAP e reprocessar os itens pendentes. |

---

## 3. Procedimento Formal de Rollback (Reversão)

Caso uma planilha seja executada com datas incorretas:
1. **Identificar o Lote Afetado**: Acessar o menu **Histórico de Tarefas** no Mirandinha e clicar em **Detalhes** da execução para listar todos os diagramas gravados;
2. **Re-execução com Planilha Corretiva**:
   - Montar uma planilha Excel contendo os mesmos números de diagrama e a data correta desejada;
   - Executar novamente a automação pelo Mirandinha;
3. **Auditoria de Histórico**:
   - Caso seja necessário resgatar a data original anterior à modificação, acesse a transação SAP `AUT10` ou consulte as tabelas `CDHDR`/`CDPOS` filtrando pelo objeto de modificação e campo `RESBD-BDTER`.
