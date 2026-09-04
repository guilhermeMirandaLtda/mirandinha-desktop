"""
Motor analítico para processamento avançado de dados com Pandas e Estatística.

Detecção de anomalias: método IQR (Tukey fences) — robusto, sem premissa de normalidade.
Um ponto é anômalo quando fica abaixo de Q1 - 1.5*IQR ou acima de Q3 + 1.5*IQR.
"""
import pandas as pd
import numpy as np
import os
from typing import Dict, Any, Tuple


def _iqr_outlier_mask(series: pd.Series) -> pd.Series:
    """Retorna uma máscara booleana marcando os outliers da série pelo método IQR."""
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) < 4:
        return pd.Series([False] * len(s), index=s.index)
    q1 = s.quantile(0.25)
    q3 = s.quantile(0.75)
    iqr = q3 - q1
    if iqr == 0:
        return pd.Series([False] * len(s), index=s.index)
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return (s < lower) | (s > upper)


class AnalyticsEngine:
    def __init__(self):
        pass

    def generate_demo_insights(self) -> Dict[str, Any]:
        """Gera um conjunto sintético e roda a mesma análise estatística aplicada a arquivos reais."""
        rng = np.random.default_rng(42)
        base = rng.normal(loc=150, scale=40, size=1000)
        injected = rng.uniform(low=280, high=400, size=15)
        all_values = np.concatenate([base, injected])

        series = pd.Series(all_values)
        mask = _iqr_outlier_mask(series)
        detected = int(mask.sum())

        scatter_data = [
            {"x": round(float(rng.uniform(10, 100)), 1), "y": round(float(v), 1)}
            for v in all_values[:40]
        ]

        return {
            "source": "demo",
            "total_rows": len(all_values),
            "total_anomalies": detected,
            "mean_value": round(float(series.mean()), 2),
            "median_value": round(float(series.median()), 2),
            "std_dev": round(float(series.std()), 2),
            "trend": {
                "labels": ["Sem 1", "Sem 2", "Sem 3", "Sem 4", "Sem 5", "Sem 6", "Sem 7", "Sem 8"],
                "values": [120, 145, 138, 162, 185, 179, 210, 235]
            },
            "scatter": scatter_data
        }

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """Lê arquivo CSV ou Excel e extrai estatísticas automáticas + detecção de anomalias (IQR)."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Arquivo não localizado: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".csv":
            df = pd.read_csv(file_path)
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(file_path)
        else:
            raise ValueError(f"Formato não suportado: {ext or 'desconhecido'}. Use CSV ou Excel.")

        numeric_cols = list(df.select_dtypes(include=[np.number]).columns)
        total_rows = len(df)

        mean_value = median_value = std_dev = 0.0
        total_anomalies = 0
        primary_col = None

        if numeric_cols:
            primary_col = numeric_cols[0]
            col = pd.to_numeric(df[primary_col], errors="coerce").dropna()
            if len(col) > 0:
                mean_value = round(float(col.mean()), 2)
                median_value = round(float(col.median()), 2)
                std_dev = round(float(col.std()), 2) if len(col) > 1 else 0.0
                total_anomalies = int(_iqr_outlier_mask(col).sum())

        scatter_data = []
        if len(numeric_cols) >= 2:
            sample = df[[numeric_cols[0], numeric_cols[1]]].apply(
                pd.to_numeric, errors="coerce"
            ).dropna().head(50)
            scatter_data = [
                {"x": round(float(r[0]), 2), "y": round(float(r[1]), 2)} for r in sample.values
            ]

        trend_values = []
        if primary_col is not None:
            trend_values = [
                round(float(v), 2)
                for v in pd.to_numeric(df[primary_col], errors="coerce").dropna().head(8)
            ]

        return {
            "source": "file",
            "file_name": os.path.basename(file_path),
            "total_rows": total_rows,
            "numeric_columns": len(numeric_cols),
            "analyzed_column": str(primary_col) if primary_col is not None else None,
            "total_anomalies": total_anomalies,
            "mean_value": mean_value,
            "median_value": median_value,
            "std_dev": std_dev,
            "trend": {
                "labels": [f"Lote {i + 1}" for i in range(len(trend_values) or 0)],
                "values": trend_values
            },
            "scatter": scatter_data
        }
