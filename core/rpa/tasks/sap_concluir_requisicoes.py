"""
Automação SAP GUI: Concluir Requisições (Transação ME52N).
Herdeiro de RPAJobBase: utiliza SapSession unificado e seletores declarativos externos.
Marca o flag de requisição concluída (EBAN-EBAKZ) a partir de planilha Excel com colunas 'Requisicao' e 'Item'.
"""
import os
import json
import time
import pandas as pd
from typing import Callable, Dict, Any, List, Optional
from core.rpa.base import RPAJobBase


class SAPConcluirRequisicoesTask(RPAJobBase):
    JOB_ID = "job_mat_concluir_requisicoes"
    JOB_NAME = "Concluir Requisições"
    JOB_VERSION = "1.0.0"
    TRANSACTION = "ME52N"
    MODULE = "Suprimentos"
    TYPE = "SAP / Suprimentos"

    # Parâmetros auditados: ~45s manual por requisição/item e ~25s de triagem em caso de bloqueio/erro
    MANUAL_TIME_PER_SUCCESS = 45.0
    MANUAL_TIME_PER_ERROR = 25.0

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
        selector_file = os.path.join(os.path.dirname(__file__), "..", "selectors", "me52n.json")
        try:
            with open(selector_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("elements", {})
        except Exception:
            return {}

    def validate_input(self):
        """Valida a existência do arquivo e as colunas obrigatórias 'Requisicao' (e opcionalmente 'Item')."""
        if not self.spreadsheet_path or not os.path.exists(self.spreadsheet_path):
            raise FileNotFoundError(f"Arquivo de planilha não encontrado: '{self.spreadsheet_path}'")

        self.log("INFO", f"Lendo e validando planilha de requisições: {self.spreadsheet_path}")
        try:
            df = pd.read_excel(self.spreadsheet_path, dtype=str)
        except Exception as e:
            raise RuntimeError(f"Falha ao ler o arquivo Excel: {str(e)}")

        # Normalização inteligente: busca coluna com nome contendo 'requisicao' ou 'req' ou 'banfn'
        req_col = next((c for c in df.columns if any(k in str(c).strip().lower() for k in ["requisicao", "requisição", "banfn", "req"])), None)
        if not req_col:
            raise ValueError(f"A planilha deve conter a coluna 'Requisicao' (ou 'BANFN'). Colunas encontradas: {list(df.columns)}")

        item_col = next((c for c in df.columns if any(k in str(c).strip().lower() for k in ["item", "bnfpo", "posicao", "posição"])), None)

        items = []
        for idx, row in df.iterrows():
            req = str(row[req_col]).strip()
            item = str(row[item_col]).strip() if item_col else "10"
            if req and req != "nan":
                items.append({
                    "linha": idx + 1,
                    "requisicao": req,
                    "item": item if item and item != "nan" else "10"
                })

        if not items:
            raise ValueError("Nenhuma requisição válida encontrada na planilha informada.")

        self.work_items = items
        self.log("INFO", f"Planilha validada: {len(self.work_items)} requisição(ões) para encerramento.")

    def prepare(self):
        """Conecta à sessão do SAP GUI Scripting."""
        self.sap.connect()

    def get_work_items(self) -> List[Any]:
        return self.work_items

    def process_item(self, item_dict: Dict[str, Any], index: int, total: int):
        session = self.sap.session
        sel = self.selectors
        requisicao = item_dict["requisicao"]
        posicao = item_dict["item"]

        self.log("INFO", f"Processando Requisição {requisicao} (Item {posicao}) [{index}/{total}]...")

        # 1. Iniciar transação ME52N de forma resiliente
        self.sap.start_transaction("ME52N")
        time.sleep(1.2)

        # 2. Abrir requisição específica pelo botão 'Outra Requisição' (Shift+F5 / btn[17])
        btn_other = sel.get("btn_other_req", "wnd[0]/tbar[1]/btn[17]")
        try:
            session.findById(btn_other).press()
        except Exception:
            session.findById("wnd[0]").sendVKey(17)

        time.sleep(0.6)

        # Digitar número da requisição no popup
        input_banfn = sel.get("input_banfn_popup", "wnd[1]/usr/subSUB0:SAPLMEGUI:0003/ctxtMEPO_SELECT_DOCUMENT-BANFN")
        session.findById(input_banfn).text = requisicao
        session.findById("wnd[1]").sendVKey(0)  # Enter para abrir
        time.sleep(1.0)

        # 3. Marcar flag de Concluída (EBAN-EBAKZ)
        # Tenta marcar via grade de posições ou detalhes da requisição
        marked = False
        try:
            # Tenta encontrar checkbox direto na tela
            chk_ebakz = session.findById("wnd[0]/usr/subSUB0:SAPLMEGUI:0015/subSUB2:SAPLMEVIEWS:1100/subSUB2:SAPLMEVIEWS:1200/subSUB1:SAPLMEGUI:1211/tblSAPLMEGUITC_1211/chkMEREQ3211-EBAKZ[0,0]")
            chk_ebakz.selected = True
            marked = True
        except Exception:
            pass

        if not marked:
            try:
                # Tenta aba Quantidades/Datas (Detail Area)
                session.findById("wnd[0]/usr/subSUB0:SAPLMEGUI:0010/subSUB3:SAPLMEVIEWS:1100/subSUB2:SAPLMEVIEWS:1200/subSUB1:SAPLMEGUI:1301/subSUB1:SAPLMEGUI:1304/chkMEREQ3304-EBAKZ").selected = True
                marked = True
            except Exception:
                pass

        if not marked:
            # Fallback genérico: tenta localizar qualquer checkbox com nome EBAKZ
            try:
                session.findById("wnd[0]/usr").findByName("MEREQ3211-EBAKZ", "GuiCheckBox").selected = True
                marked = True
            except Exception as ex_chk:
                raise RuntimeError(f"Não foi possível localizar o campo de 'Requisição Concluída' na ME52N: {str(ex_chk)}")

        # 4. Salvar (btn[11])
        session.findById(sel.get("btn_save", "wnd[0]/tbar[0]/btn[11]")).press()
        time.sleep(1.0)

        # Verificar mensagens de erro ou confirmação
        sbar_text = ""
        try:
            sbar_text = session.findById(sel.get("statusbar", "wnd[0]/sbar")).text
        except Exception:
            pass

        if "bloquead" in sbar_text.lower() or "erro" in sbar_text.lower():
            raise RuntimeError(f"Mensagem do SAP na Requisição {requisicao}: {sbar_text}")

        self.log("SUCCESS", f"Requisição {requisicao} (Item {posicao}) marcada como concluída com êxito. ({sbar_text or 'Gravado'})")
