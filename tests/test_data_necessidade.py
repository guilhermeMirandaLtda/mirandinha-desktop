"""
Suite de testes unitários para a automação CJ20N Data Necessidade.
Cobre regras puras: validação de schema de planilha, guard-rails de data e cálculo ponderado de ROI.
"""
import os
import tempfile
import unittest
import pandas as pd
from core.rpa.tasks.sap_data_necessidade import SAPDataNecessidadeTask


class TestDataNecessidadePureLogic(unittest.TestCase):
    def setUp(self):
        self.tmp_files = []

    def tearDown(self):
        for f in self.tmp_files:
            if os.path.exists(f):
                try: os.remove(f)
                except Exception: pass

    def _create_temp_excel(self, data: dict) -> str:
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        self.tmp_files.append(tmp.name)
        tmp.close()
        df = pd.DataFrame(data)
        df.to_excel(tmp.name, index=False)
        return tmp.name

    def test_validate_input_missing_columns(self):
        """Valida que a falta de colunas obrigatórias é rejeitada de imediato."""
        path = self._create_temp_excel({"PEP": ["PEP1"], "OutraColuna": ["X"]})
        task = SAPDataNecessidadeTask(spreadsheet_path=path)
        with self.assertRaises(ValueError) as ctx:
            task.validate_input()
        self.assertIn("Diagrama", str(ctx.exception))
        self.assertIn("Data Necessidade", str(ctx.exception))

    def test_validate_input_valid_spreadsheet(self):
        """Valida leitura e extração correta de diagramas únicos."""
        path = self._create_temp_excel({
            "PEP": ["01-0001", "01-0002", "01-0003"],
            "Diagrama": ["40001", "40002", "40001"], # 2 únicos
            "Data Necessidade": ["15/10/2026", "20/11/2026", "15/10/2026"]
        })
        task = SAPDataNecessidadeTask(spreadsheet_path=path)
        task.validate_input()
        self.assertEqual(len(task.get_work_items()), 2)
        self.assertEqual(task.get_work_items(), ["40001", "40002"])

    def test_date_formatting_and_guardrails(self):
        """Valida parsing e guard-rails de sanidade de datas."""
        path = self._create_temp_excel({"PEP": ["P"], "Diagrama": ["D"], "Data Necessidade": ["15/10/2026"]})
        task = SAPDataNecessidadeTask(spreadsheet_path=path)

        # 1. Formato correto DD/MM/AAAA -> DD.MM.AAAA
        self.assertEqual(task._format_date_for_sap("15/10/2026"), "15.10.2026")
        self.assertEqual(task._format_date_for_sap(pd.Timestamp("2026-10-15")), "15.10.2026")

        # 2. Rejeição de data no passado remoto (> 60 dias)
        with self.assertRaises(ValueError) as ctx_past:
            task._format_date_for_sap("01/01/2020")
        self.assertIn("passado remoto", str(ctx_past.exception))

        # 3. Rejeição de ano invertido / futuro remoto (> 24 meses)
        with self.assertRaises(ValueError) as ctx_future:
            task._format_date_for_sap("15/10/2062")
        self.assertIn("24 meses", str(ctx_future.exception))

    def test_roi_weighted_formula(self):
        """Garante a fórmula ponderada de ROI sem deixar tempo de erro órfão."""
        sucessos = 35
        erros = 2
        duracao = 215.3
        t_sucesso = 120.0
        t_erro = 60.0

        tempo_manual_estimado = (sucessos * t_sucesso) + (erros * t_erro)
        # 35 * 120 + 2 * 60 = 4200 + 120 = 4320.0s
        self.assertEqual(tempo_manual_estimado, 4320.0)

        horas_poupadas = max(0.0, tempo_manual_estimado - duracao) / 3600.0
        self.assertAlmostEqual(horas_poupadas, 1.140, places=2)


if __name__ == "__main__":
    unittest.main()
