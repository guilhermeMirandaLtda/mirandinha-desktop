"""
Gerenciador de persistência local SQLite para histórico, auditoria e metadados detalhados do Mirandinha.
Permite armazenar métricas agregadas e payload JSON de metadados operacionais para cada execução.
"""
import sqlite3
import os
import json
from datetime import datetime
from typing import List, Dict, Any

import sys

# Garante que o banco SQLite seja persistido na pasta real do executável/projeto, mesmo quando empacotado
if getattr(sys, 'frozen', False):
    APP_ROOT = os.path.dirname(sys.executable)
else:
    APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_PATH = os.path.join(APP_ROOT, "mirandinha_history.db")

# Tempo médio estimado que um operador humano leva por item no SAP (segundos)
# Para cada item o analista precisa dar duplo clique, abrir detalhes, inspecionar e tentar salvar/fechar
MANUAL_SECONDS_PER_ITEM = 45.0

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                job_id TEXT NOT NULL,
                job_name TEXT NOT NULL,
                duration_seconds REAL NOT NULL,
                items_processed INTEGER NOT NULL,
                time_saved_hours REAL DEFAULT 0.0,
                status TEXT NOT NULL,
                error_message TEXT,
                metadata TEXT
            )
        """)
        # Migração automática de colunas caso o banco já existisse
        cursor.execute("PRAGMA table_info(job_history)")
        columns = [row[1] for row in cursor.fetchall()]
        if "time_saved_hours" not in columns:
            cursor.execute("ALTER TABLE job_history ADD COLUMN time_saved_hours REAL DEFAULT 0.0")
        if "metadata" not in columns:
            cursor.execute("ALTER TABLE job_history ADD COLUMN metadata TEXT")

        # ---- Módulo Studio: fluxos montados no editor visual (Etapa 1) ----
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS studio_flows (
                flow_id         TEXT PRIMARY KEY,
                name            TEXT NOT NULL,
                group_name      TEXT,
                transacao       TEXT,
                graph_json      TEXT NOT NULL,
                schema_version  INTEGER NOT NULL DEFAULT 1,
                is_published    INTEGER DEFAULT 0,
                origem          TEXT DEFAULT 'proprio',
                created_at      TEXT,
                updated_at      TEXT
            )
        """)
        # append-only: nunca sobrescreve, permite voltar a uma versão que funcionava
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS studio_flow_versions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                flow_id     TEXT NOT NULL,
                graph_json  TEXT NOT NULL,
                saved_at    TEXT NOT NULL,
                note        TEXT
            )
        """)
        conn.commit()

def record_job_execution(
    job_id: str, 
    job_name: str, 
    duration: float, 
    items: int, 
    status: str, 
    error_msg: str = None,
    metadata: Dict[str, Any] = None
):
    """
    Persiste a execução e os metadados ricos da transação.
    Calcula tempo economizado considerando que tanto os itens processados com sucesso quanto
    os itens triados/com exceção poupam o trabalho manual do analista de abrir e verificar tela por tela.
    """
    init_db()
    
    # Itens analisados pelo robô (sucessos + falhas triadas)
    erros = (metadata and metadata.get("erros_contagem")) or 0
    total_inspecionados = max(items, items + erros)

    # Tempo que o analista levaria para inspecionar e tratar manualmente cada linha
    tempo_manual_estimado = total_inspecionados * MANUAL_SECONDS_PER_ITEM

    # Economia líquida: tempo manual poupado menos o tempo que o robô levou
    # Se o robô levou algum tempo mas poupou a conferência manual, garante o tempo de triagem do analista
    saved_seconds = max(0.0, tempo_manual_estimado - duration)
    if saved_seconds == 0.0 and total_inspecionados > 0:
        # Pelo menos o tempo de triagem e diagnóstico que o analista não precisou fazer linha por linha
        saved_seconds = total_inspecionados * 25.0

    saved_hours = round(saved_seconds / 3600.0, 2)

    meta_json = json.dumps(metadata or {}, ensure_ascii=False)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO job_history (
                timestamp, job_id, job_name, duration_seconds, 
                items_processed, time_saved_hours, status, error_message, metadata
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            job_id,
            job_name,
            round(duration, 2),
            items,
            saved_hours,
            status,
            error_msg,
            meta_json
        ))
        conn.commit()

def _parse_filter_dates(start_date: str = None, end_date: str = None):
    """Auxiliar para converter filtros de string ISO YYYY-MM-DD em datetime."""
    from datetime import datetime
    dt_start = None
    dt_end = None
    if start_date:
        try:
            dt_start = datetime.strptime(start_date.strip(), "%Y-%m-%d").replace(hour=0, minute=0, second=0)
        except Exception:
            pass
    if end_date:
        try:
            dt_end = datetime.strptime(end_date.strip(), "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        except Exception:
            pass
    return dt_start, dt_end

def get_accumulated_kpis(start_date: str = None, end_date: str = None) -> Dict[str, Any]:
    """
    Retorna métricas consolidadas acumuladas para os cards do dashboard.
    Suporta filtro por período (start_date e end_date no formato YYYY-MM-DD).
    """
    init_db()
    from datetime import datetime
    dt_start, dt_end = _parse_filter_dates(start_date, end_date)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, items_processed, time_saved_hours, status FROM job_history")
        rows = cursor.fetchall()

        total_jobs = 0
        total_items = 0
        total_hours_saved = 0.0
        success_jobs = 0

        for row in rows:
            ts_str, items, saved_h, status = row
            # Validação do período
            if dt_start or dt_end:
                try:
                    # timestamp no banco: "DD/MM/YYYY HH:MM:SS"
                    dt_row = datetime.strptime(ts_str.strip(), "%d/%m/%Y %H:%M:%S")
                    if dt_start and dt_row < dt_start:
                        continue
                    if dt_end and dt_row > dt_end:
                        continue
                except Exception:
                    pass

            total_jobs += 1
            total_items += (items or 0)
            total_hours_saved += (saved_h or 0.0)
            if status == "SUCCESS":
                success_jobs += 1

        rate = round((success_jobs / total_jobs * 100), 1) if total_jobs > 0 else 100.0

        return {
            "total_jobs": total_jobs,
            "total_items": total_items,
            "time_saved_hours": round(total_hours_saved, 1),
            "success_rate": rate
        }

def fetch_recent_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Recupera os últimos registros de auditoria convertendo o payload metadata de volta para dict."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM job_history ORDER BY id DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("metadata"):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except:
                    pass
            result.append(d)
        return result

def get_last_runs_map() -> Dict[str, Dict[str, str]]:
    """Retorna um dicionário {job_id: {'last_run': timestamp, 'status': status}} com a última execução real de cada robô."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT job_id, timestamp, status 
            FROM job_history 
            WHERE id IN (SELECT MAX(id) FROM job_history GROUP BY job_id)
        """)
        rows = cursor.fetchall()
        return {
            row[0]: {"last_run": row[1], "status": row[2]}
            for row in rows
        }

def get_dashboard_chart_data(start_date: str = None, end_date: str = None) -> Dict[str, Any]:
    """
    Agrupa os dados reais do banco SQLite para alimentar os gráficos do Dashboard:
    1. Atividade temporal de execuções e itens dentro do período filtrado.
    2. Distribuição real por tipo/nome de robô no período.
    """
    init_db()
    from datetime import datetime, timedelta
    dt_start, dt_end = _parse_filter_dates(start_date, end_date)

    category_counts = {}
    days_map = {}
    day_labels = []

    if dt_start and dt_end and (dt_end - dt_start).days >= 0:
        # Se um período customizado foi definido, gera todos os dias daquele intervalo
        diff_days = min((dt_end - dt_start).days + 1, 62) # Limite seguro para não estourar eixo
        curr = dt_start
        for _ in range(diff_days):
            day_str = curr.strftime("%d/%m")
            if day_str not in day_labels:
                day_labels.append(day_str)
                days_map[day_str] = {"jobs": 0, "items": 0}
            curr += timedelta(days=1)
    else:
        # Padrão: últimos 7 dias
        today = datetime.now()
        for i in reversed(range(7)):
            d = today - timedelta(days=i)
            day_str = d.strftime("%d/%m")
            day_labels.append(day_str)
            days_map[day_str] = {"jobs": 0, "items": 0}

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp, items_processed, job_name, status FROM job_history")
        rows = cursor.fetchall()

        for row in rows:
            ts_str, items, job_name, status = row
            try:
                dt_row = datetime.strptime(ts_str.strip(), "%d/%m/%Y %H:%M:%S")
                # Filtro por período
                if dt_start and dt_row < dt_start:
                    continue
                if dt_end and dt_row > dt_end:
                    continue

                day_month = dt_row.strftime("%d/%m")
                if day_month in days_map:
                    days_map[day_month]["jobs"] += 1
                    days_map[day_month]["items"] += (items or 0)
                else:
                    # Caso o dia esteja no período mas não no mapa pré-alocado
                    day_labels.append(day_month)
                    days_map[day_month] = {"jobs": 1, "items": (items or 0)}

                # Distribuição por robô dentro do período
                cat = job_name or "Geral"
                category_counts[cat] = category_counts.get(cat, 0) + 1
            except Exception:
                pass

    jobs_data = [days_map.get(d, {}).get("jobs", 0) for d in day_labels]
    items_data = [days_map.get(d, {}).get("items", 0) for d in day_labels]

    dist_labels = list(category_counts.keys()) if category_counts else ["Nenhuma Execução"]
    dist_data = list(category_counts.values()) if category_counts else [0]

    return {
        "activity": {
            "labels": day_labels,
            "jobs": jobs_data,
            "items": items_data
        },
        "distribution": {
            "labels": dist_labels,
            "data": dist_data
        }
    }

# ============================================================
# Módulo Studio — persistência de fluxos (Etapa 1)
# ============================================================

def save_studio_flow(
    flow_id: str,
    name: str,
    graph: Dict[str, Any],
    group_name: str = None,
    transacao: str = None,
    schema_version: int = 1,
    origem: str = "proprio",
    note: str = None
) -> Dict[str, Any]:
    """
    Grava (insere ou atualiza) um fluxo e sempre acrescenta uma versão em
    studio_flow_versions — o append-only é o que permite voltar a uma versão que funcionava.
    """
    init_db()
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    graph_json = json.dumps(graph, ensure_ascii=False)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT flow_id, created_at FROM studio_flows WHERE flow_id = ?", (flow_id,))
        existing = cursor.fetchone()

        if existing:
            cursor.execute("""
                UPDATE studio_flows
                SET name = ?, group_name = ?, transacao = ?, graph_json = ?,
                    schema_version = ?, updated_at = ?
                WHERE flow_id = ?
            """, (name, group_name, transacao, graph_json, schema_version, now, flow_id))
        else:
            cursor.execute("""
                INSERT INTO studio_flows (
                    flow_id, name, group_name, transacao, graph_json,
                    schema_version, is_published, origem, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            """, (flow_id, name, group_name, transacao, graph_json, schema_version, origem, now, now))

        cursor.execute("""
            INSERT INTO studio_flow_versions (flow_id, graph_json, saved_at, note)
            VALUES (?, ?, ?, ?)
        """, (flow_id, graph_json, now, note))

        version_id = cursor.lastrowid
        conn.commit()

    return {"flow_id": flow_id, "updated_at": now, "version_id": version_id}


def get_studio_flow(flow_id: str) -> Dict[str, Any]:
    """Retorna o fluxo com o grafo já desserializado, ou None se não existir."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM studio_flows WHERE flow_id = ?", (flow_id,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        d["graph"] = json.loads(d.pop("graph_json"))
        return d


def list_studio_flows() -> List[Dict[str, Any]]:
    """Lista os fluxos sem o payload completo do grafo — só o resumo para telas de listagem."""
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT flow_id, name, group_name, transacao, schema_version,
                   is_published, origem, created_at, updated_at
            FROM studio_flows ORDER BY updated_at DESC
        """)
        return [dict(r) for r in cursor.fetchall()]


def set_studio_flow_published(flow_id: str, is_published: bool) -> Dict[str, Any]:
    """Alterna o flag de publicação. Quem decide SE pode publicar (grafo válido, sem
    needs_review, RPA_BUSY) é a bridge — esta função só grava o que já foi decidido."""
    init_db()
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE studio_flows SET is_published = ?, updated_at = ? WHERE flow_id = ?",
            (1 if is_published else 0, now, flow_id)
        )
        if cursor.rowcount == 0:
            raise ValueError(f"Fluxo '{flow_id}' não encontrado.")
        conn.commit()
    return {"flow_id": flow_id, "is_published": is_published, "updated_at": now}


def list_published_flows() -> List[Dict[str, Any]]:
    """
    Fluxos publicados, no MESMO shape de AVAILABLE_JOBS (core/rpa/runner.py) — é isso que
    permite RPARunner.get_catalog() devolver AVAILABLE_JOBS + list_published_flows() sem a
    Central de Robôs mudar uma linha.
    """
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM studio_flows WHERE is_published = 1 ORDER BY updated_at DESC")
        rows = cursor.fetchall()

    result = []
    for row in rows:
        d = dict(row)
        graph = json.loads(d["graph_json"])
        requires_file = any(n.get("type") == "data.excel_read" for n in graph.get("nodes", []))
        result.append({
            "id": d["flow_id"],
            "group": d["group_name"] or graph.get("group", "Studio"),
            "order": None,
            "name": d["name"],
            "type": f"Studio / {d['transacao'] or 'Grafo'}",
            "requires_file": requires_file,
            "description": graph.get("description") or "Fluxo criado no Studio pelo próprio usuário.",
            "usage_steps": graph.get("usage_steps") or [
                "Certifique-se de estar com o SAP Logon aberto e conectado na sessão desejada.",
                "Clique em [Iniciar] para o Mirandinha executar o fluxo montado no Studio.",
            ],
            "last_run": "Nunca",
            "status": "idle",
            "is_studio_flow": True,
        })
    return result

