"""
Testes dos métodos studio_* da bridge (Etapa 3). Sem janela pywebview (self._window fica
None), então as chamadas de evaluate_js viram no-op — o que já é o comportamento real da
bridge quando não há frontend anexado. Cobre o contrato normativo {success, data, error}.
"""
import unittest

from core.bridge import MirandinhaBridge


class TestStudioNodeCatalog(unittest.TestCase):
    def test_retorna_catalogo_completo(self):
        bridge = MirandinhaBridge()
        res = bridge.studio_node_catalog()
        self.assertTrue(res["success"])
        self.assertIn("flow.start", res["data"])
        self.assertIn("sap.connect", res["data"])


class TestStudioScreenPacks(unittest.TestCase):
    def test_lista_os_quatro_packs(self):
        bridge = MirandinhaBridge()
        res = bridge.studio_screen_packs()
        self.assertTrue(res["success"])
        packs = {p["pack"] for p in res["data"]}
        self.assertEqual(packs, {"cn52n", "cj20n", "me52n", "mb22"})


class TestStudioValidateFlow(unittest.TestCase):
    def test_grafo_valido(self):
        bridge = MirandinhaBridge()
        graph = {
            "nodes": [
                {"id": "n1", "type": "flow.start", "params": {}},
                {"id": "n2", "type": "flow.end", "params": {}},
            ],
            "edges": [{"id": "e1", "from": "n1", "to": "n2", "port": "out"}],
        }
        res = bridge.studio_validate_flow(graph)
        self.assertTrue(res["success"])
        self.assertTrue(res["data"]["ok"])

    def test_grafo_invalido_ainda_retorna_success_com_ok_false(self):
        """studio_validate_flow nunca vira error_response por um grafo ruim — ok=False é
        um resultado válido da chamada, não uma falha da bridge."""
        bridge = MirandinhaBridge()
        res = bridge.studio_validate_flow({"nodes": [], "edges": []})
        self.assertTrue(res["success"])
        self.assertFalse(res["data"]["ok"])


class TestStudioSamples(unittest.TestCase):
    def test_lista_os_tres_exemplos(self):
        bridge = MirandinhaBridge()
        res = bridge.studio_list_samples()
        self.assertTrue(res["success"])
        files = {s["file"] for s in res["data"]}
        self.assertEqual(files, {
            "cn52n_grid_read.json", "cn52n_zerar_compromisso.json", "cj20n_data_necessidade.json",
        })

    def test_carrega_um_exemplo_pelo_nome(self):
        bridge = MirandinhaBridge()
        res = bridge.studio_load_sample("cn52n_zerar_compromisso.json")
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["flow_id"], "flow_cn52n_zerar_compromisso")

    def test_exemplo_inexistente_retorna_erro_claro(self):
        bridge = MirandinhaBridge()
        res = bridge.studio_load_sample("nao_existe.json")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "SAMPLE_NOT_FOUND")

    def test_nao_atravessa_diretorio(self):
        """filename passa por os.path.basename() — '../../secreto.json' vira 'secreto.json'."""
        bridge = MirandinhaBridge()
        res = bridge.studio_load_sample("../../../windows/system.ini")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "SAMPLE_NOT_FOUND")


class TestStudioSaveFlow(unittest.TestCase):
    def _graph(self, flow_id="flow_teste_bridge"):
        return {
            "flow_id": flow_id, "name": "Fluxo de teste", "group": "Studio", "transacao": "AUTO",
            "nodes": [{"id": "n1", "type": "flow.start", "params": {}}],
            "edges": [],
        }

    def test_recusa_sem_flow_id(self):
        bridge = MirandinhaBridge()
        graph = self._graph()
        del graph["flow_id"]
        res = bridge.studio_save_flow(graph)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "FLOW_INVALID")

    def test_recusa_com_rpa_ocupado(self):
        bridge = MirandinhaBridge()
        bridge.rpa_runner._is_running = True
        res = bridge.studio_save_flow(self._graph())
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "RPA_BUSY")

    def test_salva_com_sucesso(self):
        bridge = MirandinhaBridge()
        res = bridge.studio_save_flow(self._graph("flow_bridge_save_ok"))
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["flow_id"], "flow_bridge_save_ok")

        loaded = bridge.studio_get_flow("flow_bridge_save_ok")
        self.assertTrue(loaded["success"])
        self.assertEqual(loaded["data"]["name"], "Fluxo de teste")


class TestStudioGetFlow(unittest.TestCase):
    def test_fluxo_inexistente_retorna_erro_claro(self):
        bridge = MirandinhaBridge()
        res = bridge.studio_get_flow("flow_que_nao_existe_nunca")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "FLOW_NOT_FOUND")


class TestStudioRunFlow(unittest.TestCase):
    def test_roda_um_fluxo_simples_sem_sap(self):
        bridge = MirandinhaBridge()
        graph = {
            "flow_id": "flow_bridge_run", "name": "Fluxo simples", "variables": {},
            "nodes": [
                {"id": "n1", "type": "flow.start", "params": {}},
                {"id": "n2", "type": "data.log", "params": {"message": "oi"}, "on_error": "continue"},
                {"id": "n3", "type": "flow.end", "params": {}},
            ],
            "edges": [
                {"id": "e1", "from": "n1", "to": "n2", "port": "out"},
                {"id": "e2", "from": "n2", "to": "n3", "port": "out"},
            ],
        }
        res = bridge.studio_run_flow(graph)
        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["status"], "SUCCESS")

    def test_grafo_invalido_retorna_execution_error(self):
        bridge = MirandinhaBridge()
        res = bridge.studio_run_flow({"nodes": [], "edges": []})
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "STUDIO_EXECUTION_ERROR")


if __name__ == "__main__":
    unittest.main()
