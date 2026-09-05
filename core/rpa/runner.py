"""
Executor e gerenciador oficial de robôs RPA do Mirandinha.
Fonte única da verdade com suporte a cancelamento de rotinas e telemetria de progresso percentual.
"""
import time
import random
from datetime import datetime
from typing import Dict, Any, Callable, List
from core.storage import record_job_execution

AVAILABLE_JOBS = [
    {
        "id": "job_mat_data_necessidade",
        "group": "Materiais",
        "order": "1.1",
        "name": "Data Necessidade",
        "type": "SAP / Gestão de Materiais",
        "requires_file": True,
        "description": "Atualização automática e reprogramação em lote das datas de necessidade dos componentes de diagramas de rede na transação CJ20N a partir de planilha Excel.",
        "usage_steps": [
            "Selecione a planilha Excel (.xlsx) contendo as colunas: 'PEP', 'Diagrama' e 'Data Necessidade'.",
            "Certifique-se de estar com o SAP Logon aberto e conectado na sessão desejada.",
            "Clique em [Iniciar] para o Mirandinha abrir a transação CJ20N e processar os diagramas em lote.",
            "Ao concluir, os diagramas atualizados e eventuais exceções serão registrados no relatório e histórico."
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
            "Logar no SAP Financeiro.",
            "Acessar a transação \"CN52N\".",
            "Escolher o layout de sua preferência, sugestão \"/MIRANDA-ZER\".",
            "Clique no botão [Iniciar] abaixo.",
            "Atenção: O Mirandinha irá processar cada item, zerando a quantidade comprometida de cada linha."
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
        "requires_file": True,
        "template_type": "concluir_requisicoes",
        "file_hint": "Planilha Excel (.xlsx) com colunas: 'Requisicao' e 'Item'",
        "description": "Encerramento massivo e marcação do status de requisição concluída (EBAN-EBAKZ) na transação ME52N para saneamento da base de suprimentos.",
        "usage_steps": [
            "Selecione a planilha Excel (.xlsx) contendo as colunas: 'Requisicao' e 'Item' (ou baixe a planilha modelo).",
            "Certifique-se de estar com o SAP Logon aberto e conectado na sessão desejada.",
            "Clique em [Iniciar] para o Mirandinha abrir a transação ME52N e processar as requisições em lote.",
            "Ao concluir, os itens encerrados e eventuais bloqueios serão gravados no relatório e histórico."
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
        "requires_file": True,
        "template_type": "eliminar_reserva",
        "file_hint": "Planilha Excel (.xlsx) com colunas: 'Reserva' e 'Item'",
        "description": "Exclusão e baixa definitiva de reservas de materiais órfãs na transação MB22 (flag RESB-XLOEK), liberando saldo imediatamente para o estoque.",
        "usage_steps": [
            "Selecione a planilha Excel (.xlsx) contendo as colunas: 'Reserva' e 'Item' (ou baixe a planilha modelo).",
            "Certifique-se de estar com o SAP Logon aberto e conectado na sessão desejada.",
            "Clique em [Iniciar] para o Mirandinha abrir a transação MB22 e marcar a eliminação de cada posição.",
            "Ao concluir, o espelho das baixas e auditoria completa será gerado automaticamente."
        ],
        "last_run": "Nunca",
        "status": "idle"
    }
]

class RPARunner:
    def __init__(
        self,
        log_callback: Callable[[str, str], None] = None,
        progress_callback: Callable[[int, int], None] = None,
        trace_callback: Callable[[Dict[str, Any]], None] = None,
    ):
        self.log_callback = log_callback or (lambda level, msg: print(f"[{level}] {msg}"))
        self.progress_callback = progress_callback or (lambda cur, tot: None)
        # Só usado por execute_graph_sync() (fluxos do Studio) — tasks nativas não emitem trace.
        self.trace_callback = trace_callback or (lambda evt: None)
        self._cancel_requested = False
        self._is_running = False

    def request_cancel(self):
        """Solicita a interrupção imediata da rotina em execução."""
        self._cancel_requested = True
        self.log("WARNING", "Solicitação de cancelamento enviada ao robô pelo operador.")

    def is_cancelled(self) -> bool:
        return self._cancel_requested

    def get_catalog(self) -> List[Dict[str, Any]]:
        from core.storage import get_last_runs_map
        last_runs = get_last_runs_map()
        catalog = []
        for job in AVAILABLE_JOBS:
            j = dict(job)
            lr_info = last_runs.get(j["id"])
            if lr_info:
                j["last_run"] = lr_info.get("last_run", "Nunca")
            else:
                j["last_run"] = "Nunca"
            catalog.append(j)
        return catalog

    def log(self, level: str, message: str):
        valid_levels = {"INFO", "SUCCESS", "WARNING", "ERROR", "DEBUG"}
        norm_level = level.upper() if level.upper() in valid_levels else "INFO"
        self.log_callback(norm_level, message)

    def execute_job_sync(self, job_id: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Executa a rotina do robô, mede o tempo e grava auditoria no banco."""
        params = params or {}
        self._cancel_requested = False
        self._is_running = True
        job_def = next((j for j in AVAILABLE_JOBS if j["id"] == job_id), None)
        job_name = job_def["name"] if job_def else job_id

        start_time = time.time()
        self.log("INFO", f"Iniciando rotina robótica: {job_name}")

        task_instance = None
        start_datetime = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        try:
            if job_id == "job_mat_zerar_compromisso":
                from core.rpa.tasks.sap_zerar_compromisso import SAPZerarCompromissoTask
                task_instance = SAPZerarCompromissoTask(
                    log_callback=self.log,
                    progress_callback=self.progress_callback,
                    cancel_check=self.is_cancelled
                )
                res = task_instance.run()
                processed = res.get("sucessos", 0)
                errors = res.get("erros", 0)
                peps_falha = res.get("peps_com_falha", [])
                is_cancelled = res.get("cancelled", False)
            elif job_id == "job_mat_data_necessidade":
                spreadsheet_path = params.get("spreadsheet_path") or params.get("file_path")
                if not spreadsheet_path:
                    raise ValueError("Nenhum arquivo de planilha foi selecionado para a automação Data Necessidade.")

                from core.rpa.tasks.sap_data_necessidade import SAPDataNecessidadeTask
                task_instance = SAPDataNecessidadeTask(
                    spreadsheet_path=spreadsheet_path,
                    log_callback=self.log,
                    progress_callback=self.progress_callback,
                    cancel_check=self.is_cancelled
                )
                res = task_instance.run()
                processed = res.get("sucessos", 0)
                errors = res.get("erros", 0)
                peps_falha = res.get("peps_com_falha", [])
                is_cancelled = res.get("cancelled", False)
            elif job_id == "job_mat_concluir_requisicoes":
                spreadsheet_path = params.get("spreadsheet_path") or params.get("file_path")
                if not spreadsheet_path:
                    raise ValueError("Nenhum arquivo de planilha foi selecionado para a automação Concluir Requisições.")

                from core.rpa.tasks.sap_concluir_requisicoes import SAPConcluirRequisicoesTask
                task_instance = SAPConcluirRequisicoesTask(
                    spreadsheet_path=spreadsheet_path,
                    log_callback=self.log,
                    progress_callback=self.progress_callback,
                    cancel_check=self.is_cancelled
                )
                res = task_instance.run()
                processed = res.get("sucessos", 0)
                errors = res.get("erros", 0)
                peps_falha = res.get("peps_com_falha", [])
                is_cancelled = res.get("cancelled", False)
            elif job_id == "job_mat_eliminar_reserva":
                spreadsheet_path = params.get("spreadsheet_path") or params.get("file_path")
                if not spreadsheet_path:
                    raise ValueError("Nenhum arquivo de planilha foi selecionado para a automação Eliminar Reserva.")

                from core.rpa.tasks.sap_eliminar_reserva import SAPEliminarReservaTask
                task_instance = SAPEliminarReservaTask(
                    spreadsheet_path=spreadsheet_path,
                    log_callback=self.log,
                    progress_callback=self.progress_callback,
                    cancel_check=self.is_cancelled
                )
                res = task_instance.run()
                processed = res.get("sucessos", 0)
                errors = res.get("erros", 0)
                peps_falha = res.get("peps_com_falha", [])
                is_cancelled = res.get("cancelled", False)
            else:
                # Simulação genérica para outros robôs futuros
                total_steps = 10
                processed = 0
                errors = 0
                peps_falha = []
                is_cancelled = False
                for step in range(1, total_steps + 1):
                    if self.is_cancelled():
                        is_cancelled = True
                        self.log("WARNING", f"Execução cancelada pelo usuário no passo {step}/{total_steps}.")
                        break
                    time.sleep(0.4)
                    processed += random.randint(10, 25)
                    self.progress_callback(step, total_steps)
                    self.log("INFO", f"Processando lote {step} de {total_steps}...")

            duration = time.time() - start_time
            end_datetime = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            final_status = "CANCELLED" if is_cancelled else "SUCCESS"
            
            if is_cancelled:
                self.log("WARNING", f"Automação [{job_name}] interrompida. ({processed} itens em {duration:.1f}s)")
                motivo_desc = "Cancelado pelo Operador"
            else:
                self.log("SUCCESS", f"Automação [{job_name}] finalizada com êxito! ({processed} itens em {duration:.1f}s)")
                motivo_desc = "Concluído com Sucesso"
            
            total_analisados = processed + errors
            
            # Calibração estrita e ponderada por robô:
            # - Data Necessidade (CJ20N): 120s manual / 60s triagem
            # - Zerar Compromisso (CN52N): 45s manual / 25s triagem
            # - Concluir Requisições (ME52N): 45s manual / 25s triagem
            # - Eliminar Reserva (MB22): 40s manual / 20s triagem
            if job_id == "job_mat_data_necessidade":
                t_sucesso, t_erro = 120.0, 60.0
            elif job_id == "job_mat_zerar_compromisso":
                t_sucesso, t_erro = 45.0, 25.0
            elif job_id == "job_mat_concluir_requisicoes":
                t_sucesso, t_erro = 45.0, 25.0
            elif job_id == "job_mat_eliminar_reserva":
                t_sucesso, t_erro = 40.0, 20.0
            else:
                t_sucesso, t_erro = 45.0, 20.0

            tempo_manual_estimado = (processed * t_sucesso) + (errors * t_erro)
            horas_poupadas = max(0.0, tempo_manual_estimado - duration)
            if horas_poupadas == 0.0 and total_analisados > 0:
                horas_poupadas = (processed * (t_sucesso * 0.5)) + (errors * t_erro)

            job_version = getattr(task_instance, "JOB_VERSION", "1.0.0") if task_instance else "1.0.0"
            transacoes_map = {
                "job_mat_zerar_compromisso": "CN52N",
                "job_mat_data_necessidade": "CJ20N",
                "job_mat_concluir_requisicoes": "ME52N",
                "job_mat_eliminar_reserva": "MB22"
            }
            transacao_nome = transacoes_map.get(job_id, "AUTO")
            meta_payload = {
                "job_version": job_version,
                "engine_version": "3.0.4",
                "transacao": transacao_nome,
                "modulo": job_def.get("group", "Geral") if job_def else "Geral",
                "tipo": job_def.get("type", "RPA") if job_def else "RPA",
                "data_inicio": start_datetime,
                "data_fim": end_datetime,
                "motivo_finalizacao": motivo_desc,
                "tempo_manual_estimado_segundos": round(tempo_manual_estimado, 1),
                "tempo_robo_segundos": round(duration, 2),
                "horas_poupadas": round(horas_poupadas / 3600.0, 2),
                "itens_concluidos": processed,
                "erros_contagem": errors if 'errors' in locals() else 0,
                "total_itens_triados": total_analisados,
                "peps_com_falha": peps_falha
            }

            record_job_execution(job_id, job_name, duration, total_analisados, final_status, metadata=meta_payload)
            return {
                "job_id": job_id,
                "job_name": job_name,
                "job_version": job_version,
                "processed": processed,
                "errors": errors if 'errors' in locals() else 0,
                "duration_seconds": round(duration, 2),
                "status": final_status,
                "metadata": meta_payload,
                "peps_com_falha": peps_falha
            }
        except Exception as exc:
            duration = time.time() - start_time
            end_datetime = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            err_msg = str(exc)
            self.log("ERROR", f"Falha na execução de [{job_name}]: {err_msg}")
            
            # Recupera métricas parciais salvas na instância da task (se houver)
            parcial_sucessos = 0
            parcial_erros = 0
            parcial_falhas = []
            job_version = "1.0.0"
            if task_instance is not None:
                parcial_sucessos = getattr(task_instance, "sucessos", 0)
                parcial_erros = getattr(task_instance, "erros", 0)
                parcial_falhas = getattr(task_instance, "peps_com_falha", [])
                job_version = getattr(task_instance, "JOB_VERSION", "1.0.0")

            total_parcial = parcial_sucessos + parcial_erros
            if job_id == "job_mat_data_necessidade":
                t_sucesso, t_erro = 120.0, 60.0
            elif job_id == "job_mat_zerar_compromisso":
                t_sucesso, t_erro = 45.0, 25.0
            elif job_id == "job_mat_concluir_requisicoes":
                t_sucesso, t_erro = 45.0, 25.0
            elif job_id == "job_mat_eliminar_reserva":
                t_sucesso, t_erro = 40.0, 20.0
            else:
                t_sucesso, t_erro = 45.0, 20.0

            tempo_manual_estimado = (parcial_sucessos * t_sucesso) + (parcial_erros * t_erro)
            horas_poupadas = max(0.0, tempo_manual_estimado - duration)
            if horas_poupadas == 0.0 and total_parcial > 0:
                horas_poupadas = (parcial_sucessos * (t_sucesso * 0.5)) + (parcial_erros * t_erro)

            motivo_final = f"Interrompido por Erro / Falha: {err_msg}"
            if self.is_cancelled():
                motivo_final = f"Cancelado pelo Operador / Interrompido: {err_msg}"

            transacoes_map = {
                "job_mat_zerar_compromisso": "CN52N",
                "job_mat_data_necessidade": "CJ20N",
                "job_mat_concluir_requisicoes": "ME52N",
                "job_mat_eliminar_reserva": "MB22"
            }
            transacao_nome = transacoes_map.get(job_id, "AUTO")
            fail_meta = {
                "job_version": job_version,
                "engine_version": "3.0.4",
                "transacao": transacao_nome,
                "modulo": job_def.get("group", "Geral") if job_def else "Geral",
                "tipo": job_def.get("type", "RPA") if job_def else "RPA",
                "data_inicio": start_datetime,
                "data_fim": end_datetime,
                "motivo_finalizacao": motivo_final,
                "tempo_manual_estimado_segundos": round(tempo_manual_estimado, 1),
                "tempo_robo_segundos": round(duration, 2),
                "horas_poupadas": round(horas_poupadas / 3600.0, 2),
                "itens_concluidos": parcial_sucessos,
                "erros_contagem": parcial_erros,
                "total_itens_triados": total_parcial,
                "peps_com_falha": parcial_falhas,
                "falha_etapa": "execucao"
            }
            # Grava no histórico com o total de itens já triados e as horas poupadas
            record_job_execution(job_id, job_name, duration, total_parcial, "FAILED", err_msg, metadata=fail_meta)
            raise exc
        finally:
            self._is_running = False

    def execute_graph_sync(self, graph: Dict[str, Any], params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Executa um fluxo do Studio (Etapa 3 — direto do canvas, sem passar pelo catálogo
        de robôs; isso é trabalho da Etapa 5). Espelha execute_job_sync() de propósito —
        mesma guarda de concorrência, mesmo shape de retorno, mesma gravação em
        job_history — só troca 'qual task instanciar' e onde vêm os metadados de
        governança (do grafo, não de AVAILABLE_JOBS).
        """
        from core.rpa.tasks.graph_task import GraphTask

        params = params or {}
        if self._is_running:
            raise RuntimeError("Já existe uma automação em execução — aguarde terminar antes de rodar outro fluxo.")

        self._cancel_requested = False
        self._is_running = True

        job_id = graph.get("flow_id", "flow_sem_id")
        job_name = graph.get("name", "Fluxo do Studio")
        transacao = graph.get("transacao", "AUTO")
        modulo = graph.get("group", "Studio")

        start_time = time.time()
        start_datetime = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.log("INFO", f"Iniciando fluxo do Studio: {job_name}")

        task_instance = None
        try:
            task_instance = GraphTask(
                graph=graph,
                params=params,
                log_callback=self.log,
                progress_callback=self.progress_callback,
                cancel_check=self.is_cancelled,
                trace_callback=self.trace_callback,
            )
            res = task_instance.run()

            processed = res.get("processed", 0)
            errors = res.get("errors", 0)
            peps_falha = res.get("peps_com_falha", [])
            is_cancelled = res.get("status") == "CANCELLED"

            duration = time.time() - start_time
            end_datetime = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            final_status = res.get("status", "SUCCESS")

            if is_cancelled:
                self.log("WARNING", f"Fluxo [{job_name}] interrompido. ({processed} itens em {duration:.1f}s)")
                motivo_desc = "Cancelado pelo Operador"
            else:
                self.log("SUCCESS", f"Fluxo [{job_name}] finalizado com êxito! ({processed} itens em {duration:.1f}s)")
                motivo_desc = "Concluído com Sucesso"

            total_analisados = processed + errors
            t_sucesso, t_erro = 45.0, 20.0  # sem calibração própria ainda — genérico, como robôs futuros
            tempo_manual_estimado = (processed * t_sucesso) + (errors * t_erro)
            horas_poupadas = max(0.0, tempo_manual_estimado - duration)
            if horas_poupadas == 0.0 and total_analisados > 0:
                horas_poupadas = (processed * (t_sucesso * 0.5)) + (errors * t_erro)

            meta_payload = {
                "job_version": res.get("job_version", "1"),
                "engine_version": "3.0.4",
                "transacao": transacao,
                "modulo": modulo,
                "tipo": "Studio / Grafo",
                "data_inicio": start_datetime,
                "data_fim": end_datetime,
                "motivo_finalizacao": motivo_desc,
                "tempo_manual_estimado_segundos": round(tempo_manual_estimado, 1),
                "tempo_robo_segundos": round(duration, 2),
                "horas_poupadas": round(horas_poupadas / 3600.0, 2),
                "itens_concluidos": processed,
                "erros_contagem": errors,
                "total_itens_triados": total_analisados,
                "peps_com_falha": peps_falha,
                "origem": "studio",
            }

            record_job_execution(job_id, job_name, duration, total_analisados, final_status, metadata=meta_payload)
            return {
                "job_id": job_id,
                "job_name": job_name,
                "job_version": res.get("job_version", "1"),
                "processed": processed,
                "errors": errors,
                "duration_seconds": round(duration, 2),
                "status": final_status,
                "metadata": meta_payload,
                "peps_com_falha": peps_falha,
            }
        except Exception as exc:
            duration = time.time() - start_time
            end_datetime = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            err_msg = str(exc)
            self.log("ERROR", f"Falha na execução do fluxo [{job_name}]: {err_msg}")

            parcial_sucessos = getattr(task_instance, "sucessos", 0) if task_instance else 0
            parcial_erros = getattr(task_instance, "erros", 0) if task_instance else 0
            parcial_falhas = getattr(task_instance, "peps_com_falha", []) if task_instance else []
            total_parcial = parcial_sucessos + parcial_erros

            t_sucesso, t_erro = 45.0, 20.0
            tempo_manual_estimado = (parcial_sucessos * t_sucesso) + (parcial_erros * t_erro)
            horas_poupadas = max(0.0, tempo_manual_estimado - duration)
            if horas_poupadas == 0.0 and total_parcial > 0:
                horas_poupadas = (parcial_sucessos * (t_sucesso * 0.5)) + (parcial_erros * t_erro)

            motivo_final = f"Interrompido por Erro / Falha: {err_msg}"
            if self.is_cancelled():
                motivo_final = f"Cancelado pelo Operador / Interrompido: {err_msg}"

            fail_meta = {
                "job_version": getattr(task_instance, "JOB_VERSION", "1") if task_instance else "1",
                "engine_version": "3.0.4",
                "transacao": transacao,
                "modulo": modulo,
                "tipo": "Studio / Grafo",
                "data_inicio": start_datetime,
                "data_fim": end_datetime,
                "motivo_finalizacao": motivo_final,
                "tempo_manual_estimado_segundos": round(tempo_manual_estimado, 1),
                "tempo_robo_segundos": round(duration, 2),
                "horas_poupadas": round(horas_poupadas / 3600.0, 2),
                "itens_concluidos": parcial_sucessos,
                "erros_contagem": parcial_erros,
                "total_itens_triados": total_parcial,
                "peps_com_falha": parcial_falhas,
                "falha_etapa": "execucao",
                "origem": "studio",
            }
            record_job_execution(job_id, job_name, duration, total_parcial, "FAILED", err_msg, metadata=fail_meta)
            raise exc
        finally:
            self._is_running = False


