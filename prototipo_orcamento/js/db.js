// Camada de banco do protótipo: SQLite real via sql.js (WASM), persistido no
// localStorage entre reloads e exportável como arquivo .sqlite.

const DB = (() => {
  const LS_KEY = 'orc_proto_db_v1';
  let SQL = null;
  let db = null;

  function bytesToB64(bytes) {
    let bin = '';
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
      bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return btoa(bin);
  }
  function b64ToBytes(b64) {
    const bin = atob(b64);
    const out = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
    return out;
  }

  // Persistência com debounce: exportar+base64 a cada escrita é caro em rajadas.
  let persistTimer = null;
  function persistNow() {
    try {
      localStorage.setItem(LS_KEY, bytesToB64(db.export()));
    } catch (e) {
      console.warn('Falha ao persistir no localStorage:', e);
    }
  }
  function persist() {
    clearTimeout(persistTimer);
    persistTimer = setTimeout(persistNow, 250);
  }
  window.addEventListener('beforeunload', () => { clearTimeout(persistTimer); persistNow(); });

  // Versão do schema lida do próprio DDL (PRAGMA user_version), fonte única.
  function schemaVersion() {
    const m = (window.SCHEMA_SQL || '').match(/user_version\s*=\s*(\d+)/i);
    return m ? +m[1] : 0;
  }
  function dbVersion(d) {
    try {
      const r = d.exec('PRAGMA user_version');
      return (r[0] && r[0].values[0][0]) || 0;
    } catch { return 0; }
  }

  let reseeded = null;   // null = carregou o salvo; string = motivo da recriação

  async function init({ reseed = false } = {}) {
    if (!SQL) {
      // wasm embutido (js/sql-wasm-inline.js) → funciona em file:// e http://
      const cfg = window.SQL_WASM_BASE64
        ? { wasmBinary: b64ToBytes(window.SQL_WASM_BASE64) }
        : { locateFile: f => 'js/' + f };
      SQL = await initSqlJs(cfg);
    }
    reseeded = null;

    const esperada = schemaVersion();
    const saved = reseed ? null : localStorage.getItem(LS_KEY);
    if (saved) {
      let cand = null;
      try {
        cand = new SQL.Database(b64ToBytes(saved));
        const v = dbVersion(cand);
        if (v === esperada) {
          db = cand;
          if (window.CacheBump) window.CacheBump();
          return;
        }
        cand.close();
        reseeded = `schema ${v} → ${esperada}`;
      } catch (e) {
        try { if (cand) cand.close(); } catch {}
        reseeded = 'banco salvo ilegível';
      }
      console.info('Recriando o banco (' + reseeded + ').');
    }
    db = new SQL.Database();
    // schema/seed vêm de js/data.js (gerado); fallback para fetch se ausente
    const schema = window.SCHEMA_SQL || await fetch('sql/schema.sql').then(r => r.text());
    const seed = window.SEED_SQL || await fetch('sql/seed.sql').then(r => r.text());
    db.run(schema);
    db.run(seed);
    if (window.CacheBump) window.CacheBump();
    persistNow();
  }

  // SELECT -> array de objetos {coluna: valor}
  function all(sql, params = []) {
    const stmt = db.prepare(sql);
    try {
      stmt.bind(params);
      const rows = [];
      while (stmt.step()) rows.push(stmt.getAsObject());
      return rows;
    } finally {
      stmt.free();
    }
  }
  function one(sql, params = []) {
    const r = all(sql, params);
    return r.length ? r[0] : null;
  }
  function scalar(sql, params = []) {
    const r = one(sql, params);
    return r ? Object.values(r)[0] : null;
  }
  // INSERT/UPDATE/DELETE — invalida cache do motor e persiste (debounced)
  function run(sql, params = []) {
    db.run(sql, params);
    if (window.CacheBump) window.CacheBump();
    persist();
  }
  function lastId() {
    return scalar('SELECT last_insert_rowid()');
  }

  function exportFile() {
    const blob = new Blob([db.export()], { type: 'application/octet-stream' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'orcamento_prototipo.sqlite';
    a.click();
    URL.revokeObjectURL(a.href);
  }
  async function importFile(file) {
    const buf = new Uint8Array(await file.arrayBuffer());
    db = new SQL.Database(buf);
    if (window.CacheBump) window.CacheBump();
    persistNow();
  }

  return {
    init, all, one, scalar, run, lastId, exportFile, importFile, persist,
    get reseeded() { return reseeded; },
    get schemaVersion() { return schemaVersion(); }
  };
})();
