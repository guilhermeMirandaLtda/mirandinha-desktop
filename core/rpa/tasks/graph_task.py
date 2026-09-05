"""
GraphTask — interpretador de grafos do Studio.
Herda RPAJobBase: console, progresso, cancelamento, ROI e gravação em job_history vêm de graça,
pela mesma razão que SAPZerarCompromissoTask e SAPDataNecessidadeTask já têm tudo isso.

Etapa 1: só executa grafos LINEARES (flow.start -> ... -> flow.end, sem ramificação).
'flow.foreach' e 'flow.if' são reconhecidos pelo catálogo mas recusados aqui com uma mensagem
clara — chegam na Etapa 4, quando o corpo do laço passa a mapear sobre get_work_items()/
process_item() como descrito no plano técnico.
"""
import time
from typing import Callable, Dict, Any, List, Optional

from core.rpa.base import RPAJobBase
from core.studio.execution_context import ExecutionContext
from core.studio.node_catalog import is_implemented
from core.studio.validator import validate_graph
from core.studio.screen_library import resolve_candidates

# Ids universais de popup — os mesmos em qualquer transação SAP, por isso não vêm de
# nenhum pack da Biblioteca de Telas. 'window' (ex.: "wnd[1]") é prefixado na frente.
_POPUP_ACTION_SUFFIX = {
    "ok": "tbar[0]/btn[0]",
    "yes": "usr/btnSPOP-OPTION1",
    "no": "usr/btnSPOP-OPTION2",
    "cancel": "tbar[0]/btn[12]",
}


class GraphTask(RPAJobBase):
    TYPE = "Studio / Grafo"

    def __init__(
        self,
        graph: Dict[str, Any],
        log_callback: Optional[Callable[[str, str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        params: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            params=params,
            log_callback=log_callback,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
        self.graph = graph

        # Governança dinâmica — sobrescreve os defaults da classe com o que o grafo declara.
        self.JOB_ID = graph.get("flow_id", "flow_sem_id")
        self.JOB_NAME = graph.get("name", "Fluxo do Studio")
        self.JOB_VERSION = str(graph.get("schema_version", 1))
        self.TRANSACTION = graph.get("transacao", "AUTO")
        self.MODULE = graph.get("group", "Studio")

        self.nodes_by_id = {n["id"]: n for n in graph.get("nodes", [])}
        self.edges = graph.get("edges", [])

        self.ctx = ExecutionContext(sap_session=self.sap)
        for k, v in (graph.get("variables") or {}).items():
            self.ctx.set_var(k, v)

        self._chain: List[Dict[str, Any]] = []

        self._handlers = {
            "sap.connect": self._h_sap_connect,
            "sap.transaction": self._h_sap_transaction,
            "sap.grid_read": self._h_sap_grid_read,
            "sap.grid_double_click": self._h_sap_grid_double_click,
            "sap.set_text": self._h_sap_set_text,
            "sap.press": self._h_sap_press,
            "sap.select": self._h_sap_select,
            "sap.set_checkbox": self._h_sap_set_checkbox,
            "sap.toolbar_press": self._h_sap_toolbar_press,
            "sap.save": self._h_sap_save,
            "sap.back": self._h_sap_back,
            "sap.wait_for": self._h_sap_wait_for,
            "sap.handle_popup": self._h_sap_handle_popup,
            "flow.assert_absent": self._h_flow_assert_absent,
            "flow.escape": self._h_flow_escape,
            "data.log": self._h_data_log,
        }

    # ---- ciclo de vida do RPAJobBase ----

    def validate_input(self):
        result = validate_graph(self.graph)
        errors = [i for i in result["issues"] if i["severity"] == "error"]
        warnings = [i for i in result["issues"] if i["severity"] == "warning"]

        for w in warnings:
            self.log("WARNING", f"[{w['node_id']}] {w['message']}" if w["node_id"] else w["message"])

        if not result["ok"]:
            details = "; ".join(f"[{e['node_id']}] {e['message']}" if e["node_id"] else e["message"] for e in errors)
            raise ValueError(f"Grafo inválido: {details}")

        self._chain = self._build_linear_chain()
        self.log("INFO", f"Grafo validado: {len(self._chain)} nó(s) na cadeia linear.")

    def prepare(self):
        self.ctx.sap = self.sap

    def get_work_items(self) -> List[Any]:
        # Grafo linear (Etapa 1): uma única "execução" representa o grafo inteiro.
        # Isso muda na Etapa 4: com um flow.foreach no grafo, os itens aqui passam a ser
        # a lista resolvida pelo foreach, e o corpo do laço vira process_item().
        return [1]

    def process_item(self, item: Any, index: int, total: int):
        for node in self._chain:
            self._execute_node(node)

    # ---- montagem da cadeia linear ----

    def _build_linear_chain(self) -> List[Dict[str, Any]]:
        start = next((n for n in self.graph.get("nodes", []) if n.get("type") == "flow.start"), None)
        if start is None:
            raise ValueError("Grafo sem nó 'flow.start'.")

        chain: List[Dict[str, Any]] = []
        current_id = start["id"]
        visited = {current_id}

        while True:
            edge = next(
                (e for e in self.edges if e.get("from") == current_id and e.get("port", "out") == "out"),
                None,
            )
            if edge is None:
                break

            nxt = self.nodes_by_id.get(edge["to"])
            if nxt is None:
                raise ValueError(f"Aresta aponta para nó inexistente: '{edge['to']}'.")
            if nxt["id"] in visited:
                raise ValueError(f"Ciclo detectado no grafo linear em '{nxt['id']}'.")
            visited.add(nxt["id"])

            ntype = nxt.get("type")
            if ntype == "flow.end":
                break
            if ntype in ("flow.foreach", "flow.if"):
                raise ValueError(
                    f"Nó '{nxt['id']}' ({ntype}) requer suporte a laço/condicional, que chega "
                    f"na Etapa 4. A Etapa 1 só executa grafos lineares (sem ramificação)."
                )

            chain.append(nxt)
            current_id = nxt["id"]

        return chain

    # ---- execução de um nó ----

    def _execute_node(self, node: Dict[str, Any]):
        ntype = node["type"]
        node_id = node["id"]

        if not is_implemented(ntype):
            raise RuntimeError(
                f"Nó '{node_id}' usa o tipo '{ntype}', ainda não implementado pelo runtime "
                f"desta etapa."
            )

        handler = self._handlers.get(ntype)
        if handler is None:
            raise RuntimeError(f"Nenhum executor registrado para o tipo '{ntype}'.")

        self.log("DEBUG", f"[{node_id}] {node.get('label', ntype)}")

        try:
            handler(node)
        except Exception as exc:
            on_error = node.get("on_error", "abort")
            if on_error != "abort":
                self.log(
                    "WARNING",
                    f"[{node_id}] on_error='{on_error}' só tem semântica de laço a partir da "
                    f"Etapa 4 — tratando como 'abort' nesta execução.",
                )
            self.log("ERROR", f"Falha no nó '{node_id}' ({node.get('label', ntype)}): {exc}")
            raise

    # ---- resolução de alvo de tela ----

    def _resolve_target(self, target: Any) -> List[str]:
        """
        Retorna a lista de ids candidatos a tentar, em ordem, para SapSession.find_element_any().
        target pode ser um id literal do SAP GUI (string — modo avançado / migração) ou uma
        referência da Biblioteca de Telas {"pack": ..., "ref": ...} (o caso comum, no-code).
        """
        if isinstance(target, str):
            return [target]
        if isinstance(target, dict) and "pack" in target and "ref" in target:
            return resolve_candidates(target["pack"], target["ref"])
        raise ValueError(f"Formato de 'target' inválido: {target!r}")

    # ---- handlers de nó ----

    def _h_sap_connect(self, node: Dict[str, Any]):
        self.sap.connect()

    def _h_sap_transaction(self, node: Dict[str, Any]):
        params = node.get("params", {})
        tcode = self.ctx.resolve_value(params["tcode"])
        self.sap.start_transaction(tcode)
        self.log("INFO", f"Transação '{tcode}' iniciada.")

    def _h_sap_grid_read(self, node: Dict[str, Any]):
        params = node.get("params", {})
        candidates = self._resolve_target(params["target"])
        columns = params["columns"]
        output_var = params.get("output_var", "linhas")

        grid = self.sap.find_element_any(candidates)
        row_count = grid.rowCount

        resolved_cols: Dict[str, str] = {}
        for col in columns:
            col_name = col["name"]
            col_candidates = [col_name] + list(col.get("fallbacks", []))
            resolved = col_name
            if row_count > 0:
                for cand in col_candidates:
                    try:
                        grid.GetCellValue(0, cand)
                        resolved = cand
                        break
                    except Exception:
                        continue
            resolved_cols[col_name] = resolved

        rows: List[Dict[str, Any]] = []
        for i in range(row_count):
            row: Dict[str, Any] = {"_row": i}
            for col in columns:
                col_name = col["name"]
                try:
                    row[col_name] = grid.GetCellValue(i, resolved_cols[col_name])
                except Exception:
                    row[col_name] = None
            rows.append(row)

        self.ctx.set_var(output_var, rows)
        self.log("INFO", f"Grade lida: {row_count} linha(s) publicada(s) em '{output_var}'.")

    def _h_sap_grid_double_click(self, node: Dict[str, Any]):
        params = node.get("params", {})
        candidates = self._resolve_target(params["target"])
        row = self.ctx.resolve_value(params["row"])
        column = self.ctx.resolve_value(params["column"])

        grid = self.sap.find_element_any(candidates)
        grid.currentCellRow = int(row)
        grid.currentCellColumn = column
        grid.doubleClickCurrentCell()

    def _h_sap_set_text(self, node: Dict[str, Any]):
        params = node.get("params", {})
        candidates = self._resolve_target(params["target"])
        value = self.ctx.resolve_value(params["value"])
        el = self.sap.find_element_any(candidates)
        el.text = "" if value is None else str(value)

    def _h_sap_press(self, node: Dict[str, Any]):
        params = node.get("params", {})
        candidates = self._resolve_target(params["target"])
        self.sap.find_element_any(candidates).press()

    def _h_sap_select(self, node: Dict[str, Any]):
        params = node.get("params", {})
        candidates = self._resolve_target(params["target"])
        el = self.sap.find_element_any(candidates)
        node_ref = params.get("node")
        if node_ref is not None:
            el.selectedNode = self.ctx.resolve_value(node_ref)
        else:
            el.select()

    def _h_sap_set_checkbox(self, node: Dict[str, Any]):
        params = node.get("params", {})
        candidates = self._resolve_target(params["target"])
        el = self.sap.find_element_any(candidates)
        el.selected = bool(self.ctx.resolve_value(params["checked"]))

    def _h_sap_toolbar_press(self, node: Dict[str, Any]):
        params = node.get("params", {})
        candidates = self._resolve_target(params["target"])
        button = self.ctx.resolve_value(params["button"])
        self.sap.find_element_any(candidates).pressButton(button)

    def _h_sap_save(self, node: Dict[str, Any]):
        # Universal — btn[11] (Gravar) é o mesmo id em qualquer transação do SAP GUI.
        self.sap.find_element("wnd[0]/tbar[0]/btn[11]").press()

    def _h_sap_back(self, node: Dict[str, Any]):
        # Universal — F3 (vkey 3) é o mesmo em qualquer transação.
        self.sap.session.findById("wnd[0]").sendVKey(3)

    def _h_sap_wait_for(self, node: Dict[str, Any]):
        params = node.get("params", {})
        candidates = self._resolve_target(params["target"])
        timeout_ms = int(params.get("timeout_ms", 5000))
        poll_s = 0.08
        waited = 0.0

        while True:
            for cand in candidates:
                try:
                    self.sap.session.findById(cand)
                    return
                except Exception:
                    continue
            if waited >= timeout_ms / 1000.0:
                raise RuntimeError(f"Elemento não apareceu em {timeout_ms}ms: {candidates}")
            time.sleep(poll_s)
            waited += poll_s

    def _h_sap_handle_popup(self, node: Dict[str, Any]):
        params = node.get("params", {})
        window = params.get("window", "wnd[1]")
        action = params.get("action")
        optional = params.get("optional", True)

        if action not in _POPUP_ACTION_SUFFIX:
            raise ValueError(f"'action' inválida em sap.handle_popup: '{action}'. Use ok|yes|no|cancel.")

        try:
            popup = self.sap.session.findById(window)
        except Exception:
            if optional:
                self.log("DEBUG", f"Popup '{window}' não apareceu (opcional) — seguindo.")
                return
            raise RuntimeError(f"Popup esperado '{window}' não apareceu.")

        popup_text = ""
        try:
            popup_text = str(popup.text).strip()
        except Exception:
            pass
        if popup_text:
            self.log("WARNING", f"Popup do SAP: {popup_text}")

        action_id = f"{window}/{_POPUP_ACTION_SUFFIX[action]}"
        self.sap.session.findById(action_id).press()

    def _h_flow_assert_absent(self, node: Dict[str, Any]):
        params = node.get("params", {})
        candidates = self._resolve_target(params["target"])
        message = self.ctx.resolve_value(params["message"])

        for cand in candidates:
            try:
                self.sap.session.findById(cand)
            except Exception:
                continue
            raise RuntimeError(message)
        # Nenhum candidato encontrado — o elemento realmente sumiu, a asserção passa.

    def _h_flow_escape(self, node: Dict[str, Any]):
        params = node.get("params", {})
        attempts = max(1, int(params.get("attempts", 3)))
        for _ in range(attempts):
            self.sap.safe_recover_state()
        self.log("DEBUG", f"Rotina de escape executada ({attempts} tentativa(s)).")

    def _h_data_log(self, node: Dict[str, Any]):
        params = node.get("params", {})
        level = params.get("level", "INFO")
        message = self.ctx.resolve_value(params["message"])
        self.log(level, message)
