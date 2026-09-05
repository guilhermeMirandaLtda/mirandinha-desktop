"""
Testes do trace ao vivo do GraphTask (Etapa 3) — a base do canvas pintando os blocos
durante a execução. Cobre a regra de limite do plano: detalhe nó a nó só nos 3 primeiros
itens; dali em diante, um resumo por item, mais todo erro (não importa o item).
"""
import unittest

from core.rpa.tasks.graph_task import GraphTask


def _graph_com_n_itens(n):
    return {
        "schema_version": 1, "flow_id": "flow_trace_teste", "name": "Trace de teste",
        "variables": {"itens": list(range(n))},
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


class TestTraceLimiteDeEventos(unittest.TestCase):
    def test_traceia_no_a_no_nos_tres_primeiros_itens(self):
        events = []
        task = GraphTask(graph=_graph_com_n_itens(5), trace_callback=events.append, cancel_check=lambda: False)
        task.run()

        node_events_por_item = {}
        for e in events:
            if e["type"] == "node":
                node_events_por_item.setdefault(e["item_index"], 0)
                node_events_por_item[e["item_index"]] += 1

        # itens 1, 2, 3: dois eventos por nó executado (running + done) = 2
        for idx in (1, 2, 3):
            self.assertEqual(node_events_por_item.get(idx), 2, msg=f"item {idx}")

    def test_a_partir_do_quarto_item_so_ha_resumo_por_item(self):
        events = []
        task = GraphTask(graph=_graph_com_n_itens(5), trace_callback=events.append, cancel_check=lambda: False)
        task.run()

        for idx in (4, 5):
            node_events = [e for e in events if e["type"] == "node" and e.get("item_index") == idx]
            item_events = [e for e in events if e["type"] == "item" and e.get("item_index") == idx]
            self.assertEqual(node_events, [], msg=f"item {idx} não deveria ter evento de nó")
            self.assertEqual(len(item_events), 1, msg=f"item {idx}")
            self.assertEqual(item_events[0]["status"], "done")

    def test_erro_sempre_traceia_mesmo_alem_do_terceiro_item(self):
        graph = _graph_com_n_itens(5)
        # n3 falha sempre (mensagem exige uma variável que não existe)
        graph["nodes"][2]["params"]["message"] = "{{nao_existe}}"
        graph["nodes"][2]["on_error"] = "skip_item"

        events = []
        task = GraphTask(graph=graph, trace_callback=events.append, cancel_check=lambda: False)
        task.run()

        erros_por_no = [e for e in events if e["type"] == "node" and e["status"] == "error"]
        # 5 itens, cada um falha em n3 -> 5 eventos de erro de nó, mesmo além do item 3
        self.assertEqual(len(erros_por_no), 5)
        self.assertTrue(all(e["node_id"] == "n3" for e in erros_por_no))

    def test_evento_running_precede_done_para_o_mesmo_no(self):
        events = []
        task = GraphTask(graph=_graph_com_n_itens(1), trace_callback=events.append, cancel_check=lambda: False)
        task.run()

        node_events = [e for e in events if e["type"] == "node" and e["node_id"] == "n3"]
        self.assertEqual([e["status"] for e in node_events], ["running", "done"])

    def test_callback_que_quebra_nao_derruba_a_execucao(self):
        def trace_quebrado(evt):
            raise RuntimeError("callback do canvas explodiu")

        task = GraphTask(graph=_graph_com_n_itens(2), trace_callback=trace_quebrado, cancel_check=lambda: False)
        result = task.run()
        self.assertEqual(result["status"], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
