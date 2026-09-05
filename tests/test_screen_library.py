"""
Testes da Biblioteca de Telas (Etapa 2).
Os testes do pack CN52N comparam contra os ids literais que estão hoje em
core/rpa/tasks/sap_zerar_compromisso.py — servem de teste de regressão: se alguém editar
o pack e ele divergir do robô nativo, este teste quebra.
"""
import unittest

from core.studio.screen_library import (
    list_packs, get_pack, get_element, resolve_candidates, list_elements,
)


class TestScreenLibrary(unittest.TestCase):
    def test_list_packs_inclui_os_quatro_promovidos(self):
        packs = {p["pack"] for p in list_packs()}
        self.assertEqual(packs, {"cn52n", "cj20n", "me52n", "mb22"})

    def test_cn52n_grid_alv_bate_com_o_codigo_original(self):
        candidates = resolve_candidates("cn52n", "grid_alv")
        self.assertEqual(candidates, ["wnd[0]/usr/cntlALVCONTAINER/shellcont/shell"])

    def test_cn52n_campo_quantidade_bate_com_o_codigo_original(self):
        candidates = resolve_candidates("cn52n", "campo_quantidade")
        self.assertEqual(candidates, [
            "wnd[0]/usr/subDETAIL_AREA:SAPLCNPB_M:1010/subVIEW_AREA:SAPLCOMD:2800/"
            "tabsTABSTRIP_2700/tabpMKAG/ssubSUBSCR_2700:SAPLCOMD:2701/txtRESBD-MENGE"
        ])

    def test_cj20n_input_bdter_bate_com_o_selector_original(self):
        candidates = resolve_candidates("cj20n", "input_bdter")
        self.assertEqual(candidates, ["wnd[1]/usr/ctxtRESBD-BDTER"])

    def test_mb22_chk_eliminar_bate_com_o_selector_original(self):
        candidates = resolve_candidates("mb22", "chk_eliminar")
        self.assertEqual(candidates, ["wnd[0]/usr/chkRESB-XLOEK"])

    def test_pack_inexistente_lista_os_disponiveis_na_mensagem(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            get_pack("mb52")
        self.assertIn("mb52", str(ctx.exception))
        self.assertIn("cn52n", str(ctx.exception))

    def test_elemento_inexistente_lista_os_disponiveis_na_mensagem(self):
        with self.assertRaises(KeyError) as ctx:
            get_element("cn52n", "campo_fantasma")
        self.assertIn("campo_quantidade", str(ctx.exception))

    def test_elemento_tem_rotulo_tela_e_tipo(self):
        el = get_element("cn52n", "campo_quantidade")
        self.assertEqual(el["rotulo"], "Quantidade (MENGE)")
        self.assertIn("tela", el)
        self.assertEqual(el["tipo"], "campo_texto")

    def test_list_elements_filtra_por_tipo(self):
        botoes = list_elements("cj20n", tipo="botao")
        self.assertTrue(len(botoes) > 0)
        self.assertTrue(all(b["tipo"] == "botao" for b in botoes))
        # o campo de data não deve aparecer no filtro de botão
        self.assertFalse(any(b["ref"] == "input_bdter" for b in botoes))

    def test_fallbacks_entram_na_lista_de_candidatos(self):
        # nenhum pack atual declara fallback ainda — confirma que a lista vem vazia por padrão
        candidates = resolve_candidates("mb22", "input_reserva")
        self.assertEqual(len(candidates), 1)


if __name__ == "__main__":
    unittest.main()
