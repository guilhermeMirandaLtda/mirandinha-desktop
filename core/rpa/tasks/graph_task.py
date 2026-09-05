"""
GraphTask — interpretador de grafos do Studio.
Herda RPAJobBase: console, progresso, cancelamento, ROI e gravação em job_history vêm de graça,
pela mesma razão que SAPZerarCompromissoTask e SAPDataNecessidadeTask já têm tudo isso.

Etapa 1: só executa grafos LINEARES (flow.start -> ... -> flow.end, sem ramificação).
'flow.foreach' e 'flow.if' são reconhecidos pelo catálogo mas recusados aqui com uma mensagem
clara — chegam na Etapa 4, quando o corpo do laço passa a mapear sobre get_work_items()/
process_item() como descrito no plano técnico.
"""
from typing import Callable, Dict, Any, List, Optional

from core.rpa.base import RPAJobBase
from core.studio.execution_context import ExecutionContext
from core.studio.node_catalog import is_implemented
from core.studio.validator import validate_graph


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

    def _resolve_target(self, target: Any) -> str:
        if isinstance(target, str):
            return target
        if isinstance(target, dict) and "pack" in target and "ref" in target:
            raise RuntimeError(
                f"Referência de tela '{target['pack']}.{target['ref']}' requer a Biblioteca de "
                f"Telas, que chega na Etapa 2. Use um id literal do SAP GUI por enquanto."
            )
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
        target = self._resolve_target(params["target"])
        columns = params["columns"]
        output_var = params.get("output_var", "linhas")

        grid = self.sap.find_element(target)
        row_count = grid.rowCount

        resolved_cols: Dict[str, str] = {}
        for col in columns:
            col_name = col["name"]
            candidates = [col_name] + list(col.get("fallbacks", []))
            resolved = col_name
            if row_count > 0:
                for cand in candidates:
                    try:
                        grid.GetCellValue(0, cand)
                        resolved = cand
                        break
                    except Exception:
                        continue
            resolved_cols[col_name] = resolved

        rows: List[Dict[str, Any]] = []
        for i in range(row_count):
            row = {}
            for col in columns:
                col_name = col["name"]
                try:
                    row[col_name] = grid.GetCellValue(i, resolved_cols[col_name])
                except Exception:
                    row[col_name] = None
            rows.append(row)

        self.ctx.set_var(output_var, rows)
        self.log("INFO", f"Grade lida: {row_count} linha(s) publicada(s) em '{output_var}'.")

    def _h_data_log(self, node: Dict[str, Any]):
        params = node.get("params", {})
        level = params.get("level", "INFO")
        message = self.ctx.resolve_value(params["message"])
        self.log(level, message)
