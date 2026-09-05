"""
Testes da Etapa 6 — compartilhamento. Cobre as três camadas: screen_library (bundle
auto-contido, instalação de packs sem sobrescrever o local), summary (o resumo que o
portão de importação mostra) e bridge (studio_inspect_mirflow / studio_import_mirflow —
o portão de fato: nunca chega publicado).
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.studio.screen_library import (
    list_referenced_packs, export_bundle, import_bundle_packs, _SCREENS_DIR,
)
from core.studio.summary import summarize_flow
from core.bridge import MirandinhaBridge
from core.storage import get_studio_flow, save_studio_flow, set_studio_flow_published


def _load_sample(name):
    path = Path(__file__).resolve().parent.parent / "core" / "studio" / "samples" / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class TestListReferencedPacks(unittest.TestCase):
    def test_encontra_o_pack_cn52n_no_zerar_compromisso(self):
        graph = _load_sample("cn52n_zerar_compromisso.json")
        self.assertEqual(list_referenced_packs(graph), ["cn52n"])

    def test_grafo_sem_referencia_de_pack_retorna_vazio(self):
        graph = {"nodes": [{"id": "n1", "type": "flow.start", "params": {}}]}
        self.assertEqual(list_referenced_packs(graph), [])

    def test_nao_confunde_dict_qualquer_com_referencia_de_pack(self):
        graph = {"nodes": [{"id": "n1", "type": "data.log", "params": {"details": {"pack": 123, "ref": None}}}]}
        self.assertEqual(list_referenced_packs(graph), [])


class TestExportBundle(unittest.TestCase):
    def test_bundle_contem_grafo_e_pack_referenciado_por_inteiro(self):
        graph = _load_sample("cn52n_zerar_compromisso.json")
        bundle = export_bundle(graph)

        self.assertEqual(bundle["mirflow_version"], 1)
        self.assertIn("exported_at", bundle)
        self.assertEqual(bundle["graph"]["flow_id"], graph["flow_id"])
        self.assertIn("cn52n", bundle["packs"])
        self.assertIn("elementos", bundle["packs"]["cn52n"])
        self.assertIn("grid_alv", bundle["packs"]["cn52n"]["elementos"])

    def test_pack_referenciado_mas_nao_instalado_e_simplesmente_omitido(self):
        graph = {
            "nodes": [{"id": "n1", "type": "sap.press", "params": {"target": {"pack": "sap_fantasma", "ref": "x"}}}]
        }
        bundle = export_bundle(graph)
        self.assertEqual(bundle["packs"], {})


class TestImportBundlePacks(unittest.TestCase):
    def test_instala_pack_novo(self):
        fake_pack_name = "pack_teste_import_novo"
        fake_pack_path = _SCREENS_DIR / f"{fake_pack_name}.json"
        self.addCleanup(lambda: fake_pack_path.unlink(missing_ok=True))

        bundle = {"packs": {fake_pack_name: {"pack": fake_pack_name, "elementos": {}}}}
        installed = import_bundle_packs(bundle)

        self.assertEqual(installed, [fake_pack_name])
        self.assertTrue(fake_pack_path.exists())

    def test_nunca_sobrescreve_pack_ja_instalado(self):
        # cn52n já existe de verdade — um bundle malicioso/desatualizado não deve tocá-lo
        bundle = {"packs": {"cn52n": {"pack": "cn52n", "elementos": {"forjado": {}}}}}
        installed = import_bundle_packs(bundle)

        self.assertEqual(installed, [])
        with open(_SCREENS_DIR / "cn52n.json", "r", encoding="utf-8") as f:
            real = json.load(f)
        self.assertNotIn("forjado", real["elementos"])


class TestSummarizeFlow(unittest.TestCase):
    def test_zerar_compromisso_grava_e_nao_elimina(self):
        summary = summarize_flow(_load_sample("cn52n_zerar_compromisso.json"))
        self.assertIn("CN52N", summary["transacoes"])
        self.assertTrue(summary["grava"])
        self.assertFalse(summary["elimina_ou_exclui"])
        self.assertEqual(summary["needs_review_node_ids"], [])

    def test_data_necessidade_declara_insumo_de_planilha(self):
        summary = summarize_flow(_load_sample("cj20n_data_necessidade.json"))
        self.assertEqual(len(summary["insumos"]), 1)
        self.assertIn("PEP", summary["insumos"][0]["colunas"])
        self.assertIn("Diagrama", summary["insumos"][0]["colunas"])

    def test_deteccao_de_eliminacao_por_heuristica(self):
        graph = {
            "transacao": "MB22",
            "nodes": [
                {"id": "n1", "type": "sap.set_checkbox", "label": "Marcar eliminação (XLOEK)", "params": {}},
            ],
        }
        summary = summarize_flow(graph)
        self.assertTrue(summary["elimina_ou_exclui"])

    def test_needs_review_aparece_no_resumo(self):
        graph = {
            "nodes": [
                {"id": "n1", "type": "data.log", "params": {"message": "x"}, "needs_review": True},
            ],
        }
        summary = summarize_flow(graph)
        self.assertEqual(summary["needs_review_node_ids"], ["n1"])


class TestBridgeInspectMirflow(unittest.TestCase):
    def _write_bundle(self, graph, packs=None):
        bundle = {"mirflow_version": 1, "graph": graph, "packs": packs or {}}
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".mirflow.json", delete=False, encoding="utf-8")
        json.dump(bundle, tmp, ensure_ascii=False)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def test_inspeciona_um_bundle_valido(self):
        graph = _load_sample("cn52n_zerar_compromisso.json")
        path = self._write_bundle(graph, packs={"cn52n": {"pack": "cn52n", "elementos": {}}})

        bridge = MirandinhaBridge()
        res = bridge.studio_inspect_mirflow(path)

        self.assertTrue(res["success"])
        self.assertTrue(res["data"]["summary"]["grava"])
        self.assertFalse(res["data"]["flow_id_ja_existe"])
        self.assertEqual(res["data"]["packs_faltando_localmente"], [])  # cn52n já é local

    def test_acusa_pack_faltando_localmente(self):
        graph = {"nodes": [{"id": "n1", "type": "flow.start", "params": {}}]}
        path = self._write_bundle(graph, packs={"pack_que_nao_existe_localmente": {"elementos": {}}})

        bridge = MirandinhaBridge()
        res = bridge.studio_inspect_mirflow(path)
        self.assertTrue(res["success"])
        self.assertIn("pack_que_nao_existe_localmente", res["data"]["packs_faltando_localmente"])

    def test_arquivo_sem_graph_e_invalido(self):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".mirflow.json", delete=False, encoding="utf-8")
        json.dump({"mirflow_version": 1}, tmp)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))

        bridge = MirandinhaBridge()
        res = bridge.studio_inspect_mirflow(tmp.name)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "MIRFLOW_INVALID")

    def test_arquivo_inexistente(self):
        bridge = MirandinhaBridge()
        res = bridge.studio_inspect_mirflow("C:/caminho/que/nao/existe.mirflow.json")
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "FILE_NOT_FOUND")

    def test_json_corrompido(self):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".mirflow.json", delete=False, encoding="utf-8")
        tmp.write("{ isso não é json")
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))

        bridge = MirandinhaBridge()
        res = bridge.studio_inspect_mirflow(tmp.name)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "MIRFLOW_INVALID")

    def test_flow_id_ja_existe_e_detectado(self):
        flow_id = "flow_sharing_ja_existe"
        save_studio_flow(flow_id, "Já tenho esse", {"flow_id": flow_id, "nodes": [], "edges": []})

        graph = {"flow_id": flow_id, "name": "Versão de outra pessoa", "nodes": [], "edges": []}
        path = self._write_bundle(graph)

        bridge = MirandinhaBridge()
        res = bridge.studio_inspect_mirflow(path)
        self.assertTrue(res["data"]["flow_id_ja_existe"])


class TestBridgeImportMirflow(unittest.TestCase):
    def _write_bundle(self, graph, packs=None):
        bundle = {"mirflow_version": 1, "graph": graph, "packs": packs or {}}
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".mirflow.json", delete=False, encoding="utf-8")
        json.dump(bundle, tmp, ensure_ascii=False)
        tmp.close()
        self.addCleanup(lambda: Path(tmp.name).unlink(missing_ok=True))
        return tmp.name

    def test_importa_e_salva_como_rascunho(self):
        flow_id = "flow_sharing_import_ok"
        graph = {"flow_id": flow_id, "name": "Fluxo compartilhado", "nodes": [], "edges": []}
        path = self._write_bundle(graph)

        bridge = MirandinhaBridge()
        res = bridge.studio_import_mirflow(path)

        self.assertTrue(res["success"])
        self.assertEqual(res["data"]["flow_id"], flow_id)

        saved = get_studio_flow(flow_id)
        self.assertEqual(saved["is_published"], 0)
        self.assertEqual(saved["origem"], "importado")

    def test_nunca_importa_publicado_mesmo_se_o_arquivo_diz_que_e(self):
        flow_id = "flow_sharing_import_forjado_publicado"
        graph = {
            "flow_id": flow_id, "name": "Fingindo ser publicado", "nodes": [], "edges": [],
            "is_published": True,  # campo que não existe no schema real — tentativa de forjar
        }
        path = self._write_bundle(graph)

        bridge = MirandinhaBridge()
        bridge.studio_import_mirflow(path)

        saved = get_studio_flow(flow_id)
        self.assertEqual(saved["is_published"], 0)

    def test_reimportar_sobre_um_publicado_local_o_torna_rascunho(self):
        """O portão vale também pra sobrescrita: reimportar uma versão atualizada de um
        fluxo que já estava publicado localmente derruba a publicação — republicar é
        decisão de quem está importando, não automática."""
        flow_id = "flow_sharing_reimport_estava_publicado"
        save_studio_flow(flow_id, "Original", {"flow_id": flow_id, "nodes": [], "edges": []})
        set_studio_flow_published(flow_id, True)
        self.assertEqual(get_studio_flow(flow_id)["is_published"], 1)

        graph = {"flow_id": flow_id, "name": "Versão nova de outra pessoa", "nodes": [], "edges": []}
        path = self._write_bundle(graph)

        bridge = MirandinhaBridge()
        bridge.studio_import_mirflow(path)

        saved = get_studio_flow(flow_id)
        self.assertEqual(saved["is_published"], 0)
        self.assertEqual(saved["name"], "Versão nova de outra pessoa")

    def test_instala_packs_que_faltam_localmente(self):
        pack_name = "pack_teste_import_bridge"
        pack_path = _SCREENS_DIR / f"{pack_name}.json"
        self.addCleanup(lambda: pack_path.unlink(missing_ok=True))

        flow_id = "flow_sharing_com_pack_novo"
        graph = {"flow_id": flow_id, "name": "Usa pack novo", "nodes": [], "edges": []}
        path = self._write_bundle(graph, packs={pack_name: {"pack": pack_name, "elementos": {}}})

        bridge = MirandinhaBridge()
        res = bridge.studio_import_mirflow(path)

        self.assertEqual(res["data"]["packs_instalados"], [pack_name])
        self.assertTrue(pack_path.exists())

    def test_recusa_com_rpa_ocupado(self):
        graph = {"flow_id": "flow_sharing_busy", "name": "x", "nodes": [], "edges": []}
        path = self._write_bundle(graph)

        bridge = MirandinhaBridge()
        bridge.rpa_runner._is_running = True
        res = bridge.studio_import_mirflow(path)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "RPA_BUSY")

    def test_recusa_sem_flow_id(self):
        path = self._write_bundle({"name": "sem id", "nodes": [], "edges": []})
        bridge = MirandinhaBridge()
        res = bridge.studio_import_mirflow(path)
        self.assertFalse(res["success"])
        self.assertEqual(res["error"]["code"], "FLOW_INVALID")


if __name__ == "__main__":
    unittest.main()
