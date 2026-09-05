"""
Isolamento do banco para a suíte de testes.

Sem isto, qualquer teste que chame save_studio_flow(), set_studio_flow_published() ou
record_job_execution() grava no mirandinha_history.db **real** do desenvolvedor: fluxos
de teste aparecem na galeria do Studio e — se o teste publicar algum — na Central de
Robôs como robôs executáveis de verdade. Já aconteceu; por isso este arquivo existe.

DB_PATH só é lido dentro de core/storage.py (sempre como global, em tempo de chamada),
então trocar o atributo do módulo redireciona a suíte inteira.
"""
import tempfile
from pathlib import Path

import pytest

import core.storage as storage


@pytest.fixture(autouse=True, scope="session")
def banco_de_testes_isolado():
    """Redireciona o SQLite para um arquivo temporário durante toda a sessão de testes."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="mirandinha_testes_"))
    tmp_db = tmp_dir / "teste_history.db"

    original_db_path = storage.DB_PATH
    storage.DB_PATH = str(tmp_db)

    yield str(tmp_db)

    storage.DB_PATH = original_db_path
    try:
        tmp_db.unlink(missing_ok=True)
        tmp_dir.rmdir()
    except Exception:
        pass  # o SO limpa o temp de qualquer jeito
