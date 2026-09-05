#!/usr/bin/env python
"""
Harness de linha de comando do Studio — Etapa 1.
Prova o runtime do grafo sem depender de canvas nenhum. Uso:

    python scripts/run_flow.py --seed [destino.json]
        Copia o grafo de exemplo (conectar + abrir CN52N + ler grade) para um arquivo.

    python scripts/run_flow.py --validate <arquivo.json>
        Valida um grafo e imprime os problemas encontrados, sem tocar no SAP.

    python scripts/run_flow.py --list
        Lista os fluxos já salvos no SQLite (studio_flows).

    python scripts/run_flow.py <arquivo.json>
        Executa o grafo de verdade contra a sessão SAP ativa e grava o resultado
        em job_history — o mesmo destino que os robôs nativos usam.
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Terminal do Windows (cmd/PowerShell) costuma abrir em cp1252/850 — força UTF-8 para
# os acentos e os travessões não virarem lixo.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

SAMPLE_GRAPH = PROJECT_ROOT / "core" / "studio" / "samples" / "cn52n_grid_read.json"

_LEVEL_COLOR = {
    "INFO": "\033[36m",
    "SUCCESS": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "DEBUG": "\033[90m",
}
_RESET = "\033[0m"


def console_log(level: str, message: str):
    color = _LEVEL_COLOR.get(level.upper(), "")
    print(f"{color}[{level.upper():7s}]{_RESET} {message}")


def console_progress(current: int, total: int):
    if total > 0:
        pct = int(current / total * 100)
        print(f"          progresso: {current}/{total} ({pct}%)")


def cmd_seed(dest: str):
    dest_path = Path(dest)
    shutil.copyfile(SAMPLE_GRAPH, dest_path)
    print(f"Grafo de exemplo escrito em: {dest_path.resolve()}")
    print("Edite o arquivo se quiser, depois rode:")
    print(f"    python scripts/run_flow.py {dest_path}")


def cmd_validate(path: str):
    from core.studio.validator import validate_graph

    with open(path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    result = validate_graph(graph)
    issues = result["issues"]

    if not issues:
        print(f"OK — grafo '{graph.get('name', path)}' sem problemas.")
        return 0

    for issue in issues:
        tag = "ERRO" if issue["severity"] == "error" else "AVISO"
        node = f"[{issue['node_id']}] " if issue["node_id"] else ""
        print(f"{tag}: {node}{issue['message']}")

    print()
    print("OK." if result["ok"] else "INVÁLIDO — corrija os erros acima antes de executar.")
    return 0 if result["ok"] else 1


def cmd_list():
    from core.storage import list_studio_flows

    flows = list_studio_flows()
    if not flows:
        print("Nenhum fluxo salvo ainda em studio_flows.")
        return

    for f in flows:
        pub = "publicado" if f["is_published"] else "rascunho"
        print(f"{f['flow_id']:40s} {f['name']:35s} [{pub}] atualizado em {f['updated_at']}")


def cmd_run(path: str):
    from core.rpa.tasks.graph_task import GraphTask
    from core.storage import record_job_execution

    with open(path, "r", encoding="utf-8") as f:
        graph = json.load(f)

    print(f"Executando grafo: {graph.get('name', path)}\n")

    task = GraphTask(
        graph=graph,
        log_callback=console_log,
        progress_callback=console_progress,
        cancel_check=lambda: False,
    )

    start = time.time()
    try:
        result = task.run()
    except Exception as exc:
        duration = time.time() - start
        record_job_execution(
            job_id=graph.get("flow_id", "flow_sem_id"),
            job_name=graph.get("name", "Fluxo do Studio"),
            duration=duration,
            items=0,
            status="FAILED",
            error_msg=str(exc),
            metadata={
                "job_version": str(graph.get("schema_version", 1)),
                "transacao": graph.get("transacao", "AUTO"),
                "modulo": graph.get("group", "Studio"),
                "tipo": "Studio / Grafo",
                "motivo_finalizacao": f"Interrompido por erro: {exc}",
            },
        )
        print(f"\nFALHOU: {exc}")
        return 1

    record_job_execution(
        job_id=result["job_id"],
        job_name=result["job_name"],
        duration=result["duration_seconds"],
        items=result["processed"] + result["errors"],
        status=result["status"],
        metadata=result["metadata"],
    )

    print()
    print(f"Status: {result['status']}")
    print(f"Duração: {result['duration_seconds']}s")
    print(f"Processados: {result['processed']} | Erros: {result['errors']}")
    print("Gravado em job_history.")
    return 0 if result["status"] != "FAILED" else 1


def main():
    parser = argparse.ArgumentParser(description="Harness de linha de comando do Studio.")
    parser.add_argument("path", nargs="?", help="Arquivo do grafo (.json) a executar ou validar.")
    parser.add_argument("--seed", nargs="?", const="flow_seed.json", metavar="DESTINO",
                         help="Escreve o grafo de exemplo em DESTINO (padrão: flow_seed.json).")
    parser.add_argument("--validate", metavar="ARQUIVO",
                         help="Valida o grafo em ARQUIVO sem executar.")
    parser.add_argument("--list", action="store_true", help="Lista os fluxos salvos no banco.")
    args = parser.parse_args()

    if args.seed is not None:
        cmd_seed(args.seed)
        return 0
    if args.validate:
        return cmd_validate(args.validate)
    if args.list:
        cmd_list()
        return 0
    if args.path:
        return cmd_run(args.path)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
