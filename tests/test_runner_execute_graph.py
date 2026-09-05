"""
Testes de RPARunner.execute_graph_sync() (Etapa 3) — o caminho que o botão [Executar]
do canvas usa: mesma guarda de concorrência, mesmo shape de retorno e mesma gravação em
job_history de execute_job_sync(), mas para um grafo em vez de um job_id do catálogo.
"""
import unittest
from unittest.mock import patch

from core.rpa.runner import RPARunner
from tests._fake_sap import FakeSapGuiSession


def _graph_simples():
    return {
        "schema_version": 1, "flow_id": "flow_runner_teste", "name": "Fluxo do runner",
        "transacao": "AUTO", "group": "Studio",
        "variables": {"itens": [1, 2]},
        "nodes": [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "flow.foreach", "params": {"source": "{{itens}}", "item_var": "i"}},
            {"id": "n3", "type": "data.log", "params": {"level": "INFO", "message": "item {{i}}"}, "on_error": "continue"},
            {"id": "n4", "type": "flow.end", "params": {}},
        ],
        "edges": [
            {"id": "e1", "from": "n1", "to": "n2", "port": "out"},
            {"id": "e2", "from": "n2", "to": "n3", "port": "loop"},
            {"id": "e3", "from": "n2", "to": "n4", "port": "done"},
        ],
    }


class TestExecuteGraphSync(unittest.TestCase):
    @patch("core.rpa.runner.record_job_execution")
    def test_roda_o_grafo_e_grava_em_job_history(self, mock_record):
        runner = RPARunner()
        result = runner.execute_graph_sync(_graph_simples())

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["job_id"], "flow_runner_teste")
        self.assertFalse(runner._is_running)
        mock_record.assert_called_once()
        args, kwargs = mock_record.call_args
        self.assertEqual(args[0], "flow_runner_teste")
        self.assertEqual(kwargs["metadata"]["origem"], "studio")
        self.assertEqual(kwargs["metadata"]["transacao"], "AUTO")

    def test_recusa_rodar_com_outro_job_em_execucao(self):
        runner = RPARunner()
        runner._is_running = True
        with self.assertRaises(RuntimeError) as ctx:
            runner.execute_graph_sync(_graph_simples())
        self.assertIn("execução", str(ctx.exception))

    @patch("core.rpa.runner.record_job_execution")
    def test_trace_callback_e_repassado_ao_graphtask(self, mock_record):
        events = []
        runner = RPARunner(trace_callback=events.append)
        runner.execute_graph_sync(_graph_simples())
        self.assertTrue(any(e["type"] == "node" for e in events))

    @patch("core.rpa.runner.record_job_execution")
    def test_grafo_com_sap_roda_via_fake_session(self, mock_record):
        from core.studio.screen_library import resolve_candidates
        graph = {
            "schema_version": 1, "flow_id": "flow_runner_sap", "name": "Fluxo com SAP",
            "transacao": "CN52N", "group": "Materiais", "variables": {},
            "nodes": [
                {"id": "n1", "type": "flow.start", "params": {}},
                {"id": "n2", "type": "sap.connect", "params": {}, "on_error": "abort"},
                {"id": "n3", "type": "flow.end", "params": {}},
            ],
            "edges": [
                {"id": "e1", "from": "n1", "to": "n2", "port": "out"},
                {"id": "e2", "from": "n2", "to": "n3", "port": "out"},
            ],
        }

        runner = RPARunner()

        # Monkeypatch no nível da classe SapSession pra não tocar win32com real durante
        # o run(): equivalente ao que os outros testes fazem por instância, mas aqui a
        # instância só existe dentro de execute_graph_sync().
        from core.rpa.sap_session import SapSession
        original_connect = SapSession.connect
        SapSession.connect = lambda self: setattr(self, "session", FakeSapGuiSession({})) or self.session
        try:
            result = runner.execute_graph_sync(graph)
        finally:
            SapSession.connect = original_connect

        self.assertEqual(result["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
