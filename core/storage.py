"""
Gerenciador de persistência local SQLite para histórico, auditoria e metadados detalhados do Mirandinha.
Permite armazenar métricas agregadas e payload JSON de metadados operacionais para cada execução.

Convenções:
- `timestamp` é gravado em ISO 8601 (ordenável cronologicamente por string).
- Execuções de simulação (`is_simulated = 1`) são registradas para rastreabilidade,
  mas NUNCA entram nos KPIs consolidados nem nas séries do dashboard.
"""
import sqlite3
import os
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "mirandinha_history.db")

# Tempo médio estimado que um operador humano leva por item no SAP (segundos)
MANUAL_SECONDS_PER_ITEM = 45.0


def _fmt_display(iso_ts: str) -> str:
    """Converte ISO 8601 para exibição amigável dd/mm/YYYY HH:MM:SS."""
    try:
        return datetime.fromisoformat(iso_ts).strftime("%d/%m/%Y %H:%M:%S")
    except (ValueError, TypeError):
        return iso_ts or ""


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
                metadata TEXT,
                is_simulated INTEGER DEFAULT 0
            )
        """)
        # Migração automática de colunas caso o banco já existisse
        cursor.execute("PRAGMA table_info(job_history)")
        columns = [row[1] for row in cursor.fetchall()]
        if "time_saved_hours" not in columns:
            cursor.execute("ALTER TABLE job_history ADD COLUMN time_saved_hours REAL DEFAULT 0.0")
        if "metadata" not in columns:
            cursor.execute("ALTER TABLE job_history ADD COLUMN metadata TEXT")
        if "is_simulated" not in columns:
            cursor.execute("ALTER TABLE job_history ADD COLUMN is_simulated INTEGER DEFAULT 0")
        conn.commit()


def record_job_execution(
    job_id: str,
    job_name: str,
    duration: float,
    items: int,
    status: str,
    error_msg: str = None,
    metadata: Dict[str, Any] = None,
    is_simulated: bool = False
):
    """
    Persiste a execução e os metadados ricos da transação (ex: transação SAP, PEPs, itens zerados).

    `is_simulated=True` marca execuções geradas por robôs ainda não implementados de forma real;
    esses registros ficam disponíveis para auditoria mas são excluídos dos indicadores.
    """
    init_db()
    saved_seconds = max(0.0, (items * MANUAL_SECONDS_PER_ITEM) - duration)
    saved_hours = round(saved_seconds / 3600.0, 2)

    meta_json = json.dumps(metadata or {}, ensure_ascii=False)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO job_history (
                timestamp, job_id, job_name, duration_seconds,
                items_processed, time_saved_hours, status, error_message, metadata, is_simulated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datetime.now().isoformat(timespec="seconds"),
            job_id,
            job_name,
            round(duration, 2),
            items,
            saved_hours,
            status,
            error_msg,
            meta_json,
            1 if is_simulated else 0
        ))
        conn.commit()


def get_accumulated_kpis() -> Dict[str, Any]:
    """
    Retorna métricas consolidadas acumuladas para os cards do dashboard.
    Considera exclusivamente execuções reais (is_simulated = 0).
    """
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total_jobs,
                COALESCE(SUM(items_processed), 0) as total_items,
                COALESCE(SUM(time_saved_hours), 0) as total_time_saved,
                COALESCE(SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END), 0) as success_jobs
            FROM job_history
            WHERE is_simulated = 0
        """)
        row = cursor.fetchone()
        total_jobs = row[0] or 0
        total_items = row[1] or 0
        total_hours_saved = round(row[2] or 0.0, 1)
        success_jobs = row[3] or 0

        rate = round((success_jobs / total_jobs * 100), 1) if total_jobs > 0 else None

        return {
            "total_jobs": total_jobs,
            "total_items": total_items,
            "time_saved_hours": total_hours_saved,
            "success_rate": rate,
            "has_data": total_jobs > 0
        }


def get_dashboard_series() -> Dict[str, Any]:
    """
    Séries reais para os gráficos do dashboard (últimos 7 dias), execuções reais apenas.

    Retorna:
      - week: labels dd/mm + contagem de execuções e itens por dia
      - distribution: distribuição de execuções por processo (job_name)
    """
    init_db()
    today = datetime.now().date()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    day_keys = [d.isoformat() for d in days]
    labels = [d.strftime("%d/%m") for d in days]

    counts = {k: 0 for k in day_keys}
    items = {k: 0 for k in day_keys}
    distribution: Dict[str, int] = {}

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT substr(timestamp, 1, 10) as day, job_name, items_processed
            FROM job_history
            WHERE is_simulated = 0
        """)
        for day, job_name, n_items in cursor.fetchall():
            if day in counts:
                counts[day] += 1
                items[day] += (n_items or 0)
            distribution[job_name] = distribution.get(job_name, 0) + 1

    return {
        "has_data": any(counts.values()),
        "week": {
            "labels": labels,
            "executions": [counts[k] for k in day_keys],
            "items": [items[k] for k in day_keys]
        },
        "distribution": {
            "labels": list(distribution.keys()),
            "values": list(distribution.values())
        }
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
            d["timestamp_fmt"] = _fmt_display(d.get("timestamp", ""))
            d["is_simulated"] = bool(d.get("is_simulated", 0))
            if d.get("metadata"):
                try:
                    d["metadata"] = json.loads(d["metadata"])
                except (ValueError, TypeError):
                    pass
            result.append(d)
        return result
