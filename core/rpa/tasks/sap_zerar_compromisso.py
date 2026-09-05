"""
Automação SAP GUI: Zerar Compromisso de Materiais (Transação CN52N).
Conecta-se à sessão ativa do SAP via win32com.client e zera quantidades e locais de descarga.
Suporta progresso em tempo real e cancelamento gracioso pelo operador.
"""
import time
from typing import Callable, Dict, Any

class SAPZerarCompromissoTask:
    def __init__(self, log_callback: Callable[[str, str], None] = None, progress_callback: Callable[[int, int], None] = None, cancel_check: Callable[[], bool] = None):
        self.log = log_callback or (lambda level, msg: print(f"[{level}] {msg}"))
        self.progress = progress_callback or (lambda current, total: None)
        self.cancel_check = cancel_check or (lambda: False)
        # Atributos de telemetria persistidos na instância para contingência
        self.sucessos = 0
        self.erros = 0
        self.total_grid = 0
        self.itens_processados = 0
        self.peps_com_falha = []
        self.cancelled = False

    def run(self) -> Dict[str, Any]:
        self.log("INFO", "Iniciando conexão com o SAP GUI Scripting...")
        
        try:
            import win32com.client
        except ImportError:
            raise RuntimeError("Biblioteca 'pywin32' não encontrada no ambiente Python.")

        try:
            sap_gui_auto = win32com.client.GetObject("SAPGUI")
            if not sap_gui_auto:
                raise RuntimeError("Não foi possível obter o objeto SAPGUI. O SAP Logon está aberto?")

            application = sap_gui_auto.GetScriptingEngine
            if not application:
                raise RuntimeError("Scripting Engine do SAP não habilitado no servidor ou cliente.")

            if application.Children.Count == 0:
                raise RuntimeError("Nenhuma conexão ativa encontrada no SAP GUI.")

            connection = application.Children(0)
            if connection.Children.Count == 0:
                raise RuntimeError("Nenhuma sessão ativa aberta no SAP GUI.")

            session = connection.Children(0)
            self.log("SUCCESS", "Conectado com sucesso à sessão ativa do SAP.")

            # Maximiza janela principal
            session.findById("wnd[0]").maximize()

            # Identifica a tabela/grid do ALV da CN52N
            try:
                grid = session.findById("wnd[0]/usr/cntlALVCONTAINER/shellcont/shell")
            except Exception as e:
                raise RuntimeError("Tabela ALV da transação CN52N não localizada. Certifique-se de estar com a lista exibida na tela.")

            row_count = grid.rowCount
            self.total_grid = row_count
            self.log("INFO", f"Encontradas {row_count} linhas na tabela do ALV da CN52N.")
            self.progress(0, row_count)

            sucessos = 0
            erros = 0
            cancelled = False
            peps_com_falha = []

            # Cache inicial das colunas do ALV para acelerar leitura
            col_posid = "POSID"
            try:
                grid.GetCellValue(0, "POSID")
            except:
                col_posid = "POSID_EDIT"

            col_maktx = "MAKTX"
            try:
                grid.GetCellValue(0, "MAKTX")
            except:
                col_maktx = "MATXT"

            last_keep_alive = time.time()
            KEEP_ALIVE_INTERVAL = 90.0  # Keep-alive a cada 90 segundos

            for i in range(row_count):
                # Checagem de cancelamento do usuário
                if self.cancel_check():
                    self.log("WARNING", f"Execução cancelada pelo usuário no item {i+1} de {row_count}.")
                    cancelled = True
                    break

                # Pulso de Keep-Alive periódico para renovar timeout do SAP
                now = time.time()
                if now - last_keep_alive >= KEEP_ALIVE_INTERVAL:
                    try:
                        # Toca suavemente na propriedade da sessão para renovar o timer no servidor
                        _ = session.Info.Program
                        _ = session.findById("wnd[0]/sbar").text
                        last_keep_alive = now
                        self.log("DEBUG", "Pulso Keep-Alive enviado ao SAP para evitar timeout de inatividade.")
                    except Exception:
                        pass

                wbs = ""
                material = ""

                # Leitura direta sem exceções COM lentas
                try:
                    wbs = grid.GetCellValue(i, col_posid)
                except:
                    wbs = f"PEP_{i+1}"

                try:
                    material = grid.GetCellValue(i, col_maktx)
                except:
                    material = "Material"

                self.log("INFO", f"Processando item {i+1} de {row_count} (PEP: {wbs} | Material: {material})...")

                # Duplo clique na célula FLMNG
                try:
                    grid.currentCellRow = i
                    grid.currentCellColumn = "FLMNG"
                    grid.doubleClickCurrentCell()

                    # Aguarda até 1.5s o detalhe abrir (responsivo)
                    detail_ready = False
                    for _ in range(15):
                        try:
                            session.findById("wnd[0]/usr/subDETAIL_AREA:SAPLCNPB_M:1010")
                            detail_ready = True
                            break
                        except:
                            time.sleep(0.08)

                    if not detail_ready:
                        time.sleep(0.3)

                    # Aba de detalhes
                    try:
                        session.findById("wnd[0]/shellcont/shellcont/shell/shellcont[1]/shell/shellcont[1]/shell").topNode = "         26"
                        session.findById("wnd[0]/tbar[1]/btn[13]").press()
                    except Exception as ex_aba:
                        raise Exception(f"Erro ao abrir aba de detalhes: {str(ex_aba)}")

                    # Zera quantidade (MENGE) e local de descarga (ABLAD)
                    try:
                        session.findById("wnd[0]/usr/subDETAIL_AREA:SAPLCNPB_M:1010/subVIEW_AREA:SAPLCOMD:2800/tabsTABSTRIP_2700/tabpMKAG/ssubSUBSCR_2700:SAPLCOMD:2701/txtRESBD-MENGE").text = "0"
                        session.findById("wnd[0]/usr/subDETAIL_AREA:SAPLCNPB_M:1010/subVIEW_AREA:SAPLCOMD:2800/tabsTABSTRIP_2700/tabpMKAG/ssubSUBSCR_2700:SAPLCOMD:2701/txtRESBD-ABLAD").text = "."
                    except Exception as ex_text:
                        raise Exception(f"Item bloqueado ou somente leitura: {str(ex_text)}")

                    # Salvar (btn[11])
                    try:
                        session.findById("wnd[0]/tbar[0]/btn[11]").press()
                    except Exception as ex_save:
                        raise Exception(f"Erro ao salvar: {str(ex_save)}")

                    # Trata popup wnd[1] (se houver)
                    popup_msg = ""
                    try:
                        try:
                            popup_msg = session.findById("wnd[1]/usr/txtSPOP-VARTEXT100").text
                        except:
                            popup_msg = session.findById("wnd[1]/usr/lblSPOP-VARTEXT100").text
                        
                        session.findById("wnd[1]/tbar[0]/btn[0]").press()
                        self.log("WARNING", f"Popup de alerta do SAP confirmada: {popup_msg}")
                        time.sleep(0.3)
                    except:
                        pass

                    # Aguarda retorno à grade ou fechamento do detalhe
                    for _ in range(12):
                        try:
                            session.findById("wnd[0]/usr/subDETAIL_AREA:SAPLCNPB_M:1010")
                            time.sleep(0.08)
                        except:
                            break

                    detail_still_open = False
                    try:
                        session.findById("wnd[0]/usr/subDETAIL_AREA:SAPLCNPB_M:1010")
                        detail_still_open = True
                    except:
                        detail_still_open = False

                    if detail_still_open:
                        error_desc = "Falha ao gravar compromisso"
                        if popup_msg:
                            error_desc += f" ({popup_msg.strip()})"
                        raise Exception(error_desc)

                    sucessos += 1
                    self.sucessos = sucessos
                    self.itens_processados = i + 1
                    self.log("SUCCESS", f"Item {i+1} concluído: PEP {wbs} | Material {material} zerado com sucesso.")

                except Exception as ex:
                    erros += 1
                    self.erros = erros
                    self.itens_processados = i + 1
                    err_str = str(ex)
                    self.log("ERROR", f"Erro no item {i+1} ({wbs}): {err_str}")

                    peps_com_falha.append({
                        "linha": i + 1,
                        "pep": wbs,
                        "material": material,
                        "motivo": err_str
                    })
                    self.peps_com_falha = peps_com_falha

                    # Detecção imediata de queda de conexão / fechamento da sessão SAP
                    is_disconnected = (
                        "-2147417848" in err_str or
                        "desconectado de seus clientes" in err_str.lower() or
                        "the remote server machine does not exist" in err_str.lower() or
                        "rpc server is unavailable" in err_str.lower() or
                        "call was rejected by callee" in err_str.lower()
                    )

                    if is_disconnected:
                        self.log("ERROR", "CRÍTICO: Conexão com a sessão do SAP foi perdida/fechada! Interrompendo automação imediatamente.")
                        raise RuntimeError(f"Conexão com o SAP GUI foi interrompida no item {i+1}: {err_str}")

                    # Rotina de Escape de volta ao ALV para erros transitórios de tela
                    self.log("DEBUG", "Executando rotina de escape para retornar à grade ALV...")
                    escape_attempts = 0
                    while escape_attempts < 3:
                        try:
                            session.findById("wnd[0]/usr/cntlALVCONTAINER/shellcont/shell")
                            break
                        except Exception as ex_esc:
                            esc_str = str(ex_esc)
                            if "-2147417848" in esc_str or "desconectado" in esc_str.lower():
                                self.log("ERROR", "CRÍTICO: Sessão SAP indisponível durante tentativa de recuperação.")
                                raise RuntimeError("Sessão do SAP desconectada.")
                            try:
                                session.findById("wnd[1]/tbar[0]/btn[0]").press()
                            except:
                                pass
                            try:
                                session.findById("wnd[0]/tbar[0]/btn[12]").press()
                            except:
                                pass
                            time.sleep(0.5)
                            try:
                                session.findById("wnd[0]/tbar[0]/btn[3]").press()
                            except:
                                pass
                            time.sleep(0.5)
                            try:
                                session.findById("wnd[1]/usr/btnSPOP-OPTION2").press()
                            except:
                                pass
                            escape_attempts += 1

                self.progress(i + 1, row_count)
                time.sleep(0.1)

            self.cancelled = cancelled
            self.sucessos = sucessos
            self.erros = erros
            self.peps_com_falha = peps_com_falha

            status_msg = "cancelado pelo usuário" if cancelled else "finalizado com sucesso"
            self.log("SUCCESS" if not cancelled else "WARNING", f"Processo {status_msg}! Total no Grid: {row_count} | Sucessos: {sucessos} | Exceções: {erros}")
            return {
                "total": row_count,
                "sucessos": sucessos,
                "erros": erros,
                "peps_com_falha": peps_com_falha,
                "cancelled": cancelled
            }

        except Exception as e:
            self.log("ERROR", f"Falha geral no bot do SAP: {str(e)}")
            raise e
