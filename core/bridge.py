"""
Bridge de comunicação entre Python e frontend pywebview.
Aplica padronização estrita de resposta (caminho feliz e erro), telemetria de progresso e cancelamento.
"""
import webview
import traceback
import json
from typing import Any, Dict
from core.rpa.runner import RPARunner
from core.analytics.engine import AnalyticsEngine
from core.storage import fetch_recent_history

def success_response(data: Any = None) -> Dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "error": None
    }

def error_response(code: str, message: str, details: str = "") -> Dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "details": details
        }
    }

class MirandinhaBridge:
    def __init__(self):
        self._window = None
        self.rpa_runner = RPARunner(
            log_callback=self._emit_log,
            progress_callback=self._emit_progress,
            trace_callback=self._emit_trace
        )
        self.analytics_engine = AnalyticsEngine()

    def set_window(self, window):
        self._window = window

    def _emit_log(self, level: str, message: str):
        """Emite logs para o console do frontend via evaluate_js."""
        if self._window:
            safe_msg = message.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'").replace('\n', ' ')
            js_code = f"window.appBridge.appendLog('{level}', '{safe_msg}');"
            try:
                self._window.evaluate_js(js_code)
            except Exception:
                pass

    def _emit_progress(self, current: int, total: int):
        """Emite percentual e contagem atual de itens processados para a barra de progresso."""
        if self._window:
            js_code = f"window.appBridge.updateProgress({current}, {total});"
            try:
                self._window.evaluate_js(js_code)
            except Exception:
                pass

    def _emit_trace(self, event: Dict[str, Any]):
        """Emite um evento de trace (nó ou item) do GraphTask para o canvas do Studio pintar
        ao vivo. json.dumps() é seguro aqui: o payload é sempre str/int/float/None."""
        if self._window:
            try:
                payload = json.dumps(event, ensure_ascii=False)
                js_code = f"window.studioBridge && window.studioBridge.onTraceEvent({payload});"
                self._window.evaluate_js(js_code)
            except Exception:
                pass

    def get_available_jobs(self) -> Dict[str, Any]:
        try:
            jobs = self.rpa_runner.get_catalog()
            return success_response(jobs)
        except Exception as e:
            return error_response("CATALOG_ERROR", "Não foi possível carregar o catálogo de robôs.", str(e))

    def run_rpa_job(self, job_id: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            result = self.rpa_runner.execute_job_sync(job_id, params=params)
            return success_response(result)
        except Exception as e:
            return error_response("RPA_EXECUTION_ERROR", f"Erro durante a execução do robô: {str(e)}", traceback.format_exc())

    def is_rpa_running(self) -> Dict[str, Any]:
        """Verifica se há robô em execução ativa no momento."""
        is_running = getattr(self.rpa_runner, "_is_running", False)
        return success_response({"is_running": is_running})

    def force_close_app(self) -> Dict[str, Any]:
        """Fecha a janela da aplicação de forma limpa pelo frontend."""
        try:
            if self._window:
                self._window.destroy()
            return success_response({"closed": True})
        except Exception as e:
            return error_response("CLOSE_ERROR", str(e))

    def cancel_rpa_job(self) -> Dict[str, Any]:
        """Solicita a interrupção graciosa do robô em execução."""
        try:
            self.rpa_runner.request_cancel()
            return success_response({"status": "CANCEL_REQUESTED"})
        except Exception as e:
            return error_response("CANCEL_ERROR", f"Falha ao cancelar robô: {str(e)}")

    def get_system_kpis(self, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """Retorna indicadores reais acumulados de ROI e produtividade com filtro opcional por período."""
        try:
            from core.storage import get_accumulated_kpis
            kpis = get_accumulated_kpis(start_date=start_date, end_date=end_date)
            return success_response(kpis)
        except Exception as e:
            return error_response("KPIS_ERROR", "Falha ao calcular indicadores do sistema.", str(e))

    def get_dashboard_chart_data(self, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """Retorna dados agregados reais do banco para os gráficos da tela inicial com filtro opcional por período."""
        try:
            from core.storage import get_dashboard_chart_data
            chart_data = get_dashboard_chart_data(start_date=start_date, end_date=end_date)
            return success_response(chart_data)
        except Exception as e:
            return error_response("CHART_DATA_ERROR", "Falha ao carregar dados dos gráficos.", str(e))

    def get_job_history(self, limit: int = 50) -> Dict[str, Any]:
        try:
            history = fetch_recent_history(limit)

            return success_response(history)
        except Exception as e:
            return error_response("HISTORY_FETCH_ERROR", "Falha ao consultar histórico de tarefas.", str(e))

    def get_sample_analytics(self) -> Dict[str, Any]:
        try:
            data = self.analytics_engine.generate_demo_insights()
            return success_response(data)
        except Exception as e:
            return error_response("ANALYTICS_ERROR", "Erro ao gerar base demonstrativa.", str(e))

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        try:
            data = self.analytics_engine.analyze_file(file_path)
            return success_response(data)
        except Exception as e:
            return error_response("FILE_ANALYSIS_ERROR", f"Falha ao ler o arquivo: {str(e)}", traceback.format_exc())

    def select_file(self) -> Dict[str, Any]:
        try:
            if not self._window:
                return error_response("WINDOW_NOT_READY", "Janela da aplicação não inicializada.")
            file_types = ('Arquivos de Dados (*.csv;*.xlsx;*.xls)', 'Todos os arquivos (*.*)')
            result = self._window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=file_types)
            path = result[0] if (result and len(result) > 0) else None
            return success_response(path)
        except Exception as e:
            return error_response("DIALOG_ERROR", "Falha ao abrir seletor de arquivos.", str(e))

    def select_folder(self) -> Dict[str, Any]:
        try:
            if not self._window:
                return error_response("WINDOW_NOT_READY", "Janela da aplicação não inicializada.")
            result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
            path = result[0] if (result and len(result) > 0) else None
            return success_response(path)
        except Exception as e:
            return error_response("DIALOG_ERROR", "Falha ao abrir seletor de diretório.", str(e))

    def export_peps_to_excel(self, peps_list: list, job_name: str = "PEPs_Falha") -> Dict[str, Any]:
        """Exporta lista de PEPs com falha para planilha Excel (.xlsx) com seleção de destino."""
        try:
            if not peps_list or len(peps_list) == 0:
                return error_response("EMPTY_DATA", "Nenhum PEP com falha encontrado para exportar.")

            import os
            import pandas as pd
            from datetime import datetime

            default_name = f"PEPs_Falha_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            save_path = None

            if self._window:
                file_types = ('Planilha Excel (*.xlsx)',)
                result = self._window.create_file_dialog(
                    webview.SAVE_DIALOG, 
                    save_filename=default_name,
                    file_types=file_types
                )
                if result:
                    save_path = result if isinstance(result, str) else result[0]

            if not save_path:
                # Fallback para pasta padrão se o usuário cancelar o diálogo
                fallback_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                if not os.path.exists(fallback_dir):
                    fallback_dir = os.getcwd()
                save_path = os.path.join(fallback_dir, default_name)

            df = pd.DataFrame(peps_list)
            # Renomeia colunas para cabeçalhos amigáveis
            rename_map = {
                "linha": "Linha no SAP",
                "pep": "Elemento PEP",
                "material": "Material",
                "motivo": "Motivo do Erro / Diagnóstico"
            }
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

            df.to_excel(save_path, index=False, engine='openpyxl')

            return success_response({
                "file_path": save_path,
                "total_exported": len(peps_list)
            })
        except Exception as e:
            return error_response("EXPORT_ERROR", f"Falha ao exportar Excel: {str(e)}", traceback.format_exc())

    def download_template_excel(self, template_type: str = "data_necessidade") -> Dict[str, Any]:
        """Gera e salva planilha modelo com 3 exemplos práticos para o usuário."""
        try:
            import os
            import pandas as pd

            if template_type == "data_necessidade":
                filename = "Modelo_Data_Necessidade.xlsx"
                data = [
                    {"PEP": "01-0001-24.01.01", "Diagrama": "40001234", "Data Necessidade": "15/10/2026"},
                    {"PEP": "01-0002-24.02.03", "Diagrama": "40005678", "Data Necessidade": "20/11/2026"},
                    {"PEP": "02-0010-24.01.05", "Diagrama": "40009876", "Data Necessidade": "05/12/2026"}
                ]
            elif template_type == "concluir_requisicoes":
                filename = "Modelo_Concluir_Requisicoes.xlsx"
                data = [
                    {"Requisicao": "10012345", "Item": "10"},
                    {"Requisicao": "10012346", "Item": "10"},
                    {"Requisicao": "10012347", "Item": "20"}
                ]
            elif template_type == "eliminar_reserva":
                filename = "Modelo_Eliminar_Reserva.xlsx"
                data = [
                    {"Reserva": "0008541230", "Item": "1"},
                    {"Reserva": "0008541231", "Item": "1"},
                    {"Reserva": "0008541232", "Item": "2"}
                ]
            else:
                filename = f"Modelo_{template_type}.xlsx"
                data = []

            save_path = None
            if self._window:
                file_types = ('Planilha Excel (*.xlsx)',)
                result = self._window.create_file_dialog(
                    webview.SAVE_DIALOG,
                    save_filename=filename,
                    file_types=file_types
                )
                if result:
                    save_path = result if isinstance(result, str) else result[0]

            if not save_path:
                fallback_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                if not os.path.exists(fallback_dir):
                    fallback_dir = os.getcwd()
                save_path = os.path.join(fallback_dir, filename)

            df = pd.DataFrame(data)
            df.to_excel(save_path, index=False, engine='openpyxl')

            return success_response({
                "file_path": save_path,
                "filename": filename,
                "total_examples": len(data)
            })
        except Exception as e:
            return error_response("TEMPLATE_DOWNLOAD_ERROR", f"Falha ao salvar planilha modelo: {str(e)}", traceback.format_exc())

    def copy_to_clipboard(self, text: str) -> Dict[str, Any]:
        """Copia texto fornecido diretamente para a área de transferência do Windows."""
        try:
            import pandas.io.clipboard as cb
            cb.copy(text)
            return success_response({"copied": True, "chars": len(text)})
        except Exception as e:
            return error_response("CLIPBOARD_ERROR", f"Falha ao copiar para área de transferência: {str(e)}")

    # ================================================================
    # Módulo Studio (Etapa 3) — catálogo, biblioteca de telas, fluxos e execução
    # ================================================================

    def studio_node_catalog(self) -> Dict[str, Any]:
        """O Python é a autoridade única sobre os tipos de bloco — o canvas nunca declara
        tipo por conta própria, só consulta isto."""
        try:
            from core.studio.node_catalog import get_node_catalog
            return success_response(get_node_catalog())
        except Exception as e:
            return error_response("STUDIO_CATALOG_ERROR", "Falha ao carregar o catálogo de blocos.", str(e))

    def studio_screen_packs(self) -> Dict[str, Any]:
        """Resumo dos packs da Biblioteca de Telas — para o canvas listar."""
        try:
            from core.studio.screen_library import list_packs
            return success_response(list_packs())
        except Exception as e:
            return error_response("STUDIO_PACKS_ERROR", "Falha ao carregar a Biblioteca de Telas.", str(e))

    def studio_list_flows(self) -> Dict[str, Any]:
        try:
            from core.storage import list_studio_flows
            return success_response(list_studio_flows())
        except Exception as e:
            return error_response("STUDIO_LIST_ERROR", "Falha ao listar os fluxos salvos.", str(e))

    def studio_get_flow(self, flow_id: str) -> Dict[str, Any]:
        try:
            from core.storage import get_studio_flow
            flow = get_studio_flow(flow_id)
            if flow is None:
                return error_response("FLOW_NOT_FOUND", f"Fluxo '{flow_id}' não encontrado.")
            return success_response(flow)
        except Exception as e:
            return error_response("STUDIO_GET_ERROR", "Falha ao carregar o fluxo.", str(e))

    def studio_validate_flow(self, graph: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from core.studio.validator import validate_graph
            return success_response(validate_graph(graph))
        except Exception as e:
            return error_response("STUDIO_VALIDATE_ERROR", "Falha ao validar o fluxo.", str(e))

    def studio_save_flow(self, graph: Dict[str, Any], note: str = None) -> Dict[str, Any]:
        """Salva um rascunho — não exige grafo válido (a validação obrigatória é do
        portão de publicação, logo abaixo). Recusa enquanto um robô estiver em execução,
        pela mesma razão que a Central de Robôs já recusa disparar dois de uma vez."""
        try:
            if getattr(self.rpa_runner, "_is_running", False):
                return error_response("RPA_BUSY", "Não é possível salvar um fluxo enquanto uma automação está em execução.")

            flow_id = (graph or {}).get("flow_id")
            if not flow_id:
                return error_response("FLOW_INVALID", "O grafo precisa de um 'flow_id'.")

            from core.storage import save_studio_flow
            result = save_studio_flow(
                flow_id=flow_id,
                name=graph.get("name", flow_id),
                graph=graph,
                group_name=graph.get("group"),
                transacao=graph.get("transacao"),
                schema_version=graph.get("schema_version", 1),
                note=note,
            )
            return success_response(result)
        except Exception as e:
            return error_response("STUDIO_SAVE_ERROR", "Falha ao salvar o fluxo.", str(e))

    def studio_publish_flow(self, flow_id: str, publish: bool = True) -> Dict[str, Any]:
        """
        O portão da Etapa 5: um fluxo publicado vira código executável contra o SAP
        produtivo pelo botão [Iniciar] da Central de Robôs, então publicar exige grafo
        válido (sem erro) e sem nenhum nó pendente de revisão. Despublicar (publish=False)
        não passa por essa checagem — tirar de circulação é sempre seguro.
        """
        try:
            if getattr(self.rpa_runner, "_is_running", False):
                return error_response("RPA_BUSY", "Não é possível publicar um fluxo enquanto uma automação está em execução.")

            from core.storage import get_studio_flow, set_studio_flow_published
            flow = get_studio_flow(flow_id)
            if flow is None:
                return error_response("FLOW_NOT_FOUND", f"Fluxo '{flow_id}' não encontrado.")

            if publish:
                from core.studio.validator import validate_graph
                result = validate_graph(flow["graph"])
                errors = [i for i in result["issues"] if i["severity"] == "error"]
                pending = [n["id"] for n in flow["graph"].get("nodes", []) if n.get("needs_review")]

                if errors or pending:
                    details = {
                        "issues": result["issues"],
                        "needs_review_node_ids": pending,
                    }
                    return error_response(
                        "FLOW_INVALID",
                        "O fluxo tem problemas que impedem a publicação — corrija e tente de novo.",
                        json.dumps(details, ensure_ascii=False),
                    )

            updated = set_studio_flow_published(flow_id, publish)
            return success_response(updated)
        except Exception as e:
            return error_response("STUDIO_PUBLISH_ERROR", "Falha ao publicar o fluxo.", str(e))

    def studio_list_samples(self) -> Dict[str, Any]:
        """Grafos de exemplo empacotados com o app (core/studio/samples/) — ponto de
        partida pra quem está conhecendo o Studio, sem precisar montar do zero nem editar
        JSON à mão."""
        try:
            import os
            samples_dir = os.path.join(os.path.dirname(__file__), "studio", "samples")
            samples = []
            for filename in sorted(os.listdir(samples_dir)):
                if not filename.endswith(".json"):
                    continue
                path = os.path.join(samples_dir, filename)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    samples.append({
                        "file": filename,
                        "name": data.get("name", filename),
                        "transacao": data.get("transacao", ""),
                        "description": data.get("description", ""),
                    })
                except Exception:
                    continue
            return success_response(samples)
        except Exception as e:
            return error_response("STUDIO_SAMPLES_ERROR", "Falha ao listar os exemplos.", str(e))

    def studio_load_sample(self, filename: str) -> Dict[str, Any]:
        try:
            import os
            samples_dir = os.path.join(os.path.dirname(__file__), "studio", "samples")
            safe_name = os.path.basename(filename)  # sem travessia de diretório
            path = os.path.join(samples_dir, safe_name)
            if not os.path.exists(path):
                return error_response("SAMPLE_NOT_FOUND", f"Exemplo '{safe_name}' não encontrado.")
            with open(path, "r", encoding="utf-8") as f:
                return success_response(json.load(f))
        except Exception as e:
            return error_response("STUDIO_SAMPLE_LOAD_ERROR", "Falha ao carregar o exemplo.", str(e))

    def studio_run_flow(self, graph: Dict[str, Any], params: Dict[str, Any] = None) -> Dict[str, Any]:
        try:
            result = self.rpa_runner.execute_graph_sync(graph, params=params or {})
            return success_response(result)
        except Exception as e:
            return error_response("STUDIO_EXECUTION_ERROR", f"Erro durante a execução do fluxo: {str(e)}", traceback.format_exc())


