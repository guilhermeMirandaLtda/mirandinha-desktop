"""
Testes da Biblioteca da Equipe (Etapa 6) — pasta de rede com .mirflow.json, sem
servidor. Usa um diretório temporário e monkeypatcha o caminho de configuração pra não
tocar no core/studio/team_library.json real da máquina que roda os testes.
"""
import json
import tempfile
import unittest
from pathlib import Path

import core.studio.team_library as team_library
from core.bridge import MirandinhaBridge


class TeamLibraryTestCase(unittest.TestCase):
    """Isola cada teste com seu próprio arquivo de config, restaurado no tearDown."""

    def setUp(self):
        self._tmp_config = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp_config.close()
        Path(self._tmp_config.name).unlink()  # começa sem existir, como um app novo

        self._original_config_path = team_library._CONFIG_PATH
        team_library._CONFIG_PATH = Path(self._tmp_config.name)

    def tearDown(self):
        team_library._CONFIG_PATH = self._original_config_path
        Path(self._tmp_config.name).unlink(missing_ok=True)


class TestTeamLibraryConfig(TeamLibraryTestCase):
    def test_sem_configuracao_retorna_none(self):
        self.assertIsNone(team_library.get_team_library_path())

    def test_salva_e_le_o_caminho(self):
        team_library.set_team_library_path("Z:/mirandinha_flows")
        self.assertEqual(team_library.get_team_library_path(), "Z:/mirandinha_flows")


class TestListTeamLibraryFiles(TeamLibraryTestCase):
    def test_sem_pasta_configurada_retorna_vazio(self):
        self.assertEqual(team_library.list_team_library_files(), [])

    def test_pasta_configurada_mas_inexistente_retorna_vazio(self):
        team_library.set_team_library_path("Z:/pasta/que/nao/existe/de/verdade")
        self.assertEqual(team_library.list_team_library_files(), [])

    def test_lista_mirflow_json_com_resumo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = {
                "mirflow_version": 1,
                "exported_at": "05/09/2026 12:00:00",
                "graph": {"name": "Fluxo da equipe", "transacao": "MB22", "nodes": [
                    {"id": "n1", "type": "sap.save", "params": {}}
                ]},
                "packs": {},
            }
            (Path(tmpdir) / "fluxo_teste.mirflow.json").write_text(json.dumps(bundle), encoding="utf-8")
            (Path(tmpdir) / "nao_e_mirflow.txt").write_text("ignorar isto", encoding="utf-8")

            team_library.set_team_library_path(tmpdir)
            files = team_library.list_team_library_files()

            self.assertEqual(len(files), 1)
            self.assertEqual(files[0]["file"], "fluxo_teste.mirflow.json")
            self.assertEqual(files[0]["name"], "Fluxo da equipe")
            self.assertEqual(files[0]["transacao"], "MB22")
            self.assertTrue(files[0]["summary"]["grava"])

    def test_arquivo_corrompido_nao_derruba_a_listagem(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "corrompido.mirflow.json").write_text("{ nao é json", encoding="utf-8")
            bundle = {"graph": {"name": "Este funciona", "nodes": []}}
            (Path(tmpdir) / "bom.mirflow.json").write_text(json.dumps(bundle), encoding="utf-8")

            team_library.set_team_library_path(tmpdir)
            files = team_library.list_team_library_files()

            self.assertEqual(len(files), 1)
            self.assertEqual(files[0]["name"], "Este funciona")


class TestBridgeTeamLibrary(TeamLibraryTestCase):
    def test_get_path_sem_configuracao(self):
        bridge = MirandinhaBridge()
        res = bridge.studio_get_team_library_path()
        self.assertTrue(res["success"])
        self.assertIsNone(res["data"])

    def test_list_team_library_delega_pra_funcao_pura(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bundle = {"graph": {"name": "X", "nodes": []}}
            (Path(tmpdir) / "x.mirflow.json").write_text(json.dumps(bundle), encoding="utf-8")
            team_library.set_team_library_path(tmpdir)

            bridge = MirandinhaBridge()
            res = bridge.studio_list_team_library()
            self.assertTrue(res["success"])
            self.assertEqual(len(res["data"]), 1)


if __name__ == "__main__":
    unittest.main()
