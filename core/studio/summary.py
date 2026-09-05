"""
Resumo de risco de um fluxo — o que o portão de importação (Etapa 6) mostra ANTES do
usuário decidir se importa um .mirflow.json que veio de outra pessoa. Um fluxo
compartilhado tem o mesmo poder que um .py: precisa declarar o que faz antes de rodar.

A detecção de "grava"/"elimina" é heurística (rótulo + params do nó), não uma prova
formal — é um sinal para o operador olhar com atenção, não um veredito automático.
"""
import json
from typing import Dict, Any, List

# Tipos de nó que efetivamente escrevem ou pressionam algo no SAP.
_WRITE_TYPES = {
    "sap.set_text", "sap.set_checkbox", "sap.save", "sap.press",
    "sap.toolbar_press", "sap.select",
}

# Termos que aparecem nos nomes reais das telas/campos de exclusão no Mirandinha
# (chk_eliminar, RESB-XLOEK, EBAKZ de "concluída/encerrada"...) — cobre os casos que
# o catálogo atual conhece; um fluxo com nome de campo diferente pode escapar disso.
_DELETE_KEYWORDS = (
    "elimina", "exclu", "delet", "cancela", "estorn", "xloek", "encerr", "conclu",
)


def _node_text(node: Dict[str, Any]) -> str:
    label = node.get("label", "") or ""
    params_str = json.dumps(node.get("params", {}), ensure_ascii=False)
    return f"{label} {params_str}".lower()


def _mentions_delete(node: Dict[str, Any]) -> bool:
    text = _node_text(node)
    return any(kw in text for kw in _DELETE_KEYWORDS)


def summarize_flow(graph: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resumo declarativo do que um grafo faz, sem executar nada — só lendo a estrutura.
    Usado tanto no portão de importação quanto (a partir da Etapa 5) no publish, se algum
    dia quisermos mostrar o mesmo aviso lá.
    """
    nodes = graph.get("nodes", [])

    transacoes = set()
    if graph.get("transacao"):
        transacoes.add(str(graph["transacao"]).upper())
    for n in nodes:
        if n.get("type") == "sap.transaction":
            tcode = n.get("params", {}).get("tcode")
            if isinstance(tcode, str) and "{{" not in tcode:
                transacoes.add(tcode.upper())

    grava = any(n.get("type") in _WRITE_TYPES for n in nodes)
    elimina = any(_mentions_delete(n) for n in nodes)

    insumos: List[Dict[str, Any]] = []
    for n in nodes:
        if n.get("type") == "data.excel_read":
            params = n.get("params", {})
            colunas = [c.get("name") for c in params.get("columns", []) if c.get("name")]
            insumos.append({"path_var": params.get("path", ""), "colunas": colunas})

    needs_review_ids = [n["id"] for n in nodes if n.get("needs_review")]

    return {
        "transacoes": sorted(transacoes),
        "grava": grava,
        "elimina_ou_exclui": elimina,
        "insumos": insumos,
        "needs_review_node_ids": needs_review_ids,
        "total_nos": len(nodes),
    }
