"""
Validador de grafos do Studio.
Roda em validate_input() do GraphTask e (a partir da Etapa 5) no portão de publicação.
Retorna sempre {"ok": bool, "issues": [{"node_id", "severity", "message"}]} — nunca lança
exceção sozinho; quem chama decide o que fazer com "ok=False" (GraphTask levanta ValueError,
o portão de publicação recusa).
"""
from typing import Dict, Any, List
from core.studio.node_catalog import NODE_CATALOG, VALID_PORTS, VALID_ON_ERROR

# Tipos que não precisam de on_error porque não executam ação (marcadores de fluxo puro).
_NO_ON_ERROR_TYPES = {"flow.start", "flow.end", "flow.foreach", "flow.if", "flow.escape"}


def _issue(issues: List[Dict[str, Any]], node_id: str, severity: str, message: str):
    issues.append({"node_id": node_id, "severity": severity, "message": message})


def validate_graph(graph: Dict[str, Any]) -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []

    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []

    if not nodes:
        _issue(issues, None, "error", "O grafo não tem nenhum nó.")
        return {"ok": False, "issues": issues}

    nodes_by_id = {}
    for n in nodes:
        nid = n.get("id")
        if not nid:
            _issue(issues, None, "error", "Existe um nó sem 'id'.")
            continue
        if nid in nodes_by_id:
            _issue(issues, nid, "error", f"Id de nó duplicado: '{nid}'.")
            continue
        nodes_by_id[nid] = n

    # 1. Exatamente um flow.start
    starts = [n for n in nodes if n.get("type") == "flow.start"]
    if len(starts) == 0:
        _issue(issues, None, "error", "O grafo precisa de um nó 'flow.start'.")
    elif len(starts) > 1:
        for s in starts:
            _issue(issues, s.get("id"), "error", "Existe mais de um 'flow.start' no grafo.")

    # 2. Ao menos um flow.end
    ends = [n for n in nodes if n.get("type") == "flow.end"]
    if len(ends) == 0:
        _issue(issues, None, "warning", "O grafo não tem nenhum nó 'flow.end'.")

    # 3. Tipos conhecidos + parâmetros obrigatórios + on_error
    for n in nodes:
        nid = n.get("id")
        ntype = n.get("type")
        if ntype not in NODE_CATALOG:
            _issue(issues, nid, "error", f"Tipo de nó desconhecido: '{ntype}'.")
            continue

        spec = NODE_CATALOG[ntype]
        params = n.get("params") or {}
        for p in spec.get("params", []):
            if p.get("required") and p["name"] not in params:
                _issue(issues, nid, "error", f"Falta o parâmetro obrigatório '{p['name']}' em '{ntype}'.")

        if ntype not in _NO_ON_ERROR_TYPES:
            on_error = n.get("on_error")
            if not on_error:
                _issue(issues, nid, "error", f"Nó '{nid}' ({ntype}) não declara 'on_error'.")
            elif on_error not in VALID_ON_ERROR:
                _issue(issues, nid, "error", f"'on_error' inválido em '{nid}': '{on_error}'.")

        if n.get("needs_review"):
            _issue(issues, nid, "warning", f"Nó '{nid}' está marcado como pendente de revisão.")

    # 4. Arestas: nós existentes e portas válidas
    edge_ids_seen = set()
    for e in edges:
        eid = e.get("id")
        if eid:
            if eid in edge_ids_seen:
                _issue(issues, None, "error", f"Id de aresta duplicado: '{eid}'.")
            edge_ids_seen.add(eid)

        src, dst, port = e.get("from"), e.get("to"), e.get("port", "out")
        if src not in nodes_by_id:
            _issue(issues, eid, "error", f"Aresta '{eid}' referencia nó de origem inexistente: '{src}'.")
        if dst not in nodes_by_id:
            _issue(issues, eid, "error", f"Aresta '{eid}' referencia nó de destino inexistente: '{dst}'.")
        if port not in VALID_PORTS:
            _issue(issues, eid, "error", f"Aresta '{eid}' usa porta inválida: '{port}'.")

    # 5. Nós órfãos (inalcançáveis a partir do start) — aviso, não bloqueia a Etapa 1
    if starts:
        reachable = {starts[0]["id"]}
        changed = True
        while changed:
            changed = False
            for e in edges:
                if e.get("from") in reachable and e.get("to") not in reachable:
                    reachable.add(e.get("to"))
                    changed = True
        for n in nodes:
            if n.get("id") not in reachable:
                _issue(issues, n.get("id"), "warning", f"Nó '{n.get('id')}' é inalcançável a partir do 'flow.start'.")

    has_error = any(i["severity"] == "error" for i in issues)
    return {"ok": not has_error, "issues": issues}
