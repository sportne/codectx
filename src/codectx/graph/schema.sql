PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_version(version) VALUES (1);

CREATE TABLE IF NOT EXISTS repo (
  id INTEGER PRIMARY KEY,
  root_path TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS snapshot (
  id INTEGER PRIMARY KEY,
  repo_id INTEGER NOT NULL REFERENCES repo(id) ON DELETE CASCADE,
  indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  schema_version INTEGER NOT NULL,
  content_fingerprint TEXT
);

CREATE TABLE IF NOT EXISTS file (
  id INTEGER PRIMARY KEY,
  snapshot_id INTEGER NOT NULL REFERENCES snapshot(id) ON DELETE CASCADE,
  path TEXT NOT NULL,
  language TEXT,
  content_hash TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  line_count INTEGER NOT NULL,
  is_test INTEGER NOT NULL DEFAULT 0,
  is_generated INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(snapshot_id, path)
);

CREATE TABLE IF NOT EXISTS node (
  id INTEGER PRIMARY KEY,
  snapshot_id INTEGER NOT NULL REFERENCES snapshot(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  language TEXT,
  name TEXT,
  qualified_name TEXT,
  symbol_key TEXT,
  file_id INTEGER REFERENCES file(id) ON DELETE SET NULL,
  start_byte INTEGER,
  end_byte INTEGER,
  start_line INTEGER,
  end_line INTEGER,
  confidence REAL NOT NULL DEFAULT 1.0,
  extractor TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS edge (
  id INTEGER PRIMARY KEY,
  snapshot_id INTEGER NOT NULL REFERENCES snapshot(id) ON DELETE CASCADE,
  kind TEXT NOT NULL,
  src_node_id INTEGER REFERENCES node(id) ON DELETE CASCADE,
  dst_node_id INTEGER REFERENCES node(id) ON DELETE CASCADE,
  unresolved_src TEXT,
  unresolved_dst TEXT,
  file_id INTEGER REFERENCES file(id) ON DELETE SET NULL,
  start_byte INTEGER,
  end_byte INTEGER,
  start_line INTEGER,
  end_line INTEGER,
  confidence REAL NOT NULL DEFAULT 1.0,
  weight REAL NOT NULL DEFAULT 1.0,
  extractor TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  CHECK (src_node_id IS NOT NULL OR unresolved_src IS NOT NULL),
  CHECK (dst_node_id IS NOT NULL OR unresolved_dst IS NOT NULL OR kind IN ('contains', 'defines', 'declares', 'diagnostic_for'))
);

CREATE TABLE IF NOT EXISTS occurrence (
  id INTEGER PRIMARY KEY,
  file_id INTEGER NOT NULL REFERENCES file(id) ON DELETE CASCADE,
  node_id INTEGER REFERENCES node(id) ON DELETE SET NULL,
  role TEXT NOT NULL,
  text TEXT NOT NULL,
  start_byte INTEGER NOT NULL,
  end_byte INTEGER NOT NULL,
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  resolved_node_id INTEGER REFERENCES node(id) ON DELETE SET NULL,
  confidence REAL NOT NULL DEFAULT 1.0,
  extractor TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS chunk (
  id INTEGER PRIMARY KEY,
  file_id INTEGER NOT NULL REFERENCES file(id) ON DELETE CASCADE,
  node_id INTEGER REFERENCES node(id) ON DELETE SET NULL,
  kind TEXT NOT NULL,
  start_line INTEGER NOT NULL,
  end_line INTEGER NOT NULL,
  text TEXT NOT NULL,
  token_estimate INTEGER NOT NULL,
  score_hint REAL NOT NULL DEFAULT 0.0,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS diagnostic (
  id INTEGER PRIMARY KEY,
  snapshot_id INTEGER NOT NULL REFERENCES snapshot(id) ON DELETE CASCADE,
  file_id INTEGER REFERENCES file(id) ON DELETE CASCADE,
  start_byte INTEGER,
  end_byte INTEGER,
  start_line INTEGER,
  end_line INTEGER,
  severity TEXT NOT NULL,
  code TEXT,
  message TEXT NOT NULL,
  extractor TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS index_stat (
  id INTEGER PRIMARY KEY,
  snapshot_id INTEGER NOT NULL REFERENCES snapshot(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  UNIQUE(snapshot_id, key)
);

CREATE INDEX IF NOT EXISTS idx_file_snapshot_path ON file(snapshot_id, path);
CREATE INDEX IF NOT EXISTS idx_file_language ON file(language);
CREATE INDEX IF NOT EXISTS idx_node_snapshot_kind ON node(snapshot_id, kind);
CREATE INDEX IF NOT EXISTS idx_node_name ON node(name);
CREATE INDEX IF NOT EXISTS idx_node_qualified_name ON node(qualified_name);
CREATE INDEX IF NOT EXISTS idx_node_symbol_key ON node(symbol_key);
CREATE INDEX IF NOT EXISTS idx_node_file_range ON node(file_id, start_byte, end_byte);
CREATE INDEX IF NOT EXISTS idx_edge_src_kind ON edge(src_node_id, kind);
CREATE INDEX IF NOT EXISTS idx_edge_dst_kind ON edge(dst_node_id, kind);
CREATE INDEX IF NOT EXISTS idx_edge_snapshot_kind ON edge(snapshot_id, kind);
CREATE INDEX IF NOT EXISTS idx_occurrence_text ON occurrence(text);
CREATE INDEX IF NOT EXISTS idx_occurrence_file_range ON occurrence(file_id, start_byte, end_byte);
CREATE INDEX IF NOT EXISTS idx_chunk_file_node ON chunk(file_id, node_id);
CREATE INDEX IF NOT EXISTS idx_diagnostic_file ON diagnostic(file_id);
