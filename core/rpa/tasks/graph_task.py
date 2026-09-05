"""
GraphTask — interpretador de grafos do Studio.
Herda RPAJobBase: console, progresso, cancelamento, ROI e gravação em job_history vêm de graça,
pela mesma razão que SAPZerarCompromissoTask e SAPDataNecessidadeTask já têm tudo isso.

Etapa 4: laço (flow.foreach) e condicional (flow.if) — o grafo deixa de ser um traço e vira
automação de verdade. O mapeamento sobre o ciclo de vida do RPAJobBase é o mesmo descrito no
plano técnico:

    validate_input()  -> valida o grafo e localiza o flow.foreach (se houver), sem executar nada
    prepare()         -> executa os nós ANTES do foreach (conectar, ler grade/planilha) —
                         falha aqui aborta o job inteiro, igual a qualquer task nativa
    get_work_items()  -> resolve o 'source' do foreach para a lista real de itens
    process_item()    -> executa o corpo do laço para UM item — falha aqui é isolada por
                         item pelo próprio RPAJobBase.run(), sem código extra

Grafo SEM flow.foreach continua no modo linear da Etapa 1/2: tudo roda dentro de
process_item() como uma única "execução", exatamente como antes — nenhuma mudança de
comportamento para os grafos e testes já existentes.
"""
import time
from typing import Callable, Dict, Any, List, Optional, Tuple

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

# Operadores válidos de flow.if — despacho fechado em dict, nunca eval()/exec(). Ver plano
# técnico v2, seção de riscos: "Injeção pelo flow.if".
_IF_OPERATORS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "contains": lambda a, b: b in a,
    "empty": lambda a, b: not a,
    "not_empty": lambda a, b: bool(a),
}

# Limite defensivo contra ciclo sem stop_type — nenhum grafo real chega perto disso.
_MAX_CHAIN_STEPS = 5000


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
        # Um nó com on_error="abort" dentro do CORPO DO LAÇO precisa poder derrubar o job
        # inteiro, não só o item corrente — RPAJobBase.run() só reconhece dois motivos pra
        # isso: sessão SAP desconectada, ou cancel_check() virar True. Este flag alimenta
        # um cancel_check combinado, então "abort" no meio de um item também para o laço,
        # em vez de silenciosamente seguir pro próximo item.
        self._external_cancel_check = cancel_check or (lambda: False)
        self._abort_requested = False

        super().__init__(
            params=params,
            log_callback=log_callback,
            progress_callback=progress_callback,
            cancel_check=self._is_cancelled,
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
        for k, v in (self.params or {}).items():
            self.ctx.set_var(k, v)

        self._start_node: Optional[Dict[str, Any]] = next(
            (n for n in graph.get("nodes", []) if n.get("type") == "flow.start"), None
        )
        self._foreach_node: Optional[Dict[str, Any]] = None  # definido em validate_input()

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
            "data.excel_read": self._h_data_excel_read,
            "data.distinct": self._h_data_distinct,
            "data.first_match": self._h_data_first_match,
            "data.format_date": self._h_data_format_date,
        }

    # ---- cancelamento (combina o cancel_check externo com abort interno) ----

    def _is_cancelled(self) -> bool:
        return self._abort_requested or self._external_cancel_check()

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

        if self._start_node is None:
            raise ValueError("Grafo sem nó 'flow.start'.")

        boundary = self._locate_boundary()
        if boundary is not None and boundary["type"] == "flow.foreach":
            self._foreach_node = boundary
            done_edge = next(
                (e for e in self.edges if e.get("from") == boundary["id"] and e.get("port") == "done"),
                None,
            )
            if done_edge is None:
                raise ValueError(f"'{boundary['id']}' (flow.foreach) não tem aresta na porta 'done'.")
            done_target = self.nodes_by_id.get(done_edge["to"])
            if not done_target or done_target.get("type") != "flow.end":
                raise ValueError(
                    f"A porta 'done' de '{boundary['id']}' precisa apontar direto para um "
                    f"'flow.end' nesta etapa — nós depois do laço chegam em etapa futura."
                )
            self.log("INFO", f"Grafo com laço: '{boundary['id']}' ({boundary.get('label', '')}).")
        else:
            self._foreach_node = None
            self.log("INFO", "Grafo linear (sem flow.foreach) — execução em item único.")

    def prepare(self):
        self.ctx.sap = self.sap
        if self._foreach_node is None:
            return
        # Nós antes do laço (conectar, ler grade/planilha, ...): falha aqui propaga e
        # aborta o job inteiro — sem tratamento por item, igual a qualquer task nativa.
        self._run_chain(self._start_node["id"], "out", stop_types=("flow.foreach",))

    def get_work_items(self) -> List[Any]:
        if self._foreach_node is None:
            # Grafo linear (Etapa 1/2): uma única "execução" representa o grafo inteiro.
            return [1]

        params = self._foreach_node.get("params", {})
        items = self.ctx.resolve_value(params["source"])
        if not isinstance(items, list):
            raise ValueError(
                f"'source' do flow.foreach ('{params['source']}') precisa resolver para uma "
                f"lista; veio {type(items).__name__}."
            )
        self.ctx.item_var = params.get("item_var", "item")
        return items

    def process_item(self, item: Any, index: int, total: int):
        if self._foreach_node is None:
            self._run_chain(self._start_node["id"], "out", stop_types=("flow.end",))
            return
        self.ctx.item = item
        self._run_chain(self._foreach_node["id"], "loop", stop_types=("flow.foreach", "flow.end"))

    # ---- localização estrutural do laço (sem executar nada) ----

    def _locate_boundary(self) -> Optional[Dict[str, Any]]:
        """
        Caminha do flow.start seguindo só a porta 'out' até achar flow.foreach ou flow.end.
        Não executa nada — roda dentro de validate_input() só pra decidir o modo (linear x
        laço). Se encontrar um flow.if antes de qualquer um dos dois, desiste e devolve None:
        o grafo entra em modo linear, cujo caminhador (_run_chain, usado por process_item())
        já sabe seguir flow.if normalmente. Só fica ambíguo — e por isso não suportado ainda —
        um flow.if cujo ramo leve a um flow.foreach; isso aparece como erro em tempo de
        execução (tipo sem executor), não aqui.
        """
        current_id = self._start_node["id"]
        visited = {current_id}
        while True:
            edge = next(
                (e for e in self.edges if e.get("from") == current_id and e.get("port", "out") == "out"),
                None,
            )
            if edge is None:
                return None
            nxt = self.nodes_by_id.get(edge["to"])
            if nxt is None:
                raise ValueError(f"Aresta aponta para nó inexistente: '{edge['to']}'.")
            if nxt["id"] in visited:
                raise ValueError(f"Ciclo detectado antes do laço, em '{nxt['id']}'.")
            visited.add(nxt["id"])
            if nxt["type"] in ("flow.end", "flow.foreach"):
                return nxt
            if nxt["type"] == "flow.if":
                return None
            current_id = nxt["id"]

    # ---- caminhada que EXECUTA os nós (fase de preparo e corpo do laço) ----

    def _run_chain(
        self, start_id: str, start_port: str, stop_types: Tuple[str, ...]
    ) -> Optional[Dict[str, Any]]:
        """
        Anda pelo grafo a partir de (start_id, start_port), executando cada nó no caminho,
        até bater num tipo em stop_types (retorna esse nó, sem executá-lo) ou não haver mais
        aresta (retorna None — fim natural do corpo do laço). flow.if desvia por 'true'/
        'false' sem contar como nó executado; todo outro tipo passa por _execute_node_in_chain,
        cujo retorno diz qual porta seguir ('out' no caminho feliz, 'error' com on_error=route).
        """
        current_id, current_port = start_id, start_port
        steps = 0
        while True:
            edge = next(
                (e for e in self.edges if e.get("from") == current_id and e.get("port", "out") == current_port),
                None,
            )
            if edge is None:
                return None

            nxt = self.nodes_by_id.get(edge["to"])
            if nxt is None:
                raise ValueError(f"Aresta aponta para nó inexistente: '{edge['to']}'.")
            if nxt["type"] in stop_types:
                return nxt

            steps += 1
            if steps > _MAX_CHAIN_STEPS:
                raise RuntimeError(f"Caminho excede {_MAX_CHAIN_STEPS} passos a partir de '{start_id}' — possível ciclo.")

            if nxt["type"] == "flow.if":
                branch = self._eval_if(nxt)
                current_id, current_port = nxt["id"], ("true" if branch else "false")
                continue

            next_port = self._execute_node_in_chain(nxt)
            current_id, current_port = nxt["id"], next_port

    def _execute_node_in_chain(self, node: Dict[str, Any]) -> str:
        """
        Executa um nó e decide qual porta seguir a partir dele, segundo seu on_error:
        'continue' engole o erro e segue por 'out'; 'route' segue por 'error'; 'skip_item'
        e 'abort' deixam a exceção subir — quem trata isso é o RPAJobBase (por item) ou o
        Python (fora de um laço, na fase de preparo, onde qualquer falha aborta o job).
        """
        node_id, ntype = node["id"], node["type"]

        if not is_implemented(ntype):
            raise RuntimeError(f"Nó '{node_id}' usa o tipo '{ntype}', ainda não implementado pelo runtime.")
        handler = self._handlers.get(ntype)
        if handler is None:
            raise RuntimeError(f"Nenhum executor registrado para o tipo '{ntype}'.")

        self.log("DEBUG", f"[{node_id}] {node.get('label', ntype)}")

        try:
            handler(node)
            return "out"
        except Exception as exc:
            on_error = node.get("on_error", "abort")
            self.log("ERROR", f"Falha no nó '{node_id}' ({node.get('label', ntype)}): {exc}")

            if on_error == "continue":
                self.log("WARNING", f"[{node_id}] on_error='continue' — seguindo para o próximo nó.")
                return "out"
            if on_error == "route":
                self.log("WARNING", f"[{node_id}] on_error='route' — desviando pela porta 'error'.")
                return "error"
            if on_error == "abort":
                self._abort_requested = True
            # abort ou skip_item: propaga. Dentro de um laço, o RPAJobBase isola por item;
            # fora dele (fase de preparo, ou grafo linear sem foreach), aborta o job inteiro.
            raise

    def _eval_if(self, node: Dict[str, Any]) -> bool:
        params = node.get("params", {})
        left = self.ctx.resolve_value(params["left"])
        right = self.ctx.resolve_value(params["right"])
        operator = params["operator"]

        op_fn = _IF_OPERATORS.get(operator)
        if op_fn is None:
            raise ValueError(f"Operador inválido em flow.if: '{operator}'.")

        result = bool(op_fn(left, right))
        self.log("DEBUG", f"[{node['id']}] Se: {left!r} {operator} {right!r} -> {result}")
        return result

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

    def _h_data_excel_read(self, node: Dict[str, Any]):
        import os
        import pandas as pd

        params = node.get("params", {})
        path = self.ctx.resolve_value(params["path"])
        sheet = params.get("sheet")
        columns = params["columns"]
        output_var = params.get("output_var", "linhas")

        if not path or not os.path.exists(path):
            raise FileNotFoundError(f"Arquivo de planilha não encontrado: '{path}'")

        read_kwargs = {"sheet_name": sheet} if sheet else {}
        df = pd.read_excel(path, **read_kwargs)
        df.columns = [str(c).strip() for c in df.columns]

        required = [c["name"] for c in columns]
        missing = [c for c in required if c not in df.columns]
        if missing:
            raise ValueError(f"A planilha deve conter as colunas: {required}. Faltando: {missing}")

        rows: List[Dict[str, Any]] = []
        for idx, row in df.iterrows():
            d: Dict[str, Any] = {"_row": int(idx)}
            for col in columns:
                key = col.get("as", col["name"])
                val = row[col["name"]]
                d[key] = None if pd.isna(val) else val
            rows.append(d)

        self.ctx.set_var(output_var, rows)
        self.log("INFO", f"Planilha lida: {len(rows)} linha(s) publicada(s) em '{output_var}'.")

    def _h_data_distinct(self, node: Dict[str, Any]):
        params = node.get("params", {})
        source = self.ctx.resolve_value(params["source"])
        field = params["field"]
        output_var = params["output_var"]

        seen: List[str] = []
        for row in source:
            val = row.get(field) if isinstance(row, dict) else None
            sval = str(val).strip() if val is not None else ""
            if sval and sval != "nan" and sval not in seen:
                seen.append(sval)

        if not seen:
            raise ValueError(f"Nenhum valor válido encontrado no campo '{field}'.")

        self.ctx.set_var(output_var, seen)
        self.log("INFO", f"{len(seen)} valor(es) único(s) de '{field}' publicados em '{output_var}'.")

    def _h_data_first_match(self, node: Dict[str, Any]):
        params = node.get("params", {})
        source = self.ctx.resolve_value(params["source"])
        field = params["field"]
        value = self.ctx.resolve_value(params["value"])
        output_var = params["output_var"]

        target_str = str(value).strip()
        match = None
        for row in source:
            if isinstance(row, dict) and str(row.get(field, "")).strip() == target_str:
                match = row
                break

        if match is None:
            raise ValueError(f"Nenhuma linha encontrada com {field}='{value}'.")

        self.ctx.set_var(output_var, match)

    def _h_data_format_date(self, node: Dict[str, Any]):
        import pandas as pd

        params = node.get("params", {})
        raw = self.ctx.resolve_value(params["value"])
        min_days = int(params.get("min_days", -60))
        max_days = int(params.get("max_days", 730))
        output_var = params["output_var"]

        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            raise ValueError("Data está vazia ou nula.")

        if isinstance(raw, pd.Timestamp):
            parsed = raw
        else:
            s = str(raw).strip()
            parsed = pd.to_datetime(s, format="%d/%m/%Y", errors="coerce") if "/" in s \
                else pd.to_datetime(s, errors="coerce")

        if parsed is None or pd.isna(parsed):
            raise ValueError(f"Formato de data inválido: '{raw}'. Use DD/MM/AAAA.")

        now = pd.Timestamp.now()
        diff_days = (parsed - now).days
        if diff_days < min_days:
            raise ValueError(f"Data '{parsed.strftime('%d/%m/%Y')}' no passado remoto ({diff_days} dias).")
        if diff_days > max_days:
            raise ValueError(
                f"Data '{parsed.strftime('%d/%m/%Y')}' excede a janela máxima ({diff_days} dias). "
                f"Possível erro de ano."
            )

        formatted = parsed.strftime("%d.%m.%Y")
        self.ctx.set_var(output_var, formatted)
        self.log("DEBUG", f"[{node['id']}] Data validada: {formatted} ({diff_days} dias).")
