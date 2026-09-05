"""
Automação SAP GUI: Eliminar Reserva (Transação MB22).
Herdeiro de RPAJobBase: utiliza SapSession unificado e seletores declarativos externos.
Marca a exclusão (RESB-XLOEK) de itens de reserva a partir de planilha Excel com colunas 'Reserva' e 'Item'.
"""
import os
import json
import time
import pandas as pd
from typing import Callable, Dict, Any, List, Optional
from core.rpa.base import RPAJobBase


class SAPEliminarReservaTask(RPAJobBase):
    JOB_ID = "job_mat_eliminar_reserva"
    JOB_NAME = "Eliminar Reserva"
    JOB_VERSION = "1.0.0"
    TRANSACTION = "MB22"
    MODULE = "Materiais"
    TYPE = "SAP / Gestão de Materiais"

    # Parâmetros auditados: ~40s manual por item de reserva e ~20s de triagem em caso de erro
    MANUAL_TIME_PER_SUCCESS = 40.0
    MANUAL_TIME_PER_ERROR = 20.0

    def __init__(
        self,
        spreadsheet_path: str,
        log_callback: Optional[Callable[[str, str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None
    ):
        super().__init__(
            params={"spreadsheet_path": spreadsheet_path},
            log_callback=log_callback,
            progress_callback=progress_callback,
            cancel_check=cancel_check
        )
        self.spreadsheet_path = spreadsheet_path
        self.work_items: List[Dict[str, Any]] = []
        self.selectors = self._load_selectors()

    def _load_selectors(self) -> Dict[str, str]:
        selector_file = os.path.join(os.path.dirname(__file__), "..", "selectors", "mb22.json")
        try:
            with open(selector_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("elements", {})
        except Exception:
            return {}

    def validate_input(self):
        """Valida a existência do arquivo e as colunas obrigatórias 'Reserva' e 'Item'."""
        if not self.spreadsheet_path or not os.path.exists(self.spreadsheet_path):
            raise FileNotFoundError(f"Arquivo de planilha não encontrado: '{self.spreadsheet_path}'")

        self.log("INFO", f"Lendo e validando planilha: {self.spreadsheet_path}")
        try:
            df = pd.read_excel(self.spreadsheet_path, dtype=str)
        except Exception as e:
            raise RuntimeError(f"Falha ao ler o arquivo Excel: {str(e)}")

        # Normalização inteligente de colunas
        required_cols = ["Reserva", "Item"]
        col_map = {}
        for req in required_cols:
            match = next((c for c in df.columns if str(req).lower() == str(c).strip().lower()), None)
            if not match:
                # busca por substring caso tenha acento ou sufixo
                match = next((c for c in df.columns if str(req).lower() in str(c).strip().lower()), None)
            if match:
                col_map[match] = req

        if len(col_map) == len(required_cols):
            df = df.rename(columns=col_map)
        else:
            missing = [r for r in required_cols if r not in df.columns]
            raise ValueError(f"A planilha deve conter as colunas obrigatórias: {required_cols}. Faltando: {missing}")

        items = []
        for idx, row in df.iterrows():
            reserva = str(row["Reserva"]).strip()
            item = str(row["Item"]).strip()
            if reserva and reserva != "nan" and item and item != "nan":
                items.append({
                    "linha": idx + 1,
                    "reserva": reserva,
                    "item": item
                })

        if not items:
            raise ValueError("Nenhum item com Reserva e Item válidos encontrado na planilha informada.")

        self.work_items = items
        self.log("INFO", f"Planilha validada com sucesso: {len(self.work_items)} reserva(s)/item(ns) para processamento.")

    def prepare(self):
        """Conecta à sessão do SAP GUI Scripting."""
        self.sap.connect()

    def get_work_items(self) -> List[Any]:
        return self.work_items

    def process_item(self, item_dict: Dict[str, Any], index: int, total: int):
        session = self.sap.session
        sel = self.selectors
        reserva = item_dict["reserva"]
        item_pos = item_dict["item"]

        self.log("INFO", f"Processando Reserva {reserva} / Item {item_pos} ({index}/{total})...")

        # 1. Iniciar transação MB22 de forma resiliente
        self.sap.start_transaction("MB22")
        time.sleep(1.2)

        # 2. Informar número da Reserva na tela inicial
        session.findById(sel.get("input_reserva", "wnd[0]/usr/ctxtRM07M-RSNUM")).text = reserva
        session.findById("wnd[0]").sendVKey(0)  # Enter
        time.sleep(0.6)

        # 3. Selecionar Item específico via Popup de seleção
        btn_sel = sel.get("btn_select_item", "wnd[0]/tbar[1]/btn[20]")
        session.findById(btn_sel).press()
        time.sleep(0.6)

        # Preencher Item na janela modal
        input_item = sel.get("input_item_popup", "wnd[1]/usr/txtRM07M-RSPOS")
        session.findById(input_item).text = item_pos
        session.findById("wnd[1]").sendVKey(0)  # Enter
        time.sleep(0.6)

        # 4. Marcar checkbox de Eliminação (RESB-XLOEK)
        chk_del = sel.get("chk_eliminar", "wnd[0]/usr/chkRESB-XLOEK")
        session.findById(chk_del).selected = True

        # 5. Salvar (btn[11])
        session.findById(sel.get("btn_save", "wnd[0]/tbar[0]/btn[11]")).press()
        time.sleep(0.8)

        # Verificar barra de status do SAP
        sbar_text = ""
        try:
            sbar_text = session.findById(sel.get("statusbar", "wnd[0]/sbar")).text
        except Exception:
            pass

        if "erro" in sbar_text.lower() or "bloquead" in sbar_text.lower():
            raise RuntimeError(f"Mensagem do SAP na Reserva {reserva}: {sbar_text}")

        self.log("SUCCESS", f"Reserva {reserva} Item {item_pos} eliminada com sucesso. ({sbar_text or 'Salvo'})")
