"""
Automação SAP GUI: Data Necessidade (Transação CJ20N).
Herdeiro de RPAJobBase: utiliza SapSession unificado e seletores declarativos externos.
"""
import os
import json
import time
import pandas as pd
from typing import Callable, Dict, Any, List, Optional
from core.rpa.base import RPAJobBase


class SAPDataNecessidadeTask(RPAJobBase):
    JOB_ID = "job_mat_data_necessidade"
    JOB_NAME = "Data Necessidade"
    JOB_VERSION = "1.1.0"
    TRANSACTION = "CJ20N"
    MODULE = "Materiais"
    TYPE = "SAP / Gestão de Materiais"

    # Parâmetros auditados via cronometria operacional
    MANUAL_TIME_PER_SUCCESS = 120.0
    MANUAL_TIME_PER_ERROR = 60.0

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
        self.df: Optional[pd.DataFrame] = None
        self.diagramas_unicos: List[str] = []
        self.selectors = self._load_selectors()

    def _load_selectors(self) -> Dict[str, str]:
        selector_file = os.path.join(os.path.dirname(__file__), "..", "selectors", "cj20n.json")
        try:
            with open(selector_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("elements", {})
        except Exception:
            return {}

    def validate_input(self):
        """Valida a existência do arquivo, as colunas obrigatórias e os diagramas."""
        if not self.spreadsheet_path or not os.path.exists(self.spreadsheet_path):
            raise FileNotFoundError(f"Arquivo de planilha não encontrado: '{self.spreadsheet_path}'")

        self.log("INFO", f"Lendo e validando planilha: {self.spreadsheet_path}")
        try:
            df = pd.read_excel(self.spreadsheet_path)
        except Exception as e_file:
            raise RuntimeError(f"Falha ao ler o arquivo Excel '{self.spreadsheet_path}': {str(e_file)}")

        df.columns = [str(c).strip() for c in df.columns]
        required_cols = ["PEP", "Diagrama", "Data Necessidade"]
        missing_cols = [c for c in required_cols if c not in df.columns]
        if missing_cols:
            raise ValueError(f"A planilha selecionada deve conter as colunas: {required_cols}. Faltando: {missing_cols}")

        diagramas_series = df["Diagrama"].dropna().astype(str).str.strip()
        self.diagramas_unicos = [d for d in diagramas_series.unique() if d and d != "nan"]

        if not self.diagramas_unicos:
            raise ValueError("Nenhum diagrama válido encontrado na planilha informada.")

        self.df = df
        self.log("INFO", f"Planilha validada: {len(df)} registros para {len(self.diagramas_unicos)} diagrama(s) único(s).")

    def prepare(self):
        """Conecta à sessão do SAP GUI Scripting."""
        self.sap.connect()

    def get_work_items(self) -> List[Any]:
        """Retorna os diagramas únicos que serão processados."""
        return self.diagramas_unicos

    def process_item(self, diagrama: str, index: int, total: int):
        """Processa a alteração em massa da data de necessidade no diagrama na CJ20N."""
        session = self.sap.session
        sel = self.selectors

        row = self.df[self.df["Diagrama"].astype(str).str.strip() == diagrama].iloc[0]
        data_nec_raw = row["Data Necessidade"]
        pep_ref = str(row["PEP"]).strip() if pd.notna(row["PEP"]) else f"Diag_{diagrama}"

        data_nec = self._format_date_for_sap(data_nec_raw)
        self.log("INFO", f"Processando Diagrama {diagrama} ({index}/{total}) | PEP: {pep_ref} | Data: {data_nec}...")

        # 1. Iniciar transação CJ20N de forma resiliente
        self.sap.start_transaction("CJ20N")
        time.sleep(1.5)

        # 2. Abrir Diagrama
        self._open_diagrama(diagrama)

        # 3. Selecionar nó na árvore de projeto
        tree_id = sel.get("tree_project", "wnd[0]/shellcont/shellcont/shell/shellcont[0]/shell/shellcont[1]/shell")
        tree = session.findById(tree_id)
        try:
            tree.selectedNode = "000002"
        except Exception:
            try:
                tree.selectedNode = "000001"
            except Exception:
                pass

        # 4. Acessar Visão Geral de Componentes
        tb_id = sel.get("toolbar_overview", "wnd[0]/usr/subDETAIL_AREA:SAPLCNPB_M:1010/cntlTOOLBAR_CONTAINER_OVERVIEW/shellcont/shell")
        session.findById(tb_id).pressButton("COMP_OVW")
        time.sleep(0.8)

        # 5. Clicar no botão de alteração em massa (copiar dados)
        btn_copy = sel.get("btn_mass_copy", "wnd[0]/usr/subDETAIL_AREA:SAPLCNPB_M:1010/subVIEW_AREA:SAPLCOMK:2799/tabsTABSTRIP_2700/tabpALLE/ssubSUBSCR_2000:SAPLCOMK:2701/btnICON_SYSTEM_COPY")
        session.findById(btn_copy).press()
        time.sleep(0.8)

        # 6. Desmarcar todos os campos se botão existir
        try:
            session.findById(sel.get("btn_deselect_all", "wnd[1]/usr/btnMALO_F")).press()
        except Exception:
            pass

        # 7. Marcar flag de Data de Necessidade e preencher valor
        session.findById(sel.get("chk_mark_bdter", "wnd[1]/usr/chkFLG_MARK_RESBD-MARK_BDTER")).selected = True
        session.findById(sel.get("input_bdter", "wnd[1]/usr/ctxtRESBD-BDTER")).text = data_nec

        # Executar marcação de todas as posições
        session.findById(sel.get("btn_mark_all_lines", "wnd[1]/usr/btnMAAL")).press()
        time.sleep(0.8)

        # 8. Confirmar Alteração em Massa na janela modal
        try:
            session.findById(sel.get("btn_modal_confirm", "wnd[1]/tbar[0]/btn[13]")).press()
        except Exception:
            try:
                session.findById(sel.get("btn_modal_enter", "wnd[1]/tbar[0]/btn[0]")).press()
            except Exception:
                pass

        time.sleep(0.8)

        # 9. Salvar alterações (btn[11])
        self.log("DEBUG", f"Gravando alterações do diagrama {diagrama}...")
        session.findById(sel.get("btn_save", "wnd[0]/tbar[0]/btn[11]")).press()
        time.sleep(1.0)

        # 10. Confirmar popup de salvamento/alerta (se surgir)
        try:
            session.findById(sel.get("btn_popup_save_confirm", "wnd[1]/usr/btnSPOP-OPTION1")).press()
        except Exception:
            try:
                session.findById("wnd[1]/tbar[0]/btn[0]").press()
            except Exception:
                pass

        self.log("SUCCESS", f"Diagrama {diagrama} reprogramado com sucesso para {data_nec}.")

    def _open_diagrama(self, diagrama: str):
        session = self.sap.session
        sel = self.selectors
        btn_open = sel.get("btn_open", "wnd[0]/shellcont/shellcont/shell/shellcont[0]/shell/shellcont[0]/shell")
        
        opened_modal = False
        try:
            session.findById(btn_open).pressButton("OPEN")
            opened_modal = True
        except Exception as e_btn:
            self.log("DEBUG", f"pressButton('OPEN') no controle principal falhou ({str(e_btn)}). Tentando via menu Projeto -> Abrir...")
            try:
                session.findById("wnd[0]/mbar/menu[0]/menu[0]").select()
                opened_modal = True
            except Exception as e_menu:
                # Tenta Ctrl+F1 (atalho padrão para abrir projeto na CJ20N)
                try:
                    session.findById("wnd[0]").sendVKey(13)  # Shift+F1 / Ctrl+O dependendo da GUI
                    opened_modal = True
                except Exception:
                    pass

        time.sleep(1.0)

        # Checar se a janela modal wnd[1] apareceu
        try:
            modal = session.findById("wnd[1]")
        except Exception:
            sbar_text = self.sap.get_statusbar_text()
            raise RuntimeError(f"Janela de abertura de projeto/diagrama não foi exibida pelo SAP. Barra de status: '{sbar_text}'")

        # Limpar filtros
        try: session.findById(sel.get("filter_proj_ext", "wnd[1]/usr/ctxtCNPB_W_ADD_OBJ_DYN-PROJ_EXT")).text = ""
        except Exception: pass
        try: session.findById(sel.get("filter_prps_ext", "wnd[1]/usr/ctxtCNPB_W_ADD_OBJ_DYN-PRPS_EXT")).text = ""
        except Exception: pass

        # Informar diagrama e confirmar
        try:
            session.findById(sel.get("input_aufnr", "wnd[1]/usr/ctxtCNPB_W_ADD_OBJ_DYN-AUFNR")).text = diagrama
        except Exception as e_aufnr:
            raise RuntimeError(f"Campo de diagrama na modal de busca não localizado: {str(e_aufnr)}")

        session.findById(sel.get("btn_search_confirm", "wnd[1]/tbar[0]/btn[0]")).press()
        time.sleep(1.5)


    def _format_date_for_sap(self, date_val: Any) -> str:
        """Formata e valida a data com guard-rails contra erros grosseiros (-60 dias a +24 meses)."""
        if pd.isna(date_val):
            raise ValueError("Data Necessidade está vazia ou nula.")

        parsed_dt = None
        if isinstance(date_val, (pd.Timestamp, time.struct_time)):
            parsed_dt = pd.to_datetime(date_val)
        else:
            s = str(date_val).strip()
            try:
                if "/" in s:
                    parsed_dt = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce")
                else:
                    parsed_dt = pd.to_datetime(s, errors="coerce")
            except Exception:
                pass

        if parsed_dt is None or pd.isna(parsed_dt):
            raise ValueError(f"Formato de data inválido: '{date_val}'. Use DD/MM/AAAA.")

        now = pd.Timestamp.now()
        diff_days = (parsed_dt - now).days
        if diff_days < -60:
            raise ValueError(f"Data Necessidade '{parsed_dt.strftime('%d/%m/%Y')}' no passado remoto ({diff_days} dias).")
        if diff_days > 730:
            raise ValueError(f"Data Necessidade '{parsed_dt.strftime('%d/%m/%Y')}' excede a janela máxima de 24 meses ({diff_days} dias). Possível erro de ano (ex: 2062).")

        return parsed_dt.strftime("%d.%m.%Y")
