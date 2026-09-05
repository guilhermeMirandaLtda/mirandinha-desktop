"""
Testes unitários para as automações Concluir Requisições (ME52N) e Eliminar Reserva (MB22).
"""
import os
import tempfile
import unittest
import pandas as pd
from core.rpa.tasks.sap_eliminar_reserva import SAPEliminarReservaTask
from core.rpa.tasks.sap_concluir_requisicoes import SAPConcluirRequisicoesTask


class TestNovosRobosPureLogic(unittest.TestCase):
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

    def test_eliminar_reserva_validation_success(self):
        """Valida leitura de planilha com colunas Reserva e Item."""
        path = self._create_temp_excel({
            "Reserva": ["0008541230", "0008541231"],
            "Item": ["1", "2"]
        })
        task = SAPEliminarReservaTask(spreadsheet_path=path)
        task.validate_input()
        items = task.get_work_items()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["reserva"], "0008541230")
        self.assertEqual(items[0]["item"], "1")

    def test_eliminar_reserva_missing_columns(self):
        """Garante erro quando faltam colunas obrigatórias na Eliminar Reserva."""
        path = self._create_temp_excel({"Outra": ["123"]})
        task = SAPEliminarReservaTask(spreadsheet_path=path)
        with self.assertRaises(ValueError) as ctx:
            task.validate_input()
        self.assertIn("Reserva", str(ctx.exception))

    def test_concluir_requisicoes_validation_success(self):
        """Valida leitura de planilha com colunas Requisicao e Item."""
        path = self._create_temp_excel({
            "Requisicao": ["10012345", "10012346"],
            "Item": ["10", "20"]
        })
        task = SAPConcluirRequisicoesTask(spreadsheet_path=path)
        task.validate_input()
        items = task.get_work_items()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["requisicao"], "10012345")
        self.assertEqual(items[0]["item"], "10")

    def test_concluir_requisicoes_missing_col(self):
        """Garante erro quando falta coluna Requisicao."""
        path = self._create_temp_excel({"Material": ["12345"]})
        task = SAPConcluirRequisicoesTask(spreadsheet_path=path)
        with self.assertRaises(ValueError) as ctx:
            task.validate_input()
        self.assertIn("Requisicao", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
