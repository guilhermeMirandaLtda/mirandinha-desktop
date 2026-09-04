"""
Executor e gerenciador oficial de robôs RPA do Mirandinha.
Fonte única da verdade com suporte a cancelamento de rotinas e telemetria de progresso percentual.
"""
import time
import random
from typing import Dict, Any, Callable, List
from core.storage import record_job_execution

AVAILABLE_JOBS = [
    {
        "id": "job_mat_data_necessidade",
        "group": "Materiais",
        "order": "1.1",
        "name": "Data Necessidade",
        "type": "SAP / Gestão de Materiais",
        "description": "Atualização automática e reprogramação em lote das datas de necessidade das reservas e ordens de serviço pendentes no ERP.",
        "usage_steps": [
            "Certifique-se de que a planilha de insumos ou a lista de ordens no SAP esteja com os números de reserva válidos.",
            "O robô fará a conexão com a interface transacional e localizará cada item de material pendente.",
            "As datas de necessidade serão reprogramadas de acordo com o cronograma atualizado de suprimentos.",
            "Ao concluir, um espelho das alterações e relatório de consistência será gerado automaticamente."
        ],
        "last_run": "Nunca",
        "status": "idle"
    },
    {
        "id": "job_mat_zerar_compromisso",
        "group": "Materiais",
        "order": "1.2",
        "name": "Zerar Compromisso",
        "type": "SAP / Gestão de Materiais",
        "description": "Automação nativa via SAP GUI Scripting para zerar a quantidade reservada (MENGE) e local de descarga (ABLAD) dos itens de materiais diretamente na transação CN52N.",
        "usage_steps": [
            "Abra o SAP Logon e conecte-se ao ambiente desejado.",
            "Acesse a transação CN52N com os critérios e filtros de sua escolha e execute (F8) para exibir o relatório ALV na tela.",
            "Certifique-se de que a grade ALV com as colunas POSID, MAKTX e FLMNG está visível na janela principal.",
            "Volte ao Mirandinha e clique em [Iniciar]. O robô fará o drill-down linha por linha, zerando os compromissos e tratando eventuais popups de orçamento automaticamente."
        ],
        "last_run": "Nunca",
        "status": "idle"
    },
    {
        "id": "job_mat_concluir_requisicoes",
        "group": "Materiais",
        "order": "1.3",
        "name": "Concluir Requisições",
        "type": "SAP / Suprimentos",
        "description": "Encerramento massivo e conclusão de requisições de compra atendidas ou obsoletas para saneamento da base de compras.",
        "usage_steps": [
            "Carregue ou aponte a lista de requisições de compras que devem receber o status 'Concluída'.",
            "O robô valida se não existem pedidos de compra ativos em aberto atrelados a cada requisição.",
            "Efetua a marcação do indicador de requisição concluída.",
            "Emite resumo com totais processados com sucesso e eventuais exceções de bloqueio."
        ],
        "last_run": "Nunca",
        "status": "idle"
    },
    {
        "id": "job_mat_eliminar_reserva",
        "group": "Materiais",
        "order": "1.4",
        "name": "Eliminar Reserva",
        "type": "SAP / Gestão de Materiais",
        "description": "Exclusão definitiva ou baixa de reservas de materiais órfãs, liberando itens para requisições prioritárias.",
        "usage_steps": [
            "Selecione o arquivo de entrada com o número das reservas e seus respectivos centros/depósitos.",
            "O robô abre a transação de modificação de reservas (ex: MB22/SAP).",
            "Marca o flag de eliminação/bloqueio em cada posição da reserva indicada.",
            "Grava o log de auditoria comprovando a devolução das quantidades ao estoque disponível."
        ],
        "last_run": "Nunca",
        "status": "idle"
    }
]

class RPARunner:
    def __init__(self, log_callback: Callable[[str, str], None] = None, progress_callback: Callable[[int, int], None] = None):
        self.log_callback = log_callback or (lambda level, msg: print(f"[{level}] {msg}"))
        self.progress_callback = progress_callback or (lambda cur, tot: None)
        self._cancel_requested = False
        self._is_running = False

    def request_cancel(self):
        """Solicita a interrupção imediata da rotina em execução."""
        self._cancel_requested = True
        self.log("WARNING", "Solicitação de cancelamento enviada ao robô pelo operador.")

    def is_cancelled(self) -> bool:
        return self._cancel_requested

    def get_catalog(self) -> List[Dict[str, Any]]:
        return AVAILABLE_JOBS

    def log(self, level: str, message: str):
        valid_levels = {"INFO", "SUCCESS", "WARNING", "ERROR", "DEBUG"}
        norm_level = level.upper() if level.upper() in valid_levels else "INFO"
        self.log_callback(norm_level, message)

    # IDs de robôs com automação real implementada. Os demais rodam em modo simulação
    # e seus registros NÃO entram nos indicadores consolidados.
    REAL_JOBS = {"job_mat_zerar_compromisso"}

    def execute_job_sync(self, job_id: str) -> Dict[str, Any]:
        """
        Executa a rotina do robô, mede o tempo e grava auditoria no banco.

        Concorrência: recusa iniciar se já houver um robô em execução — nunca deve
        haver duas automações disputando a mesma sessão do SAP GUI.
        """
        if self._is_running:
            raise RuntimeError("Já existe uma automação em execução. Aguarde a conclusão ou cancele-a.")

        self._cancel_requested = False
        self._is_running = True
        job_def = next((j for j in AVAILABLE_JOBS if j["id"] == job_id), None)
        job_name = job_def["name"] if job_def else job_id
        is_simulated = job_id not in self.REAL_JOBS

        start_time = time.time()
        self.log("INFO", f"Iniciando rotina robótica: {job_name}")


        try:
            if job_id == "job_mat_zerar_compromisso":
                from core.rpa.tasks.sap_zerar_compromisso import SAPZerarCompromissoTask
                task = SAPZerarCompromissoTask(
                    log_callback=self.log,
                    progress_callback=self.progress_callback,
                    cancel_check=self.is_cancelled
                )
                res = task.run()
                processed = res.get("sucessos", 0)
                errors = res.get("erros", 0)
                is_cancelled = res.get("cancelled", False)
            else:
                # Simulação com passos e cancelamento para os robôs ainda não implementados.
                # Registrado no histórico apenas para fins de rastreabilidade (is_simulated=True).
                self.log("WARNING", f"[{job_name}] roda em MODO SIMULAÇÃO — sem efeito real no SAP.")
                total_steps = 10
                processed = 0
                errors = 0
                is_cancelled = False
                for step in range(1, total_steps + 1):
                    if self.is_cancelled():
                        is_cancelled = True
                        self.log("WARNING", f"Execução cancelada pelo usuário no passo {step}/{total_steps}.")
                        break
                    time.sleep(0.4)
                    processed += random.randint(10, 25)
                    self.progress_callback(step, total_steps)
                    self.log("INFO", f"Processando lote {step} de {total_steps} (simulado)...")

            duration = time.time() - start_time
            final_status = "CANCELLED" if is_cancelled else "SUCCESS"
            
            if is_cancelled:
                self.log("WARNING", f"Automação [{job_name}] interrompida. ({processed} itens em {duration:.1f}s)")
            else:
                self.log("SUCCESS", f"Automação [{job_name}] finalizada! ({processed} itens em {duration:.1f}s)")
            
            meta_payload = {
                "transacao": "CN52N" if job_id == "job_mat_zerar_compromisso" else "AUTO",
                "modulo": job_def.get("group", "Geral") if job_def else "Geral",
                "tipo": job_def.get("type", "RPA") if job_def else "RPA",
                "simulado": is_simulated,
                "tempo_manual_estimado_segundos": round(processed * 45.0, 1),
                "tempo_robo_segundos": round(duration, 2),
                "horas_poupadas": round(max(0.0, (processed * 45.0) - duration) / 3600.0, 2),
                "erros_contagem": errors if 'errors' in locals() else 0
            }

            record_job_execution(
                job_id, job_name, duration, processed, final_status,
                metadata=meta_payload, is_simulated=is_simulated
            )
            return {
                "job_id": job_id,
                "job_name": job_name,
                "processed": processed,
                "errors": errors if 'errors' in locals() else 0,
                "duration_seconds": round(duration, 2),
                "status": final_status,
                "is_simulated": is_simulated,
                "metadata": meta_payload
            }
        except Exception as exc:
            duration = time.time() - start_time
            err_msg = str(exc)
            self.log("ERROR", f"Falha na execução de [{job_name}]: {err_msg}")
            fail_meta = {
                "transacao": "CN52N" if job_id == "job_mat_zerar_compromisso" else "AUTO",
                "simulado": is_simulated,
                "falha_etapa": "execucao"
            }
            record_job_execution(
                job_id, job_name, duration, 0, "FAILED", err_msg,
                metadata=fail_meta, is_simulated=is_simulated
            )
            raise exc
        finally:
            self._is_running = False


