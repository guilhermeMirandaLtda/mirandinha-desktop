"""
Contexto de execução de um grafo do Studio.
Nós leem e escrevem dados só através dele — nunca diretamente uns nos outros. Guarda a sessão
SAP, as variáveis do fluxo e o item corrente do laço (None fora de um flow.foreach).
"""
import re
from typing import Any, Dict, Optional

_TEMPLATE_RE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_.]*)\s*\}\}")


class ExecutionContext:
    def __init__(self, sap_session=None):
        self.sap = sap_session
        self.variables: Dict[str, Any] = {}
        self.item: Any = None
        self.item_var: str = "item"

    def set_var(self, name: str, value: Any):
        self.variables[name] = value

    def get_var(self, name: str, default: Any = None) -> Any:
        return self.variables.get(name, default)

    def _lookup_path(self, path: str) -> Any:
        """Resolve um caminho pontilhado ('diagrama.data') contra variables e o item corrente."""
        parts = path.split(".")
        head = parts[0]

        if head == self.item_var:
            root = self.item
        elif head in self.variables:
            root = self.variables[head]
        else:
            raise KeyError(f"Variável '{head}' não definida no contexto.")

        current = root
        for part in parts[1:]:
            if isinstance(current, dict):
                if part not in current:
                    raise KeyError(f"Caminho '{path}' inválido: campo '{part}' não existe.")
                current = current[part]
            else:
                current = getattr(current, part)
        return current

    def resolve_value(self, value: Any) -> Any:
        """
        Resolve o valor de um parâmetro de nó. Strings com um único placeholder
        '{{variavel}}' (o valor inteiro, nada mais ao redor) retornam o tipo original da
        variável; placeholders embutidos em texto maior viram interpolação de string.
        Valores não-string (bool, number, list, dict) retornam literais.
        """
        if not isinstance(value, str):
            return value

        full_match = _TEMPLATE_RE.fullmatch(value.strip())
        if full_match:
            return self._lookup_path(full_match.group(1))

        def _sub(m):
            resolved = self._lookup_path(m.group(1))
            return "" if resolved is None else str(resolved)

        return _TEMPLATE_RE.sub(_sub, value)
