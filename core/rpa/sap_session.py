"""
Gerenciador unificado de conexão e interação com o SAP GUI Scripting.
Centraliza autenticação de sessão, keep-alive periódico, detecção de erros de RPC/queda e navegação segura.
"""
import time
from typing import Optional, Any, Callable


class SapSession:
    """Encapsula a sessão ativa do SAP GUI Scripting com blindagem de conectividade."""

    def __init__(self, log_callback: Optional[Callable[[str, str], None]] = None):
        self.log = log_callback or (lambda level, msg: print(f"[{level}] {msg}"))
        self.session = None
        self.last_keep_alive = time.time()
        self.keep_alive_interval = 90.0

    def connect(self) -> Any:
        """Conecta-se à sessão ativa do SAP GUI Scripting via win32com."""
        self.log("INFO", "Conectando ao SAP GUI Scripting...")
        try:
            import win32com.client
        except ImportError:
            raise RuntimeError("Biblioteca 'pywin32' não encontrada no ambiente Python.")

        try:
            sap_gui_auto = win32com.client.GetObject("SAPGUI")
            if not sap_gui_auto:
                raise RuntimeError("Objeto SAPGUI não encontrado. O SAP Logon está aberto?")

            application = sap_gui_auto.GetScriptingEngine
            if not application:
                raise RuntimeError("Scripting Engine do SAP desabilitado no servidor ou cliente.")

            if application.Children.Count == 0:
                raise RuntimeError("Nenhuma conexão ativa encontrada no SAP GUI.")

            connection = application.Children(0)
            if connection.Children.Count == 0:
                raise RuntimeError("Nenhuma sessão ativa aberta no SAP GUI.")

            self.session = connection.Children(0)
            self.log("SUCCESS", "Conectado com sucesso à sessão ativa do SAP.")

            try:
                self.session.findById("wnd[0]").maximize()
            except Exception:
                pass

            self.last_keep_alive = time.time()
            return self.session
        except Exception as e:
            err_msg = str(e)
            if "Objeto SAPGUI não encontrado" in err_msg or "Scripting Engine" in err_msg:
                raise e
            raise RuntimeError(f"Falha ao conectar à sessão ativa do SAP: {err_msg}")

    def pulse_keep_alive(self):
        """Envia pulso leve periódico para renovar o timer de inatividade do servidor SAP."""
        now = time.time()
        if now - self.last_keep_alive >= self.keep_alive_interval:
            try:
                if self.session:
                    _ = self.session.Info.Program
                    self.last_keep_alive = now
                    self.log("DEBUG", "Pulso Keep-Alive enviado ao SAP para prevenir timeout de inatividade.")
            except Exception:
                pass

    def is_session_disconnected(self, exception_msg: str) -> bool:
        """Avalia se uma exceção capturada representa queda física ou encerramento da conexão COM."""
        err_lower = str(exception_msg).lower()
        return (
            "-2147417848" in err_lower or
            "desconectado de seus clientes" in err_lower or
            "the remote server machine does not exist" in err_lower or
            "rpc server is unavailable" in err_lower or
            "call was rejected by callee" in err_lower
        )

    def find_element(self, element_id: str) -> Any:
        """Busca elemento na sessão com validação."""
        if not self.session:
            raise RuntimeError("Sessão SAP não inicializada.")
        return self.session.findById(element_id)

    def find_element_any(self, candidates: list) -> Any:
        """
        Tenta uma lista de ids em ordem — o id primário de um elemento da Biblioteca de
        Telas seguido dos seus fallbacks. Usado pelo GraphTask do Studio para resolver
        alvos sem que o grafo precise saber qual variante de tela está ativa.
        """
        if not self.session:
            raise RuntimeError("Sessão SAP não inicializada.")
        last_err = None
        for cand in candidates:
            try:
                return self.session.findById(cand)
            except Exception as e:
                last_err = e
        raise RuntimeError(
            f"Nenhum dos elementos foi encontrado na tela: {candidates}. Último erro: {last_err}"
        )

    def start_transaction(self, tcode: str):
        """Navega para uma transação do SAP de forma blindada contra erros de prefixo e telas presas."""
        if not self.session:
            raise RuntimeError("Sessão SAP não inicializada.")

        clean_tcode = tcode.strip().replace("/n", "").replace("/N", "").upper()
        self.log("DEBUG", f"Navegando para a transação SAP: '{clean_tcode}'...")

        # Estratégia 1: Tentar pelo método nativo StartTransaction com o código limpo
        try:
            self.session.StartTransaction(clean_tcode)
            time.sleep(1.2)
            # Verifica se gerou mensagem de erro na barra de status
            sbar_text = self.get_statusbar_text()
            if sbar_text and any(k in sbar_text.lower() for k in ["não existe", "not exist", "desconhecid", "unknown"]):
                raise RuntimeError(f"SAP reportou: {sbar_text}")
            return
        except Exception as e:
            self.log("DEBUG", f"StartTransaction('{clean_tcode}') falhou ({str(e)}). Tentando via okcd com /n...")

        # Estratégia 2: Comando /n no campo okcd (reseta estado e força a transação)
        try:
            okcd = self.session.findById("wnd[0]/tbar[0]/okcd")
            okcd.text = f"/n{clean_tcode}"
            self.session.findById("wnd[0]").sendVKey(0)  # Enter
            time.sleep(1.2)
        except Exception as e2:
            self.log("WARNING", f"Falha ao digitar no campo okcd: {str(e2)}")

    def get_statusbar_text(self) -> str:
        """Lê com segurança o texto da barra de status do SAP se existir."""
        if not self.session:
            return ""
        try:
            sbar = self.session.findById("wnd[0]/sbar")
            return str(sbar.text).strip() if sbar else ""
        except Exception:
            return ""

    def safe_recover_state(self):

        """Rotina de escape segura: fecha modais secundárias e descarta tela com F3."""
        if not self.session:
            return
        try:
            # 1. Fechar popup secundária se houver
            try:
                self.session.findById("wnd[1]").close()
            except Exception:
                pass

            # 2. Pressionar F3 (Voltar / btn[3])
            try:
                self.session.findById("wnd[0]/tbar[0]/btn[3]").press()
            except Exception:
                pass

            # 3. Inspecionar e confirmar popup de não salvar dados com segurança
            try:
                popup = self.session.findById("wnd[1]")
                if popup:
                    popup_text = ""
                    try:
                        popup_text = popup.findById("usr/txtSPOP-VARTEXT100").text
                    except Exception:
                        try:
                            popup_text = popup.findById("usr/lblSPOP-VARTEXT100").text
                        except Exception:
                            popup_text = str(popup.text)

                    self.log("DEBUG", f"Popup de saída detectada: '{popup_text}'. Acionando descarte seguro.")
                    try:
                        # Opção NÃO salvar
                        self.session.findById("wnd[1]/usr/btnSPOP-OPTION2").press()
                    except Exception:
                        try:
                            self.session.findById("wnd[1]/tbar[0]/btn[12]").press()  # F12 Cancelar
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception:
            pass
