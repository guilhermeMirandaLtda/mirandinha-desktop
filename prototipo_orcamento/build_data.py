"""
Regenera js/data.js e js/sql-wasm-inline.js a partir das fontes canônicas.
Rode sempre que editar sql/schema.sql, sql/seed.sql ou trocar o sql-wasm.wasm.

    python build_data.py
"""
import base64
import json
import pathlib

here = pathlib.Path(__file__).parent

wasm = (here / "js" / "sql-wasm.wasm").read_bytes()
(here / "js" / "sql-wasm-inline.js").write_text(
    "// Gerado de sql-wasm.wasm — permite rodar sem servidor (file://).\n"
    "window.SQL_WASM_BASE64 = " + json.dumps(base64.b64encode(wasm).decode()) + ";\n",
    encoding="utf-8",
)

schema = (here / "sql" / "schema.sql").read_text(encoding="utf-8")
seed = (here / "sql" / "seed.sql").read_text(encoding="utf-8")
(here / "js" / "data.js").write_text(
    "// Gerado de sql/schema.sql e sql/seed.sql — evita fetch() (bloqueado em file://).\n"
    "// Edite os .sql e rode: python build_data.py\n"
    "window.SCHEMA_SQL = " + json.dumps(schema) + ";\n"
    "window.SEED_SQL = " + json.dumps(seed) + ";\n",
    encoding="utf-8",
)
print("OK — js/sql-wasm-inline.js e js/data.js regenerados.")
