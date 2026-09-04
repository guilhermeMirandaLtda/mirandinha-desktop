"""
Bridge de comunicação entre Python e frontend pywebview.
Aplica padronização estrita de resposta (caminho feliz e erro), telemetria de progresso e cancelamento.
"""
import json
import webview
import traceback
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
            progress_callback=self._emit_progress
        )
        self.analytics_engine = AnalyticsEngine()

    def set_window(self, window):
        self._window = window

    def _emit_log(self, level: str, message: str):
        """Emite logs para o console do frontend via evaluate_js (payload serializado com json.dumps)."""
        if self._window:
            js_code = f"window.appBridge.appendLog({json.dumps(str(level))}, {json.dumps(str(message))});"
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

    def get_available_jobs(self) -> Dict[str, Any]:
        try:
            jobs = self.rpa_runner.get_catalog()
            return success_response(jobs)
        except Exception as e:
            return error_response("CATALOG_ERROR", "Não foi possível carregar o catálogo de robôs.", str(e))

    def run_rpa_job(self, job_id: str) -> Dict[str, Any]:
        if getattr(self.rpa_runner, "_is_running", False):
            return error_response(
                "RPA_BUSY",
                "Já existe uma automação em execução. Aguarde a conclusão ou cancele-a antes de iniciar outra."
            )
        try:
            result = self.rpa_runner.execute_job_sync(job_id)
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

    def get_system_kpis(self) -> Dict[str, Any]:
        """Retorna indicadores reais acumulados de ROI e produtividade."""
        try:

            from core.storage import get_accumulated_kpis
            kpis = get_accumulated_kpis()
            return success_response(kpis)
        except Exception as e:
            return error_response("KPIS_ERROR", "Falha ao calcular indicadores do sistema.", str(e))

    def get_dashboard_series(self) -> Dict[str, Any]:
        """Retorna as séries reais (últimos 7 dias) para os gráficos do dashboard."""
        try:
            from core.storage import get_dashboard_series
            return success_response(get_dashboard_series())
        except Exception as e:
            return error_response("DASHBOARD_SERIES_ERROR", "Falha ao montar séries do dashboard.", str(e))

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
