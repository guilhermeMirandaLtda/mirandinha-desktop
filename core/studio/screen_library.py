"""
Biblioteca de Telas — a peça que torna o Studio no-code.
Promove os antigos core/rpa/selectors/*.json a "packs" com rótulo, tela de origem e tipo por
elemento. Um bloco pede "Data de necessidade" no inspetor; é aqui que isso resolve para o
caminho cru do SAP GUI Scripting — o usuário nunca precisa ver o segundo.

Cada pack é um arquivo em core/studio/screens/<pack>.json. Preencher a biblioteca (adicionar
packs, adicionar elementos) é tarefa técnica; montar o fluxo com o que ela expõe é tarefa do
analista — essa separação é o ponto central da Etapa 2.
"""
import json
from pathlib import Path
from typing import Dict, Any, List

_SCREENS_DIR = Path(__file__).resolve().parent / "screens"


def _pack_path(pack_name: str) -> Path:
    return _SCREENS_DIR / f"{pack_name}.json"


def list_packs() -> List[Dict[str, Any]]:
    """Resumo de cada pack disponível — para a futura tela de biblioteca do canvas."""
    packs = []
    for path in sorted(_SCREENS_DIR.glob("*.json")):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        packs.append({
            "pack": data.get("pack", path.stem),
            "transacao": data.get("transacao", ""),
            "nome": data.get("nome", path.stem),
            "total_elementos": len(data.get("elementos", {})),
        })
    return packs


def get_pack(pack_name: str) -> Dict[str, Any]:
    """Carrega um pack inteiro. Lança FileNotFoundError com mensagem clara se não existir."""
    path = _pack_path(pack_name)
    if not path.exists():
        disponiveis = ", ".join(p["pack"] for p in list_packs()) or "nenhum"
        raise FileNotFoundError(
            f"Pack de telas '{pack_name}' não encontrado em core/studio/screens/. "
            f"Packs disponíveis: {disponiveis}."
        )
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_element(pack_name: str, ref: str) -> Dict[str, Any]:
    """Retorna a definição de um elemento — rótulo, tela, tipo, id e fallbacks."""
    pack = get_pack(pack_name)
    elementos = pack.get("elementos", {})
    if ref not in elementos:
        disponiveis = ", ".join(sorted(elementos.keys())) or "nenhum"
        raise KeyError(
            f"Elemento '{ref}' não existe no pack '{pack_name}'. "
            f"Elementos disponíveis: {disponiveis}."
        )
    return elementos[ref]


def resolve_candidates(pack_name: str, ref: str) -> List[str]:
    """
    O id primário do elemento seguido dos seus fallbacks, na ordem em que devem ser
    tentados — é isto que GraphTask passa para SapSession.find_element_any().
    """
    el = get_element(pack_name, ref)
    return [el["id"]] + list(el.get("fallbacks", []))


def list_elements(pack_name: str, tipo: str = None) -> List[Dict[str, Any]]:
    """Elementos de um pack, opcionalmente filtrados por tipo — o que o inspetor do canvas
    usa (a partir da Etapa 3) para só oferecer alvos compatíveis com o bloco selecionado."""
    pack = get_pack(pack_name)
    result = []
    for ref, el in pack.get("elementos", {}).items():
        if tipo and el.get("tipo") != tipo:
            continue
        result.append({"ref": ref, **el})
    return result
