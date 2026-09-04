"""
Gera sql/seed.sql a partir da aba "LISTA TÉC" da planilha real.

Modelo por FAMÍLIA: COD_ERP = <letra de perfil> + <família>.
  I... -> ODI (instalação)     D... -> ODD (retirada)     M... -> ODM (manutenção)
IEBT106 e DEBT106 são a mesma família 'EBT106'. Para cada família curada,
extraímos TODAS as variantes existentes (I e D) com seus componentes reais.

    python build_seed.py                       # caminho padrão da planilha
    python build_seed.py "D:\\...\\arquivo.xlsx"

Depois: python build_data.py
"""
import hashlib
import pathlib
import re
import sys

import openpyxl

XLSX = sys.argv[1] if len(sys.argv) > 1 else r"E:\NOVO TOMBAMENTO MA 2022-09-21.xlsx"
ABA = "LISTA TÉC"
HERE = pathlib.Path(__file__).parent

# Famílias curadas (sem a letra de perfil). Cada uma existe em I e D na planilha.
FAM_PRINCIPAL = [
    "EMT007", "EMT008", "EMT009", "EMT010", "EMT011", "EMT012",   # B1/B2/B3/B4 34,5 kV
    "EMT014", "EMT015", "EMT016", "EMT017", "EMT018", "EMT019",   # N1/N2/N4 25 e 13,8 kV
    "POS.011", "POS.012", "POS.015", "POS.016",                    # postes 11 e 12 m
]
FAM_CONEXAO = ["CXMT100", "CXMT101", "CXMT102"]                    # conexão por bitola
FAM_FIXACAO = ["FCMT200", "FCMT201", "FCMT202", "FCMT203",         # laço topo (N1/B1)
               "FCMT205", "FCMT206", "FCMT207", "FCMT208"]         # laço lateral (N2/B2)
FAMILIAS = set(FAM_PRINCIPAL) | set(FAM_CONEXAO) | set(FAM_FIXACAO)

PERFIL_LETRA = {"I": "ODI", "D": "ODD", "M": "ODM"}
GRUPO_TIPO = {"CONEX MT": "CONEXAO", "CONEX BT": "CONEXAO",
              "FIX CB MT": "FIXACAO", "FIX CB BT": "FIXACAO"}

EMPRESAS = [(1, "DPL (SUL)"), (2, "CELTA"), (3, "EQUATORIAL SERVICOS")]
FATOR_EMPRESA = {1: 1.00, 2: 1.12, 3: 0.94}

PARAMS = [
    ("capacidade_veiculo_kg", 27000, "Carga máxima por veículo de transporte"),
    ("custo_km", 3.62, "R$ por km rodado por veículo (a calibrar)"),
    ("pct_engenharia", 0.536, "Engenharia e supervisão: % sobre (material + serviço)"),
]
KM = [
    ("ACAILANDIA", "IMPERATRIZ", 67), ("AMARANTE", "IMPERATRIZ", 115),
    ("BALSAS", "IMPERATRIZ", 193), ("BURITICUPU", "IMPERATRIZ", 227),
    ("CAROLINA", "BALSAS", 166), ("DAVINOPOLIS", "IMPERATRIZ", 15),
    ("ESTREITO", "IMPERATRIZ", 125), ("GRAJAU", "IMPERATRIZ", 251),
    ("IMPERATRIZ", "IMPERATRIZ", 15), ("JOAO LISBOA", "IMPERATRIZ", 11),
    ("MONTES ALTOS", "IMPERATRIZ", 64), ("PORTO FRANCO", "IMPERATRIZ", 97),
    ("SITIO NOVO", "IMPERATRIZ", 110), ("SENADOR LA ROQUE", "IMPERATRIZ", 30),
]


def _rng(s):
    return int(hashlib.md5(s.encode("utf-8")).hexdigest()[:8], 16) / 0xFFFFFFFF


def preco_material(cod, desc, un):
    d = (desc or "").upper()
    r = _rng("mat" + cod)
    if "POSTE" in d:
        base, spread, peso = 1100, 1400, 780
    elif "TRAFO" in d:
        base, spread, peso = 8000, 9000, 360
    elif "CRUZETA" in d:
        base, spread, peso = 120, 110, 40
    elif "ISOLADOR" in d:
        base, spread, peso = 35, 60, 3.4
    elif "PARA-RAIO" in d or "PARA RAIO" in d:
        base, spread, peso = 90, 90, 2.2
    elif "CHAVE" in d:
        base, spread, peso = 180, 200, 3.6
    elif any(k in d for k in ("LACO", "LAÇO", "CONECT", "PINO", "MANILHA", "GANCHO", "OLHAL")):
        base, spread, peso = 12, 26, 0.4
    elif un and un.upper() == "KG":
        base, spread, peso = 14, 20, 1.0
    elif any(k in d for k in ("PARAFUSO", "ARRUELA", "PORCA")):
        base, spread, peso = 2, 6, 0.25
    else:
        base, spread, peso = 8, 30, 0.5
    return round(base + spread * r, 2), round(peso * (0.7 + 0.6 * _rng("p" + cod)), 3)


def preco_servico(cod, desc):
    d = (desc or "").upper()
    r = _rng("srv" + cod)
    if "POSTE" in d:
        return round(280 + 160 * r, 2)
    if "RETIRAR" in d:
        return round(80 + 120 * r, 2)
    return round(120 + 160 * r, 2)


def q(v):
    if v is None:
        return "NULL"
    return "'" + str(v).replace("'", "''").strip() + "'"


def main():
    ws = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)[ABA]

    kits = {}       # cod_erp -> {grupo, familia, perfil, desc, comps}
    materiais, servicos = {}, {}

    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or all(v is None for v in row):
            continue
        cod_erp = row[2]
        if not cod_erp:
            continue
        m = re.match(r"^([IDM])(.+)$", cod_erp)
        if not m or m.group(2) not in FAMILIAS:
            continue
        k = kits.setdefault(cod_erp, {
            "grupo": (row[1] or "").strip(), "familia": m.group(2),
            "perfil": PERFIL_LETRA[m.group(1)], "desc": (row[3] or "").strip(), "comps": []})
        ind = 1 if row[0] == 1 else 0
        ap = row[11]
        if row[4]:
            c = str(row[4]).strip()
            materiais.setdefault(c, (row[5], row[7]))
            k["comps"].append(("M", ind, c, row[5], row[7], float(row[6] or 0), ap))
        if row[8]:
            c = str(row[8]).strip()
            servicos.setdefault(c, row[9])
            k["comps"].append(("S", ind, c, row[9], "UN", float(row[10] or 0), ap))

    fams_ok = {k["familia"] for k in kits.values()}
    faltando = FAMILIAS - fams_ok
    if faltando:
        print("AVISO: famílias sem nenhuma variante na planilha:", sorted(faltando))

    out = ["-- GERADO por build_seed.py a partir de", f"--   {XLSX}  /  aba {ABA}",
           "-- Estrutura e códigos REAIS; preços sintéticos determinísticos.", ""]

    out.append("INSERT INTO tab_empresa (id,nome) VALUES")
    out.append(",\n".join(f"  ({i},{q(n)})" for i, n in EMPRESAS) + ";\n")

    out.append("INSERT INTO tab_param (chave,valor,descricao) VALUES")
    out.append(",\n".join(f"  ({q(c)},{v},{q(d)})" for c, v, d in PARAMS) + ";\n")

    out.append("INSERT INTO tab_km (municipio,origem,km) VALUES")
    out.append(",\n".join(f"  ({q(a)},{q(b)},{c})" for a, b, c in KM) + ";\n")

    out.append("INSERT INTO tab_preco_material (codigo,texto,un,preco,peso_kg) VALUES")
    out.append(",\n".join(
        f"  ({q(c)},{q(t)},{q(u or 'UN')},{preco_material(c, t, u)[0]},{preco_material(c, t, u)[1]})"
        for c, (t, u) in sorted(materiais.items())) + ";\n")

    out.append("INSERT INTO tab_preco_servico (codigo,empresa_id,texto,un,preco) VALUES")
    linhas = []
    for c, t in sorted(servicos.items()):
        base = preco_servico(c, t)
        for eid, f in FATOR_EMPRESA.items():
            linhas.append(f"  ({q(c)},{eid},{q(t)},'UN',{round(base * f, 2)})")
    out.append(",\n".join(linhas) + ";\n")

    # ordem: PRINCIPAL(I depois D), CONEXAO, FIXACAO — variante I antes da D
    ordem_fam = FAM_PRINCIPAL + FAM_CONEXAO + FAM_FIXACAO
    lista = []
    for fam in ordem_fam:
        for pre in ("I", "D", "M"):
            if pre + fam in kits:
                lista.append(pre + fam)
    ids = {c: i + 1 for i, c in enumerate(lista)}

    out.append("INSERT INTO tab_estrutura (id,tipo_kit,grupo_componente,cod_erp,familia,perfil,descricao,un) VALUES")
    linhas = []
    for c in lista:
        k = kits[c]
        tk = GRUPO_TIPO.get(k["grupo"], "PRINCIPAL")
        linhas.append(f"  ({ids[c]},{q(tk)},{q(k['grupo'])},{q(c)},{q(k['familia'])},"
                      f"{q(k['perfil'])},{q(k['desc'])},'KIT')")
    out.append(",\n".join(linhas) + ";\n")

    out.append("INSERT INTO tab_estrutura_componente")
    out.append("  (estrutura_id,ind_principal,tipo,codigo,texto,un,quantidade,tipo_aplicacao) VALUES")
    linhas, ncomp = [], 0
    for c in lista:
        for (tipo, ind, cc, txt, un, qt, ap) in kits[c]["comps"]:
            ncomp += 1
            linhas.append(f"  ({ids[c]},{ind},{q(tipo)},{q(cc)},{q(txt)},{q(un)},{qt},{q(ap)})")
    out.append(",\n".join(linhas) + ";\n")

    out.append("""INSERT INTO tab_projeto
  (id,nome,municipio,regional,empresa_id,pct_engenharia)
VALUES (1,'Novo orçamento','BURITICUPU','SUL',1,0.536);
""")

    (HERE / "sql" / "seed.sql").write_text("\n".join(out), encoding="utf-8")
    npri = sum(1 for c in lista if kits[c]["grupo"] not in GRUPO_TIPO)
    print(f"seed.sql: {len(lista)} estruturas ({len(fams_ok)} famílias) · {npri} PRINCIPAL · "
          f"{ncomp} componentes · {len(materiais)} materiais · {len(servicos)} serviços")


if __name__ == "__main__":
    main()
