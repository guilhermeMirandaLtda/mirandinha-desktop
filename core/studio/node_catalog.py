"""
Catálogo oficial de tipos de nó do Studio.
Fonte única da verdade sobre a forma dos parâmetros e as portas de saída de cada bloco —
o frontend (quando existir, a partir da Etapa 3) consulta isto via bridge e nunca declara
tipo por conta própria. Ver plano técnico v2, seção "Catálogo de blocos, por atividade".

Campo `implemented`: False para os tipos que o GraphTask ainda não sabe executar (chegam em
etapas futuras). O validador aceita qualquer tipo do catálogo; o GraphTask recusa em tempo de
execução um tipo com `implemented=False`, com mensagem clara de em qual etapa ele chega.
"""
from typing import Dict, Any, List

# Portas válidas para arestas (edges) do grafo.
VALID_PORTS = {"out", "true", "false", "loop", "done", "error"}

# Políticas de on_error válidas para blocos de ação.
VALID_ON_ERROR = {"abort", "skip_item", "continue", "route"}

NODE_CATALOG: Dict[str, Dict[str, Any]] = {

    # ---- Começar e terminar ----
    "flow.start": {
        "label": "Início",
        "category": "Sessão & fluxo",
        "params": [],
        "ports": ["out"],
        "needs_on_error": False,
        "implemented": True,
        "description": "Único por grafo. Ponto de entrada.",
    },
    "sap.connect": {
        "label": "Conectar ao SAP",
        "category": "Sessão & fluxo",
        "params": [],
        "ports": ["out"],
        "needs_on_error": True,
        "default_on_error": "abort",
        "implemented": True,
        "description": "Attach à sessão ativa via GetObject(\"SAPGUI\"). Falha aqui é sempre abort.",
    },
    "sap.transaction": {
        "label": "Abrir transação",
        "category": "Sessão & fluxo",
        "params": [{"name": "tcode", "kind": "text", "required": True}],
        "ports": ["out"],
        "needs_on_error": True,
        "default_on_error": "abort",
        "implemented": True,
        "description": "Escreve em okcd e envia Enter, via SapSession.start_transaction().",
    },
    "flow.end": {
        "label": "Fim",
        "category": "Sessão & fluxo",
        "params": [],
        "ports": [],
        "needs_on_error": False,
        "implemented": True,
        "description": "Consolida contadores e encerra.",
    },

    # ---- Mexer na tela ----
    "sap.set_text": {
        "label": "Escrever num campo",
        "category": "Interação de tela",
        "params": [
            {"name": "target", "kind": "target", "required": True},
            {"name": "value", "kind": "text", "required": True},
        ],
        "ports": ["out"],
        "needs_on_error": True,
        "implemented": False,
        "description": "value aceita literal ou {{variavel}}.",
    },
    "sap.press": {
        "label": "Pressionar botão",
        "category": "Interação de tela",
        "params": [{"name": "target", "kind": "target", "required": True}],
        "ports": ["out"],
        "needs_on_error": True,
        "implemented": False,
        "description": "Botão de tela ou de barra.",
    },
    "sap.select": {
        "label": "Selecionar",
        "category": "Interação de tela",
        "params": [
            {"name": "target", "kind": "target", "required": True},
            {"name": "node", "kind": "text", "required": False},
        ],
        "ports": ["out"],
        "needs_on_error": True,
        "implemented": False,
        "description": "Abas, radio buttons, nós de árvore.",
    },
    "sap.set_checkbox": {
        "label": "Marcar caixa",
        "category": "Interação de tela",
        "params": [
            {"name": "target", "kind": "target", "required": True},
            {"name": "checked", "kind": "bool", "required": True},
        ],
        "ports": ["out"],
        "needs_on_error": True,
        "implemented": False,
        "description": "",
    },
    "sap.toolbar_press": {
        "label": "Acionar barra de ferramentas",
        "category": "Interação de tela",
        "params": [
            {"name": "target", "kind": "target", "required": True},
            {"name": "button", "kind": "text", "required": True},
        ],
        "ports": ["out"],
        "needs_on_error": True,
        "implemented": False,
        "description": "O pressButton(\"COMP_OVW\") da CJ20N.",
    },
    "sap.save": {
        "label": "Gravar",
        "category": "Interação de tela",
        "params": [],
        "ports": ["out"],
        "needs_on_error": True,
        "implemented": False,
        "description": "Atividade, não btn[11].",
    },
    "sap.back": {
        "label": "Voltar",
        "category": "Interação de tela",
        "params": [],
        "ports": ["out"],
        "needs_on_error": True,
        "implemented": False,
        "description": "Atividade, não sendVKey(3).",
    },

    # ---- Grid / ALV ----
    "sap.grid_read": {
        "label": "Ler a grade",
        "category": "Grid / ALV",
        "params": [
            {"name": "target", "kind": "target", "required": True},
            {"name": "columns", "kind": "column_list", "required": True},
            {"name": "output_var", "kind": "text", "required": False, "default": "linhas"},
        ],
        "ports": ["out"],
        "needs_on_error": True,
        "default_on_error": "abort",
        "implemented": True,
        "description": "Publica `linhas` no contexto. Cada coluna aceita fallbacks.",
    },
    "sap.grid_double_click": {
        "label": "Abrir detalhe (duplo clique)",
        "category": "Grid / ALV",
        "params": [
            {"name": "target", "kind": "target", "required": True},
            {"name": "row", "kind": "expr", "required": True},
            {"name": "column", "kind": "text", "required": True},
        ],
        "ports": ["out"],
        "needs_on_error": True,
        "implemented": False,
        "description": "O drill-down da CN52N.",
    },

    # ---- Robustez ----
    "sap.wait_for": {
        "label": "Esperar elemento existir",
        "category": "Robustez",
        "params": [
            {"name": "target", "kind": "target", "required": True},
            {"name": "timeout_ms", "kind": "number", "required": False, "default": 5000},
        ],
        "ports": ["out", "error"],
        "needs_on_error": True,
        "implemented": False,
        "description": "Espera o elemento existir, não o relógio passar.",
    },
    "sap.handle_popup": {
        "label": "Tratar popup",
        "category": "Robustez",
        "params": [
            {"name": "window", "kind": "text", "required": False, "default": "wnd[1]"},
            {"name": "action", "kind": "text", "required": True},
            {"name": "optional", "kind": "bool", "required": False, "default": True},
        ],
        "ports": ["out"],
        "needs_on_error": True,
        "implemented": False,
        "description": "Captura o texto do popup antes de confirmar — vai para o log e o relatório.",
    },
    "flow.assert_absent": {
        "label": "Conferir que fechou",
        "category": "Robustez",
        "params": [
            {"name": "target", "kind": "target", "required": True},
            {"name": "message", "kind": "text", "required": True},
        ],
        "ports": ["out", "error"],
        "needs_on_error": True,
        "implemented": False,
        "description": "\"A tela de detalhe continuou aberta\" = a gravação falhou. Verificação positiva de sucesso.",
    },
    "flow.escape": {
        "label": "Rotina de escape",
        "category": "Robustez",
        "params": [
            {"name": "sequence", "kind": "list", "required": False},
            {"name": "attempts", "kind": "number", "required": False, "default": 3},
        ],
        "ports": ["out"],
        "needs_on_error": False,
        "implemented": False,
        "description": "Envolve SapSession.safe_recover_state(), com sequência editável.",
    },

    # ---- Lógica & dados ----
    "flow.foreach": {
        "label": "Para cada",
        "category": "Lógica & dados",
        "params": [
            {"name": "source", "kind": "var_ref", "required": True},
            {"name": "item_var", "kind": "text", "required": False, "default": "item"},
        ],
        "ports": ["loop", "done"],
        "needs_on_error": False,
        "implemented": False,
        "description": "Define a unidade de progresso e de skip_item.",
    },
    "flow.if": {
        "label": "Se",
        "category": "Lógica & dados",
        "params": [
            {"name": "left", "kind": "expr", "required": True},
            {"name": "operator", "kind": "operator", "required": True},
            {"name": "right", "kind": "expr", "required": True},
        ],
        "ports": ["true", "false"],
        "needs_on_error": False,
        "implemented": False,
        "description": "Três campos estruturados. Nunca uma expressão avaliada.",
    },
    "data.excel_read": {
        "label": "Ler planilha",
        "category": "Dados",
        "params": [
            {"name": "path", "kind": "text", "required": True},
            {"name": "sheet", "kind": "text", "required": False},
            {"name": "columns", "kind": "column_list", "required": True},
            {"name": "output_var", "kind": "text", "required": False, "default": "linhas"},
        ],
        "ports": ["out"],
        "needs_on_error": True,
        "default_on_error": "abort",
        "implemented": False,
        "description": "Reaproveita o pandas que já está no projeto.",
    },
    "data.distinct": {
        "label": "Valores únicos",
        "category": "Dados",
        "params": [
            {"name": "source", "kind": "var_ref", "required": True},
            {"name": "field", "kind": "text", "required": True},
            {"name": "output_var", "kind": "text", "required": True},
        ],
        "ports": ["out"],
        "needs_on_error": True,
        "implemented": False,
        "description": "Os diagramas únicos da CJ20N.",
    },
    "data.format_date": {
        "label": "Formatar e validar data",
        "category": "Dados",
        "params": [
            {"name": "value", "kind": "expr", "required": True},
            {"name": "min_days", "kind": "number", "required": False, "default": -60},
            {"name": "max_days", "kind": "number", "required": False, "default": 730},
            {"name": "output_var", "kind": "text", "required": True},
        ],
        "ports": ["out", "error"],
        "needs_on_error": True,
        "implemented": False,
        "description": "Guarda-corpo contra erro de ano. Vem de _format_date_for_sap().",
    },
    "data.log": {
        "label": "Registrar no console",
        "category": "Dados",
        "params": [
            {"name": "level", "kind": "log_level", "required": False, "default": "INFO"},
            {"name": "message", "kind": "text", "required": True},
        ],
        "ports": ["out"],
        "needs_on_error": False,
        "implemented": True,
        "description": "Os cinco níveis do design system.",
    },
}


def get_node_catalog() -> Dict[str, Any]:
    """Retorna o catálogo completo — é o que studio_node_catalog() da bridge vai expor."""
    return NODE_CATALOG


def get_node_spec(node_type: str) -> Dict[str, Any]:
    spec = NODE_CATALOG.get(node_type)
    if spec is None:
        raise ValueError(f"Tipo de nó desconhecido: '{node_type}'.")
    return spec


def is_implemented(node_type: str) -> bool:
    spec = NODE_CATALOG.get(node_type)
    return bool(spec and spec.get("implemented"))


def list_categories() -> List[str]:
    seen = []
    for spec in NODE_CATALOG.values():
        cat = spec["category"]
        if cat not in seen:
            seen.append(cat)
    return seen
