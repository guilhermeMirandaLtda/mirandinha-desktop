"""
Framework Base para Robôs RPA do Mirandinha.
Define o ciclo de vida padronizado: validate_input() -> prepare() -> process_items() -> finalize().
Gerencia telemetria, contagem, cancelamento gracioso, cálculo defensivo de ROI e isolamento de exceções.
"""
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Callable, Dict, Any, List, Optional
from core.rpa.sap_session import SapSession


class RPAJobBase(ABC):
    """Classe base abstrata para todos os robôs RPA do sistema."""

    # Atributos de governança e versão a serem sobrescritos pelas subclasses
    JOB_ID: str = "job_base"
    JOB_NAME: str = "Robô Base"
    JOB_VERSION: str = "1.0.0"
    TRANSACTION: str = "AUTO"
    MODULE: str = "Geral"
    TYPE: str = "RPA"
    
    # Parâmetros padrão de aferição manual (segundos)
    MANUAL_TIME_PER_SUCCESS: float = 45.0
    MANUAL_TIME_PER_ERROR: float = 20.0

    def __init__(
        self,
        params: Optional[Dict[str, Any]] = None,
        log_callback: Optional[Callable[[str, str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ):
        self.params = params or {}
        self.log = log_callback or (lambda level, msg: print(f"[{level}] {msg}"))
        self.progress = progress_callback or (lambda current, total: None)
        self.cancel_check = cancel_check or (lambda: False)

        # Estado de execução e métricas padronizadas
        self.sap = SapSession(log_callback=self.log)
        self.sucessos = 0
        self.erros = 0
        self.itens_processados = 0
        self.total_itens = 0
        self.peps_com_falha: List[Dict[str, Any]] = []
        self.cancelled = False

        self.start_datetime = ""
        self.end_datetime = ""
        self.start_time = 0.0
        self.duration = 0.0

    @abstractmethod
    def validate_input(self):
        """Valida planilhas de entrada, argumentos obrigatórios e regras de sanidade."""
        pass

    @abstractmethod
    def prepare(self):
        """Prepara dados em memória, inicializa conexão com o ERP ou sistema de destino."""
        pass

    @abstractmethod
    def get_work_items(self) -> List[Any]:
        """Retorna a lista de itens de trabalho discretos para a esteira de processamento."""
        pass

    @abstractmethod
    def process_item(self, item: Any, index: int, total: int):
        """Processa um item de trabalho individual na transação de destino."""
        pass

    def recover_item_state(self, item: Any, exception: Exception):
        """Rotina de contingência chamada automaticamente quando o processamento de um item falha."""
        self.sap.safe_recover_state()

    def run(self) -> Dict[str, Any]:
        """Orquestra o ciclo de vida completo com isolamento de falhas e telemetria."""
        self.start_time = time.time()
        self.start_datetime = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.log("INFO", f"Iniciando [{self.JOB_NAME}] (v{self.JOB_VERSION})...")

        # 1. Validação de Insumos
        self.validate_input()

        # 2. Preparação e Conexão
        self.prepare()

        # 3. Esteira de Processamento de Itens
        items = self.get_work_items()
        self.total_itens = len(items)
        self.progress(0, self.total_itens)

        for idx, item in enumerate(items, start=1):
            if self.cancel_check():
                self.log("WARNING", f"Execução cancelada pelo operador no item {idx} de {self.total_itens}.")
                self.cancelled = True
                break

            self.sap.pulse_keep_alive()

            try:
                self.process_item(item, idx, self.total_itens)
                self.sucessos += 1
                self.itens_processados = idx
            except Exception as e_item:
                self.erros += 1
                self.itens_processados = idx
                err_msg = str(e_item)
                self.log("ERROR", f"Falha no item {idx}/{self.total_itens}: {err_msg}")

                item_repr = getattr(item, "pep", None) or getattr(item, "name", None) or str(item)
                self.peps_com_falha.append({
                    "linha": idx,
                    "pep": item_repr,
                    "material": str(item),
                    "motivo": err_msg
                })

                # Verifica desconexão crítica imediata
                if self.sap.is_session_disconnected(err_msg):
                    self.log("ERROR", "CRÍTICO: Sessão do SAP desconectada. Paralisando esteira imediatamente.")
                    raise RuntimeError(f"Sessão do SAP desconectada no item {idx}: {err_msg}")

                # Recupera estado para o próximo item
                try:
                    self.recover_item_state(item, e_item)
                except Exception:
                    pass

            self.progress(idx, self.total_itens)
            time.sleep(0.1)

        self.duration = time.time() - self.start_time
        self.end_datetime = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        status_str = "CANCELLED" if self.cancelled else "SUCCESS"
        status_msg = "cancelada pelo operador" if self.cancelled else "finalizada com sucesso"
        self.log(
            "SUCCESS" if not self.cancelled else "WARNING",
            f"Automação [{self.JOB_NAME}] {status_msg}! Total: {self.total_itens} | Sucessos: {self.sucessos} | Falhas: {self.erros} ({self.duration:.1f}s)"
        )

        # Cálculo de ROI Ponderado
        total_triados = self.sucessos + self.erros
        tempo_manual_estimado = (self.sucessos * self.MANUAL_TIME_PER_SUCCESS) + (self.erros * self.MANUAL_TIME_PER_ERROR)
        horas_poupadas = max(0.0, tempo_manual_estimado - self.duration)
        if horas_poupadas == 0.0 and total_triados > 0:
            horas_poupadas = (self.sucessos * (self.MANUAL_TIME_PER_SUCCESS * 0.5)) + (self.erros * self.MANUAL_TIME_PER_ERROR)

        motivo_final = "Cancelado pelo Operador" if self.cancelled else "Concluído com Sucesso"

        metadata = {
            "job_version": self.JOB_VERSION,
            "transacao": self.TRANSACTION,
            "modulo": self.MODULE,
            "tipo": self.TYPE,
            "data_inicio": self.start_datetime,
            "data_fim": self.end_datetime,
            "motivo_finalizacao": motivo_final,
            "tempo_manual_estimado_segundos": round(tempo_manual_estimado, 1),
            "tempo_robo_segundos": round(self.duration, 2),
            "horas_poupadas": round(horas_poupadas / 3600.0, 2),
            "itens_concluidos": self.sucessos,
            "erros_contagem": self.erros,
            "total_itens_triados": total_triados,
            "peps_com_falha": self.peps_com_falha
        }

        return {
            "job_id": self.JOB_ID,
            "job_name": self.JOB_NAME,
            "job_version": self.JOB_VERSION,
            "processed": self.sucessos,
            "errors": self.erros,
            "duration_seconds": round(self.duration, 2),
            "status": status_str,
            "metadata": metadata,
            "peps_com_falha": self.peps_com_falha
        }
