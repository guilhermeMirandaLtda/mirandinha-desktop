"""
Testes unitários do runtime do Studio (Etapa 1) — validador, contexto de execução e GraphTask.
Não tocam no SAP: usam apenas nós que não dependem de SapSession (data.log) para provar o
ciclo de vida completo herdado de RPAJobBase.
"""
import unittest

from core.studio.validator import validate_graph
from core.studio.execution_context import ExecutionContext
from core.rpa.tasks.graph_task import GraphTask


def _base_graph(nodes, edges, variables=None):
    return {
        "schema_version": 1,
        "flow_id": "flow_teste",
        "name": "Grafo de teste",
        "variables": variables or {},
        "nodes": nodes,
        "edges": edges,
    }


class TestValidator(unittest.TestCase):
    def test_grafo_valido_sem_problemas(self):
        graph = _base_graph(
            nodes=[
                {"id": "n1", "type": "flow.start", "params": {}},
                {"id": "n2", "type": "data.log", "params": {"message": "oi"}, "on_error": "continue"},
                {"id": "n3", "type": "flow.end", "params": {}},
            ],
            edges=[
                {"id": "e1", "from": "n1", "to": "n2", "port": "out"},
                {"id": "e2", "from": "n2", "to": "n3", "port": "out"},
            ],
        )
        result = validate_graph(graph)
        self.assertTrue(result["ok"])
        self.assertEqual(result["issues"], [])

    def test_sem_flow_start_e_erro(self):
        graph = _base_graph(
            nodes=[{"id": "n1", "type": "flow.end", "params": {}}],
            edges=[],
        )
        result = validate_graph(graph)
        self.assertFalse(result["ok"])
        self.assertTrue(any("flow.start" in i["message"] for i in result["issues"]))

    def test_on_error_obrigatorio(self):
        graph = _base_graph(
            nodes=[
                {"id": "n1", "type": "flow.start", "params": {}},
                {"id": "n2", "type": "data.log", "params": {"message": "sem on_error"}},
                {"id": "n3", "type": "flow.end", "params": {}},
            ],
            edges=[
                {"id": "e1", "from": "n1", "to": "n2", "port": "out"},
                {"id": "e2", "from": "n2", "to": "n3", "port": "out"},
            ],
        )
        result = validate_graph(graph)
        self.assertFalse(result["ok"])
        self.assertTrue(any("on_error" in i["message"] for i in result["issues"] if i["node_id"] == "n2"))

    def test_tipo_desconhecido_e_erro(self):
        graph = _base_graph(
            nodes=[
                {"id": "n1", "type": "flow.start", "params": {}},
                {"id": "n2", "type": "sap.teleport", "params": {}, "on_error": "abort"},
            ],
            edges=[{"id": "e1", "from": "n1", "to": "n2", "port": "out"}],
        )
        result = validate_graph(graph)
        self.assertFalse(result["ok"])
        self.assertTrue(any("desconhecido" in i["message"] for i in result["issues"]))

    def test_no_orfao_gera_aviso_nao_bloqueia(self):
        graph = _base_graph(
            nodes=[
                {"id": "n1", "type": "flow.start", "params": {}},
                {"id": "n2", "type": "flow.end", "params": {}},
                {"id": "n3", "type": "data.log", "params": {"message": "solto"}, "on_error": "continue"},
            ],
            edges=[{"id": "e1", "from": "n1", "to": "n2", "port": "out"}],
        )
        result = validate_graph(graph)
        self.assertTrue(result["ok"])
        warnings = [i for i in result["issues"] if i["severity"] == "warning"]
        self.assertTrue(any(i["node_id"] == "n3" for i in warnings))

    def test_porta_invalida_e_erro(self):
        graph = _base_graph(
            nodes=[
                {"id": "n1", "type": "flow.start", "params": {}},
                {"id": "n2", "type": "flow.end", "params": {}},
            ],
            edges=[{"id": "e1", "from": "n1", "to": "n2", "port": "lateral"}],
        )
        result = validate_graph(graph)
        self.assertFalse(result["ok"])


class TestExecutionContext(unittest.TestCase):
    def test_resolve_value_placeholder_unico_preserva_tipo(self):
        ctx = ExecutionContext()
        ctx.set_var("linhas", [{"a": 1}, {"a": 2}])
        self.assertEqual(ctx.resolve_value("{{linhas}}"), [{"a": 1}, {"a": 2}])

    def test_resolve_value_interpolacao_em_texto(self):
        ctx = ExecutionContext()
        ctx.set_var("nome", "CN52N")
        self.assertEqual(ctx.resolve_value("Transação: {{nome}}"), "Transação: CN52N")

    def test_resolve_value_caminho_pontilhado_no_item(self):
        ctx = ExecutionContext()
        ctx.item = {"pep": "123", "material": "Cabo"}
        ctx.item_var = "item"
        self.assertEqual(ctx.resolve_value("{{item.material}}"), "Cabo")

    def test_variavel_inexistente_leva_a_erro(self):
        ctx = ExecutionContext()
        with self.assertRaises(KeyError):
            ctx.resolve_value("{{nao_existe}}")

    def test_valor_nao_string_e_literal(self):
        ctx = ExecutionContext()
        self.assertEqual(ctx.resolve_value(42), 42)
        self.assertEqual(ctx.resolve_value(True), True)


class TestGraphTask(unittest.TestCase):
    def _linear_graph(self):
        return _base_graph(
            nodes=[
                {"id": "n1", "type": "flow.start", "params": {}},
                {"id": "n2", "type": "data.log", "params": {"level": "INFO", "message": "Olá {{quem}}"}, "on_error": "continue"},
                {"id": "n3", "type": "data.log", "params": {"level": "SUCCESS", "message": "fim"}, "on_error": "continue"},
                {"id": "n4", "type": "flow.end", "params": {}},
            ],
            edges=[
                {"id": "e1", "from": "n1", "to": "n2", "port": "out"},
                {"id": "e2", "from": "n2", "to": "n3", "port": "out"},
                {"id": "e3", "from": "n3", "to": "n4", "port": "out"},
            ],
            variables={"quem": "Etapa 1"},
        )

    def test_run_grafo_linear_sem_sap(self):
        logs = []
        task = GraphTask(
            graph=self._linear_graph(),
            log_callback=lambda level, msg: logs.append((level, msg)),
            cancel_check=lambda: False,
        )
        result = task.run()

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["processed"], 1)
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["job_id"], "flow_teste")
        self.assertTrue(any("Olá Etapa 1" in msg for _, msg in logs))

    def test_governanca_dinamica_vem_do_grafo(self):
        graph = self._linear_graph()
        graph["transacao"] = "CN52N"
        graph["group"] = "Materiais"
        task = GraphTask(graph=graph, cancel_check=lambda: False)
        self.assertEqual(task.TRANSACTION, "CN52N")
        self.assertEqual(task.MODULE, "Materiais")
        self.assertEqual(task.JOB_NAME, "Grafo de teste")

    def test_foreach_no_grafo_recusa_com_mensagem_de_etapa4(self):
        graph = _base_graph(
            nodes=[
                {"id": "n1", "type": "flow.start", "params": {}},
                {"id": "n2", "type": "flow.foreach", "params": {"source": "{{linhas}}"}},
                {"id": "n3", "type": "flow.end", "params": {}},
            ],
            edges=[
                {"id": "e1", "from": "n1", "to": "n2", "port": "out"},
                {"id": "e2", "from": "n2", "to": "n3", "port": "done"},
            ],
        )
        task = GraphTask(graph=graph, cancel_check=lambda: False)
        with self.assertRaises(ValueError) as ctx:
            task.validate_input()
        self.assertIn("Etapa 4", str(ctx.exception))

    def test_grafo_invalido_levanta_value_error_na_validacao(self):
        graph = _base_graph(nodes=[{"id": "n1", "type": "flow.end", "params": {}}], edges=[])
        task = GraphTask(graph=graph, cancel_check=lambda: False)
        with self.assertRaises(ValueError):
            task.validate_input()


if __name__ == "__main__":
    unittest.main()
