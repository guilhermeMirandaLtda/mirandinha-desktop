"""
Biblioteca da equipe (Etapa 6) — uma pasta de rede com arquivos .mirflow.json que o time
inteiro enxerga. Sem servidor: é só uma pasta compartilhada, configurada uma vez. O
caminho fica salvo por máquina em core/studio/team_library.json (cada analista aponta
pra sua própria unidade de rede mapeada — não é um valor pra sincronizar entre pessoas).
"""
import json
import os
from pathlib import Path
from typing import Optional, List, Dict, Any

_CONFIG_PATH = Path(__file__).resolve().parent / "team_library.json"


def get_team_library_path() -> Optional[str]:
    if not _CONFIG_PATH.exists():
        return None
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("path")
    except Exception:
        return None


def set_team_library_path(path: str) -> None:
    with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"path": path}, f, ensure_ascii=False, indent=2)


def list_team_library_files() -> List[Dict[str, Any]]:
    """
    Lista os .mirflow.json da pasta configurada, cada um já com o resumo (summarize_flow)
    — a galeria mostra isso direto no card, sem precisar abrir um seletor de arquivo pra
    cada fluxo. Pasta não configurada ou arquivo corrompido não derrubam a listagem —
    só ficam de fora.
    """
    path = get_team_library_path()
    if not path or not os.path.isdir(path):
        return []

    from core.studio.summary import summarize_flow

    files = []
    for entry in sorted(os.listdir(path)):
        if not entry.endswith(".mirflow.json"):
            continue
        full_path = os.path.join(path, entry)
        try:
            with open(full_path, "r", encoding="utf-8") as f:
                bundle = json.load(f)
            graph = bundle.get("graph", {})
            files.append({
                "file": entry,
                "file_path": full_path,
                "name": graph.get("name", entry),
                "transacao": graph.get("transacao", ""),
                "exported_at": bundle.get("exported_at", ""),
                "summary": summarize_flow(graph),
            })
        except Exception:
            continue
    return files
