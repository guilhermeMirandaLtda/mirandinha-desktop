"""
Prova o critério de aceite da Etapa 2 sobre o grafo de exemplo do Zerar Compromisso:
'funciona sem um único ID de SAP aparecendo no JSON do fluxo' — aqui, 'funciona' significa
valida estruturalmente e resolve todo alvo pela Biblioteca de Telas. O grafo tem um
flow.foreach, então ainda é recusado pelo runtime linear da Etapa 1/2 — isso é esperado e
está testado explicitamente, para não regredir silenciosamente quando a Etapa 4 chegar.
"""
import json
import re
import unittest
from pathlib import Path

from core.studio.validator import validate_graph
from core.rpa.tasks.graph_task import GraphTask

SAMPLE_PATH = (
    Path(__file__).resolve().parent.parent
    / "core" / "studio" / "samples" / "cn52n_zerar_compromisso.json"
)

# Um id cru do SAP GUI Scripting sempre começa com "wnd[".
_RAW_SAP_ID_RE = re.compile(r"wnd\[\d\]")


def _load_sample():
    with open(SAMPLE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


class TestZerarCompromissoSample(unittest.TestCase):
    def test_grafo_valida_estruturalmente(self):
        graph = _load_sample()
        result = validate_graph(graph)
        errors = [i for i in result["issues"] if i["severity"] == "error"]
        self.assertTrue(result["ok"], msg=f"Erros: {errors}")

    def test_nenhum_id_cru_de_sap_no_campo_target(self):
        """
        O teste central da Etapa 2: todo 'target' é {pack, ref}, nunca uma string wnd[...].
        Não varre o params inteiro — sap.handle_popup tem 'window': 'wnd[1]', que é constante
        estrutural (qual janela popup), não uma referência de tela; sua 'action' já é
        simbólica ('ok'/'yes'/'no'/'cancel'), o teste de action_e_simbolica cobre isso.
        """
        graph = _load_sample()
        for node in graph["nodes"]:
            target = node.get("params", {}).get("target")
            if target is None:
                continue
            target_str = json.dumps(target)
            self.assertNotRegex(
                target_str, _RAW_SAP_ID_RE,
                msg=f"Nó '{node['id']}' ({node['type']}) tem um id cru do SAP GUI em 'target'.",
            )

    def test_handle_popup_usa_action_simbolica_nao_id_cru(self):
        graph = _load_sample()
        popup_nodes = [n for n in graph["nodes"] if n["type"] == "sap.handle_popup"]
        self.assertGreater(len(popup_nodes), 0)
        for node in popup_nodes:
            action = node["params"]["action"]
            self.assertIn(action, {"ok", "yes", "no", "cancel"})

    def test_todos_os_alvos_sao_referencias_de_pack_para_cn52n(self):
        graph = _load_sample()
        targets_checked = 0
        for node in graph["nodes"]:
            target = node.get("params", {}).get("target")
            if target is None:
                continue
            self.assertIsInstance(target, dict)
            self.assertEqual(target.get("pack"), "cn52n")
            self.assertIn("ref", target)
            targets_checked += 1
        self.assertGreater(targets_checked, 0)

    def test_runtime_reconhece_o_laco_desde_a_etapa_4(self):
        """A Etapa 4 passou a suportar flow.foreach — o grafo valida e localiza o laço."""
        graph = _load_sample()
        task = GraphTask(graph=graph, cancel_check=lambda: False)
        task.validate_input()  # não levanta mais
        self.assertIsNotNone(task._foreach_node)
        self.assertEqual(task._foreach_node["id"], "n_foreach")


if __name__ == "__main__":
    unittest.main()
