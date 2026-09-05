"""
Testes do laço (flow.foreach), do condicional (flow.if) e das políticas de on_error dentro
do corpo do laço — o coração da Etapa 4. Também roda os dois grafos de exemplo completos
(Zerar Compromisso e Data Necessidade) ponta a ponta contra uma sessão SAP falsa, provando
que o runtime executa exatamente o que os robôs nativos fazem, item a item.
"""
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from core.rpa.tasks.graph_task import GraphTask
from core.studio.screen_library import resolve_candidates
from tests._fake_sap import FakeElement, FakeSapGuiSession

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "core" / "studio" / "samples"


def _load_sample(name):
    with open(SAMPLES_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


def _task_with_fake_sap(graph, elements=None, params=None, cancel_check=None):
    task = GraphTask(graph=graph, params=params, cancel_check=cancel_check or (lambda: False))
    task.sap.session = FakeSapGuiSession(elements or {})
    task.sap.connect = lambda: task.sap.session  # sap.connect() não deve tocar win32com real
    task.sap.start_transaction = lambda tcode: None
    task.ctx.sap = task.sap
    return task


class TestForeachBasico(unittest.TestCase):
    def _graph_soma(self):
        """Grafo sintético: para cada número em 'numeros', loga o dobro. Sem SAP nenhum —
        prova o mecanismo de laço isoladamente do domínio SAP."""
        return {
            "schema_version": 1, "flow_id": "flow_teste_loop", "name": "Loop de teste",
            "variables": {"numeros": [1, 2, 3]},
            "nodes": [
                {"id": "n1", "type": "flow.start", "params": {}},
                {"id": "n2", "type": "flow.foreach", "params": {"source": "{{numeros}}", "item_var": "n"}},
                {"id": "n3", "type": "data.log", "params": {"level": "INFO", "message": "processando {{n}}"}, "on_error": "continue"},
                {"id": "n4", "type": "flow.end", "params": {}},
            ],
            "edges": [
                {"id": "e1", "from": "n1", "to": "n2", "port": "out"},
                {"id": "e2", "from": "n2", "to": "n3", "port": "loop"},
                {"id": "e3", "from": "n2", "to": "n4", "port": "done"},
            ],
        }

    def test_processa_todos_os_itens(self):
        logs = []
        task = GraphTask(graph=self._graph_soma(), log_callback=lambda l, m: logs.append((l, m)), cancel_check=lambda: False)
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["processed"], 3)
        self.assertEqual(result["errors"], 0)
        self.assertTrue(any("processando 1" in m for _, m in logs))
        self.assertTrue(any("processando 2" in m for _, m in logs))
        self.assertTrue(any("processando 3" in m for _, m in logs))

    def test_progresso_reflete_total_de_itens(self):
        progress_calls = []
        task = GraphTask(graph=self._graph_soma(), progress_callback=lambda c, t: progress_calls.append((c, t)), cancel_check=lambda: False)
        task.run()
        self.assertEqual(progress_calls[-1], (3, 3))

    def test_source_que_nao_e_lista_levanta_erro_claro(self):
        graph = self._graph_soma()
        graph["variables"]["numeros"] = "não sou uma lista"
        task = GraphTask(graph=graph, cancel_check=lambda: False)
        task.validate_input()
        task.prepare()
        with self.assertRaises(ValueError) as ctx:
            task.get_work_items()
        self.assertIn("lista", str(ctx.exception))


class TestOnErrorDentroDoLaco(unittest.TestCase):
    def _graph_dois_nos(self, on_error_no2):
        """n2 falha sempre (alvo inexistente); n3 só roda se o walk continuar depois de n2."""
        return {
            "schema_version": 1, "flow_id": "flow_teste_onerror", "name": "Teste on_error",
            "variables": {"itens": ["a", "b"]},
            "nodes": [
                {"id": "n1", "type": "flow.start", "params": {}},
                {"id": "n_fe", "type": "flow.foreach", "params": {"source": "{{itens}}", "item_var": "x"}},
                {"id": "n2", "type": "sap.press", "params": {"target": "wnd[0]/nao_existe"}, "on_error": on_error_no2},
                {"id": "n3", "type": "data.log", "params": {"level": "INFO", "message": "chegou em n3 para {{x}}"}, "on_error": "continue"},
                {"id": "n_end", "type": "flow.end", "params": {}},
            ],
            "edges": [
                {"id": "e1", "from": "n1", "to": "n_fe", "port": "out"},
                {"id": "e2", "from": "n_fe", "to": "n2", "port": "loop"},
                {"id": "e3", "from": "n2", "to": "n3", "port": "out"},
                {"id": "e4", "from": "n_fe", "to": "n_end", "port": "done"},
            ],
        }

    def test_skip_item_aborta_o_item_mas_segue_pro_proximo(self):
        logs = []
        task = _task_with_fake_sap(self._graph_dois_nos("skip_item"), elements={})
        task.log = lambda level, msg: logs.append((level, msg))
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["errors"], 2)  # os dois itens falharam em n2
        self.assertEqual(result["processed"], 0)
        self.assertFalse(any("chegou em n3" in m for _, m in logs))  # n3 nunca executou

    def test_continue_engole_o_erro_e_segue_pro_proximo_no(self):
        task = _task_with_fake_sap(self._graph_dois_nos("continue"), elements={})
        logs = []
        task.log = lambda level, msg: logs.append((level, msg))
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["processed"], 2)  # os dois itens completaram (n3 rodou)
        self.assertEqual(result["errors"], 0)
        self.assertTrue(any("chegou em n3 para a" in m for _, m in logs))
        self.assertTrue(any("chegou em n3 para b" in m for _, m in logs))

    def test_abort_dentro_do_laco_para_tudo_e_nao_processa_os_demais_itens(self):
        task = _task_with_fake_sap(self._graph_dois_nos("abort"), elements={})
        result = task.run()
        # abort levanta a flag interna -> cancel_check() combinado vira True -> RPAJobBase
        # trata como cancelamento e para antes do próximo item.
        self.assertEqual(result["status"], "CANCELLED")
        self.assertLessEqual(result["errors"] + result["processed"], 1)

    def test_route_desvia_para_a_porta_error(self):
        graph = self._graph_dois_nos("route")
        graph["nodes"].append({"id": "n_err", "type": "data.log", "params": {"level": "WARNING", "message": "rota de erro para {{x}}"}, "on_error": "continue"})
        graph["edges"].append({"id": "e5", "from": "n2", "to": "n_err", "port": "error"})
        logs = []
        task = _task_with_fake_sap(graph, elements={})
        task.log = lambda level, msg: logs.append((level, msg))
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")
        self.assertTrue(any("rota de erro para a" in m for _, m in logs))
        self.assertFalse(any("chegou em n3" in m for _, m in logs))  # 'out' não foi seguido


class TestFlowIf(unittest.TestCase):
    def _graph_if(self, left_value):
        return {
            "schema_version": 1, "flow_id": "flow_teste_if", "name": "Teste if",
            "variables": {"x": left_value},
            "nodes": [
                {"id": "n1", "type": "flow.start", "params": {}},
                {"id": "n2", "type": "flow.if", "params": {"left": "{{x}}", "operator": ">", "right": 10}},
                {"id": "n3", "type": "data.log", "params": {"level": "INFO", "message": "maior que 10"}, "on_error": "continue"},
                {"id": "n4", "type": "data.log", "params": {"level": "INFO", "message": "não é maior que 10"}, "on_error": "continue"},
                {"id": "n5", "type": "flow.end", "params": {}},
            ],
            "edges": [
                {"id": "e1", "from": "n1", "to": "n2", "port": "out"},
                {"id": "e2", "from": "n2", "to": "n3", "port": "true"},
                {"id": "e3", "from": "n2", "to": "n4", "port": "false"},
                {"id": "e4", "from": "n3", "to": "n5", "port": "out"},
                {"id": "e5", "from": "n4", "to": "n5", "port": "out"},
            ],
        }

    def test_branch_true(self):
        logs = []
        task = GraphTask(graph=self._graph_if(20), log_callback=lambda l, m: logs.append(m), cancel_check=lambda: False)
        task.run()
        self.assertTrue(any("maior que 10" == m for m in logs))
        self.assertFalse(any("não é maior que 10" == m for m in logs))

    def test_branch_false(self):
        logs = []
        task = GraphTask(graph=self._graph_if(5), log_callback=lambda l, m: logs.append(m), cancel_check=lambda: False)
        task.run()
        self.assertTrue(any("não é maior que 10" == m for m in logs))
        self.assertFalse(any("maior que 10" == m for m in logs))

    def test_operador_invalido_levanta_erro_claro(self):
        graph = self._graph_if(5)
        graph["nodes"][1]["params"]["operator"] = "??"
        task = GraphTask(graph=graph, cancel_check=lambda: False)
        result = task.run()
        # RPAJobBase isola falha por item: linear = 1 item só, então o job termina SUCCESS
        # com esse único item marcado como erro (mesmo padrão dos testes de handlers).
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["errors"], 1)


class _FecharPainelAoSalvar(FakeElement):
    """
    Botão Gravar cujo .press() remove o painel de detalhe da sessão falsa — simula o SAP
    fechando a tela de detalhe depois de uma gravação bem-sucedida, o que é exatamente o
    que flow.assert_absent (n_check) verifica no grafo real.
    """
    def __init__(self, session, panel_id):
        super().__init__()
        self._session = session
        self._panel_id = panel_id

    def press(self):
        super().press()
        self._session.elements.pop(self._panel_id, None)


class _GridComAberturaDeDetalhe(FakeElement):
    """
    Grade cujo doubleClickCurrentCell() reabre o painel de detalhe — simula o SAP exibindo
    a tela de detalhe do item ao dar duplo clique, que é o que sap.wait_for (n_wait) espera
    aparecer em seguida, item após item.
    """
    def __init__(self, row_count, cells, session, panel_id):
        super().__init__(row_count=row_count, cells=cells)
        self._session = session
        self._panel_id = panel_id

    def doubleClickCurrentCell(self):
        super().doubleClickCurrentCell()
        self._session.elements[self._panel_id] = FakeElement()


class TestZerarCompromissoEndToEnd(unittest.TestCase):
    def _build_elements(self, rows):
        """rows: lista de (posid, maktx). Monta o grid e os elementos da tela de detalhe,
        com o painel de detalhe abrindo a cada duplo clique e fechando a cada gravação —
        o ciclo real que sap.wait_for e flow.assert_absent conferem em cada item."""
        cells = {}
        for i, (posid, maktx) in enumerate(rows):
            cells[(i, "POSID")] = posid
            cells[(i, "MAKTX")] = maktx

        grid_id = resolve_candidates("cn52n", "grid_alv")[0]
        panel_id = resolve_candidates("cn52n", "painel_detalhe")[0]

        elements = {
            panel_id: FakeElement(),
            resolve_candidates("cn52n", "aba_detalhes")[0]: FakeElement(),
            resolve_candidates("cn52n", "campo_quantidade")[0]: FakeElement(),
            resolve_candidates("cn52n", "campo_local_descarga")[0]: FakeElement(),
        }
        session = FakeSapGuiSession(elements)
        grid = _GridComAberturaDeDetalhe(len(rows), cells, session, panel_id)
        elements[grid_id] = grid
        elements["wnd[0]/tbar[0]/btn[11]"] = _FecharPainelAoSalvar(session, panel_id)
        return elements, grid, session

    def test_roda_o_grafo_completo_e_zera_os_dois_itens(self):
        graph = _load_sample("cn52n_zerar_compromisso.json")
        elements, grid, _session = self._build_elements([("PEP-01", "Cabo"), ("PEP-02", "Conector")])
        task = _task_with_fake_sap(graph, elements=elements)

        result = task.run()

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["processed"], 2)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["job_id"], "flow_cn52n_zerar_compromisso")

        campo_qtd = elements[resolve_candidates("cn52n", "campo_quantidade")[0]]
        campo_local = elements[resolve_candidates("cn52n", "campo_local_descarga")[0]]
        self.assertEqual(campo_qtd.text, "0")
        self.assertEqual(campo_local.text, ".")  # variables.local_descarga do grafo
        self.assertTrue(grid.double_clicked)

    def test_item_bloqueado_vira_erro_isolado_sem_derrubar_o_job(self):
        graph = _load_sample("cn52n_zerar_compromisso.json")
        elements, grid, _session = self._build_elements([("PEP-01", "Cabo"), ("PEP-02", "Conector")])
        # painel_detalhe ausente -> sap.wait_for estoura -> item 1 falha; mas o grid_double_click
        # do item 2 já rodou antes disso ser detectado, então simulamos removendo o campo
        # obrigatório em vez do painel (mais realista: campo bloqueado/somente leitura).
        del elements[resolve_candidates("cn52n", "campo_quantidade")[0]]

        task = _task_with_fake_sap(graph, elements=elements)
        result = task.run()

        self.assertEqual(result["status"], "SUCCESS")  # job continua, isolado por item
        self.assertEqual(result["errors"], 2)
        self.assertEqual(result["processed"], 0)
        self.assertEqual(len(result["peps_com_falha"]), 2)


class TestDataNecessidadeEndToEnd(unittest.TestCase):
    def _make_spreadsheet(self):
        df = pd.DataFrame({
            "PEP": ["01-0001-24.01.01", "02-0010-24.01.05"],
            "Diagrama": ["40001234", "40009876"],
            "Data Necessidade": ["15/10/2026", "05/12/2026"],
        })
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.close()
        df.to_excel(tmp.name, index=False)
        return tmp.name

    def _build_elements(self):
        refs = [
            "btn_open", "filter_proj_ext", "filter_prps_ext", "input_aufnr",
            "btn_search_confirm", "tree_project", "toolbar_overview", "btn_mass_copy",
            "btn_deselect_all", "chk_mark_bdter", "input_bdter", "btn_mark_all_lines",
            "btn_modal_confirm",
        ]
        elements = {resolve_candidates("cj20n", ref)[0]: FakeElement() for ref in refs}
        elements["wnd[0]/tbar[0]/btn[11]"] = FakeElement()
        return elements

    def test_roda_o_grafo_completo_para_dois_diagramas(self):
        path = self._make_spreadsheet()
        try:
            graph = _load_sample("cj20n_data_necessidade.json")
            elements = self._build_elements()
            task = _task_with_fake_sap(graph, elements=elements, params={"spreadsheet_path": path})

            result = task.run()

            self.assertEqual(result["status"], "SUCCESS")
            self.assertEqual(result["processed"], 2)
            self.assertEqual(result["errors"], 0)

            campo_data = elements[resolve_candidates("cj20n", "input_bdter")[0]]
            # o último diagrama processado grava por último — confere que alguma data válida chegou
            self.assertIn(campo_data.text, ("15.10.2026", "05.12.2026"))
        finally:
            Path(path).unlink(missing_ok=True)

    def test_data_no_passado_remoto_isola_o_diagrama_sem_derrubar_o_job(self):
        df = pd.DataFrame({
            "PEP": ["01-0001-24.01.01"],
            "Diagrama": ["40001234"],
            "Data Necessidade": ["01/01/2000"],  # bem no passado -> data.format_date recusa
        })
        tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        tmp.close()
        df.to_excel(tmp.name, index=False)
        try:
            graph = _load_sample("cj20n_data_necessidade.json")
            elements = self._build_elements()
            task = _task_with_fake_sap(graph, elements=elements, params={"spreadsheet_path": tmp.name})

            result = task.run()

            self.assertEqual(result["status"], "SUCCESS")
            self.assertEqual(result["errors"], 1)
            self.assertEqual(result["processed"], 0)
        finally:
            Path(tmp.name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
