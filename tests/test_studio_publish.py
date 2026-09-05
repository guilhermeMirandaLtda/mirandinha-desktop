"""
Testes da Etapa 5 — o portão de publicação e o caminho de um fluxo publicado até a
Central de Robôs. Cobre as três camadas: storage (flag + shape do catálogo),
RPARunner (get_catalog() mesclado, execute_job_sync() delegando pra fluxo) e bridge
(studio_publish_flow — grafo inválido / nó pendente / RPA_BUSY / não encontrado).
"""
import unittest
from unittest.mock import patch

from core.storage import (
    save_studio_flow, set_studio_flow_published, list_published_flows, get_studio_flow,
)
from core.rpa.runner import RPARunner, AVAILABLE_JOBS
from core.bridge import MirandinhaBridge


def _flow_valido(flow_id="flow_publish_teste"):
    return {
        "flow_id": flow_id, "name": "Fluxo publicável", "group": "Materiais", "transacao": "CN52N",
        "variables": {"itens": [1]},
        "nodes": [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "flow.foreach", "params": {"source": "{{itens}}", "item_var": "i"}},
            {"id": "n3", "type": "data.log", "params": {"message": "item {{i}}"}, "on_error": "continue"},
            {"id": "n4", "type": "flow.end", "params": {}},
        ],
        "edges": [
            {"id": "e1", "from": "n1", "to": "n2", "port": "out"},
            {"id": "e2", "from": "n2", "to": "n3", "port": "loop"},
            {"id": "e3", "from": "n2", "to": "n4", "port": "done"},
        ],
    }


def _flow_invalido(flow_id="flow_publish_invalido"):
    graph = _flow_valido(flow_id)
    del graph["nodes"][2]["on_error"]  # data.log sem on_error -> erro de validação
    return graph


class TestStorageListPublishedFlows(unittest.TestCase):
    def test_fluxo_nao_publicado_nao_aparece(self):
        flow_id = "flow_storage_nao_publicado"
        save_studio_flow(flow_id, "Rascunho", _flow_valido(flow_id))
        ids = [f["id"] for f in list_published_flows()]
        self.assertNotIn(flow_id, ids)

    def test_fluxo_publicado_aparece_no_shape_do_catalogo(self):
        flow_id = "flow_storage_publicado"
        save_studio_flow(flow_id, "Publicado de teste", _flow_valido(flow_id), transacao="CN52N", group_name="Materiais")
        set_studio_flow_published(flow_id, True)

        published = {f["id"]: f for f in list_published_flows()}
        self.assertIn(flow_id, published)
        entry = published[flow_id]
        for key in ("id", "group", "name", "type", "requires_file", "description", "usage_steps", "last_run", "status"):
            self.assertIn(key, entry)
        self.assertEqual(entry["group"], "Materiais")
        self.assertTrue(entry["is_studio_flow"])

    def test_requires_file_detecta_data_excel_read(self):
        flow_id = "flow_storage_requires_file"
        graph = _flow_valido(flow_id)
        graph["nodes"].insert(1, {
            "id": "n_read", "type": "data.excel_read",
            "params": {"path": "{{spreadsheet_path}}", "columns": [{"name": "PEP"}], "output_var": "linhas"},
            "on_error": "abort",
        })
        graph["edges"].insert(0, {"id": "e0", "from": "n1", "to": "n_read", "port": "out"})
        graph["edges"][1] = {"id": "e1", "from": "n_read", "to": "n2", "port": "out"}
        save_studio_flow(flow_id, "Com planilha", graph)
        set_studio_flow_published(flow_id, True)

        entry = next(f for f in list_published_flows() if f["id"] == flow_id)
        self.assertTrue(entry["requires_file"])

    def test_despublicar_tira_da_lista(self):
        flow_id = "flow_storage_despublicar"
        save_studio_flow(flow_id, "Vai e volta", _flow_valido(flow_id))
        set_studio_flow_published(flow_id, True)
        self.assertIn(flow_id, [f["id"] for f in list_published_flows()])
        set_studio_flow_published(flow_id, False)
        self.assertNotIn(flow_id, [f["id"] for f in list_published_flows()])

    def test_flow_id_inexistente_levanta_erro_claro(self):
        with self.assertRaises(ValueError):
            set_studio_flow_published("flow_que_nunca_existiu", True)


class TestRunnerCatalogEExecucao(unittest.TestCase):
    def test_get_catalog_mescla_jobs_nativos_e_fluxos_publicados(self):
        flow_id = "flow_runner_catalog"
        save_studio_flow(flow_id, "No catálogo", _flow_valido(flow_id))
        set_studio_flow_published(flow_id, True)

        runner = RPARunner()
        catalog = runner.get_catalog()
        ids = [j["id"] for j in catalog]

        self.assertIn(flow_id, ids)
        for native in AVAILABLE_JOBS:
            self.assertIn(native["id"], ids)

    @patch("core.rpa.runner.record_job_execution")
    def test_execute_job_sync_roda_fluxo_publicado(self, mock_record):
        flow_id = "flow_runner_exec_publicado"
        save_studio_flow(flow_id, "Roda pela central", _flow_valido(flow_id))
        set_studio_flow_published(flow_id, True)

        runner = RPARunner()
        result = runner.execute_job_sync(flow_id)
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["job_id"], flow_id)

    def test_execute_job_sync_recusa_fluxo_nao_publicado(self):
        flow_id = "flow_runner_exec_rascunho"
        save_studio_flow(flow_id, "Ainda rascunho", _flow_valido(flow_id))
        # não publica de propósito

        runner = RPARunner()
        with self.assertRaises(ValueError) as ctx:
            runner.execute_job_sync(flow_id)
        self.assertIn("publicado", str(ctx.exception))

    def test_execute_job_sync_flow_inexistente(self):
        runner = RPARunner()
        with self.assertRaises(ValueError) as ctx:
            runner.execute_job_sync("flow_isso_nao_existe_nunca")
        self.assertIn("não encontrado", str(ctx.exception))


class TestBridgePublishFlow(unittest.TestCase):
    def test_publica_um_fluxo_valido(self):
        bridge = MirandinhaBridge()
        flow_id = "flow_bridge_publish_ok"
        bridge.studio_save_flow(_flow_valido(flow_id))

        res = bridge.studio_publish_flow(flow_id, True)
        self.assertTrue(res["success"])
        self.assertTrue(res["data"]["is_published"])

        catalog_res = bridge.get_available_jobs()
        self.assertTrue(any(j["id"] == flow_id for j in catalog_res["data"]))

    def test_recusa_publicar_grafo_invalido(self):
        bridge = MirandinhaBridge()
        flow_id = "flow_bridge_publish_invalido"
        bridge.studio_save_flow(_flow_invalido(flow_id))

        res = bridge.studio_publish_flow(flow_id, True)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "FLOW_INVALID")

        published = get_studio_flow(flow_id)
        self.assertEqual(published["is_published"], 0)

    def test_recusa_publicar_com_no_pendente_de_revisao(self):
        bridge = MirandinhaBridge()
        flow_id = "flow_bridge_publish_needs_review"
        graph = _flow_valido(flow_id)
        graph["nodes"][2]["needs_review"] = True
        bridge.studio_save_flow(graph)

        res = bridge.studio_publish_flow(flow_id, True)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "FLOW_INVALID")
        self.assertIn("needs_review_node_ids", res["error"]["details"])

    def test_despublicar_nao_exige_validade(self):
        bridge = MirandinhaBridge()
        flow_id = "flow_bridge_unpublish"
        bridge.studio_save_flow(_flow_valido(flow_id))
        bridge.studio_publish_flow(flow_id, True)

        res = bridge.studio_publish_flow(flow_id, False)
        self.assertTrue(res["success"])
        self.assertFalse(res["data"]["is_published"])

    def test_recusa_com_rpa_ocupado(self):
        bridge = MirandinhaBridge()
        flow_id = "flow_bridge_publish_busy"
        bridge.studio_save_flow(_flow_valido(flow_id))
        bridge.rpa_runner._is_running = True

        res = bridge.studio_publish_flow(flow_id, True)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "RPA_BUSY")

    def test_fluxo_inexistente(self):
        bridge = MirandinhaBridge()
        res = bridge.studio_publish_flow("flow_nao_existe_no_banco", True)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "FLOW_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
