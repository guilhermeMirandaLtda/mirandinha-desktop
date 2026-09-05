"""
Testes dos executores de nó do GraphTask (Etapa 2) contra uma sessão SAP falsa.
Não importa win32com nem precisa do SAP aberto — troca task.sap.session por um objeto
fake que implementa só o que os handlers realmente chamam (findById, .text, .press(), ...).
Prova que a resolução de alvo (literal e via Biblioteca de Telas) e cada executor fazem
exatamente o que o código legado fazia.
"""
import unittest

from core.rpa.tasks.graph_task import GraphTask
from core.studio.screen_library import resolve_candidates
from tests._fake_sap import FakeElement, FakeSapGuiSession


def _minimal_task(nodes, edges, variables=None, elements=None):
    graph = {
        "schema_version": 1,
        "flow_id": "flow_handler_teste",
        "name": "Teste de handlers",
        "variables": variables or {},
        "nodes": nodes,
        "edges": edges,
    }
    task = GraphTask(graph=graph, cancel_check=lambda: False)
    fake_session = FakeSapGuiSession(elements or {})
    task.sap.session = fake_session
    task.ctx.sap = task.sap
    return task, fake_session


class TestSapSetTextEPress(unittest.TestCase):
    def test_set_text_com_alvo_literal(self):
        el = FakeElement()
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "sap.set_text", "params": {"target": "wnd[0]/usr/txtX", "value": "0"}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [
            {"id": "e1", "from": "n1", "to": "n2", "port": "out"},
            {"id": "e2", "from": "n2", "to": "n3", "port": "out"},
        ]
        task, session = _minimal_task(nodes, edges, elements={"wnd[0]/usr/txtX": el})
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(el.text, "0")

    def test_set_text_resolve_template(self):
        el = FakeElement()
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "sap.set_text", "params": {"target": "wnd[0]/usr/txtX", "value": "{{local}}"}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [
            {"id": "e1", "from": "n1", "to": "n2", "port": "out"},
            {"id": "e2", "from": "n2", "to": "n3", "port": "out"},
        ]
        task, session = _minimal_task(nodes, edges, variables={"local": "."}, elements={"wnd[0]/usr/txtX": el})
        task.run()
        self.assertEqual(el.text, ".")

    def test_press_via_biblioteca_de_telas(self):
        """Prova a cadeia completa: pack -> resolve_candidates -> find_element_any -> .press()."""
        el = FakeElement()
        real_id = resolve_candidates("cn52n", "aba_detalhes")[0]
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "sap.press", "params": {"target": {"pack": "cn52n", "ref": "aba_detalhes"}}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [
            {"id": "e1", "from": "n1", "to": "n2", "port": "out"},
            {"id": "e2", "from": "n2", "to": "n3", "port": "out"},
        ]
        task, session = _minimal_task(nodes, edges, elements={real_id: el})
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertTrue(el.pressed)


class TestSapSelectECheckbox(unittest.TestCase):
    def test_select_sem_node_chama_select(self):
        el = FakeElement()
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "sap.select", "params": {"target": "wnd[0]/tab"}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [{"id": "e1", "from": "n1", "to": "n2", "port": "out"}, {"id": "e2", "from": "n2", "to": "n3", "port": "out"}]
        task, session = _minimal_task(nodes, edges, elements={"wnd[0]/tab": el})
        task.run()
        self.assertTrue(el.pressed)

    def test_select_com_node_define_selected_node(self):
        el = FakeElement()
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "sap.select", "params": {"target": "wnd[0]/tree", "node": "000002"}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [{"id": "e1", "from": "n1", "to": "n2", "port": "out"}, {"id": "e2", "from": "n2", "to": "n3", "port": "out"}]
        task, session = _minimal_task(nodes, edges, elements={"wnd[0]/tree": el})
        task.run()
        self.assertEqual(el.selectedNode, "000002")

    def test_set_checkbox(self):
        el = FakeElement()
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "sap.set_checkbox", "params": {"target": "wnd[0]/chk", "checked": True}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [{"id": "e1", "from": "n1", "to": "n2", "port": "out"}, {"id": "e2", "from": "n2", "to": "n3", "port": "out"}]
        task, session = _minimal_task(nodes, edges, elements={"wnd[0]/chk": el})
        task.run()
        self.assertTrue(el.selected)


class TestSapSaveEBack(unittest.TestCase):
    def test_save_usa_id_universal_btn11(self):
        el = FakeElement()
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "sap.save", "params": {}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [{"id": "e1", "from": "n1", "to": "n2", "port": "out"}, {"id": "e2", "from": "n2", "to": "n3", "port": "out"}]
        task, session = _minimal_task(nodes, edges, elements={"wnd[0]/tbar[0]/btn[11]": el})
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertTrue(el.pressed)

    def test_back_envia_f3_na_janela_principal(self):
        el = FakeElement()
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "sap.back", "params": {}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [{"id": "e1", "from": "n1", "to": "n2", "port": "out"}, {"id": "e2", "from": "n2", "to": "n3", "port": "out"}]
        task, session = _minimal_task(nodes, edges, elements={"wnd[0]": el})
        task.run()
        self.assertIn("vkey:3", el.pressed_buttons)


class TestSapGridDoubleClick(unittest.TestCase):
    def test_double_click_posiciona_e_dispara(self):
        grid = FakeElement()
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "sap.grid_double_click",
             "params": {"target": "wnd[0]/grid", "row": "{{linha}}", "column": "FLMNG"}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [{"id": "e1", "from": "n1", "to": "n2", "port": "out"}, {"id": "e2", "from": "n2", "to": "n3", "port": "out"}]
        task, session = _minimal_task(nodes, edges, variables={"linha": 3}, elements={"wnd[0]/grid": grid})
        task.run()
        self.assertEqual(grid.currentCellRow, 3)
        self.assertEqual(grid.currentCellColumn, "FLMNG")
        self.assertTrue(grid.double_clicked)


class TestSapWaitFor(unittest.TestCase):
    def test_wait_for_retorna_quando_elemento_ja_existe(self):
        el = FakeElement()
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "sap.wait_for", "params": {"target": "wnd[0]/x", "timeout_ms": 200}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [{"id": "e1", "from": "n1", "to": "n2", "port": "out"}, {"id": "e2", "from": "n2", "to": "n3", "port": "out"}]
        task, session = _minimal_task(nodes, edges, elements={"wnd[0]/x": el})
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")

    def test_wait_for_estoura_timeout_e_falha(self):
        # RPAJobBase isola falha por item: o job continua SUCCESS, o item é que vira erro —
        # igual ao comportamento das tasks nativas (peps_com_falha), não uma exceção que
        # derruba o job inteiro.
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "sap.wait_for", "params": {"target": "wnd[0]/nunca", "timeout_ms": 150}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [{"id": "e1", "from": "n1", "to": "n2", "port": "out"}, {"id": "e2", "from": "n2", "to": "n3", "port": "out"}]
        task, session = _minimal_task(nodes, edges, elements={})
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["processed"], 0)


class TestFlowAssertAbsent(unittest.TestCase):
    def test_assert_absent_passa_quando_elemento_sumiu(self):
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "flow.assert_absent",
             "params": {"target": "wnd[0]/detalhe", "message": "continuou aberto"}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [{"id": "e1", "from": "n1", "to": "n2", "port": "out"}, {"id": "e2", "from": "n2", "to": "n3", "port": "out"}]
        task, session = _minimal_task(nodes, edges, elements={})
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")

    def test_assert_absent_falha_quando_elemento_continua_presente(self):
        el = FakeElement()
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "flow.assert_absent",
             "params": {"target": "wnd[0]/detalhe", "message": "A tela de detalhe continuou aberta."}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [{"id": "e1", "from": "n1", "to": "n2", "port": "out"}, {"id": "e2", "from": "n2", "to": "n3", "port": "out"}]
        task, session = _minimal_task(nodes, edges, elements={"wnd[0]/detalhe": el})
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["errors"], 1)


class TestSapHandlePopup(unittest.TestCase):
    def test_popup_opcional_ausente_nao_falha(self):
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "sap.handle_popup",
             "params": {"window": "wnd[1]", "action": "ok", "optional": True}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [{"id": "e1", "from": "n1", "to": "n2", "port": "out"}, {"id": "e2", "from": "n2", "to": "n3", "port": "out"}]
        task, session = _minimal_task(nodes, edges, elements={})
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")

    def test_popup_presente_pressiona_acao_ok(self):
        popup = FakeElement()
        btn_ok = FakeElement()
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "sap.handle_popup",
             "params": {"window": "wnd[1]", "action": "ok", "optional": True}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [{"id": "e1", "from": "n1", "to": "n2", "port": "out"}, {"id": "e2", "from": "n2", "to": "n3", "port": "out"}]
        task, session = _minimal_task(nodes, edges, elements={
            "wnd[1]": popup,
            "wnd[1]/tbar[0]/btn[0]": btn_ok,
        })
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertTrue(btn_ok.pressed)

    def test_popup_action_invalida_levanta_erro_claro(self):
        popup = FakeElement()
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "sap.handle_popup",
             "params": {"window": "wnd[1]", "action": "talvez", "optional": True}, "on_error": "abort"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [{"id": "e1", "from": "n1", "to": "n2", "port": "out"}, {"id": "e2", "from": "n2", "to": "n3", "port": "out"}]
        task, session = _minimal_task(nodes, edges, elements={"wnd[1]": popup})
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["errors"], 1)


class TestFlowEscape(unittest.TestCase):
    def test_escape_chama_safe_recover_state_n_vezes(self):
        calls = []
        nodes = [
            {"id": "n1", "type": "flow.start", "params": {}},
            {"id": "n2", "type": "flow.escape", "params": {"attempts": 2}, "on_error": "continue"},
            {"id": "n3", "type": "flow.end", "params": {}},
        ]
        edges = [{"id": "e1", "from": "n1", "to": "n2", "port": "out"}, {"id": "e2", "from": "n2", "to": "n3", "port": "out"}]
        task, session = _minimal_task(nodes, edges, elements={})
        task.sap.safe_recover_state = lambda: calls.append(1)
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(len(calls), 2)


if __name__ == "__main__":
    unittest.main()
