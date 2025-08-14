from sqlalchemy import create_engine, text
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "finance.db")
engine = create_engine(f"sqlite:///{DB_PATH}", echo=False, future=True)

SCHEMA_SQL = """
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS accounts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,            -- 'bucket' | 'cash' | 'bank'
  priority_pre INTEGER DEFAULT 0,-- 1 = prioridade antes da distribuição (ex.: dízimo)
  percentage REAL DEFAULT 0,     -- 0..1
  active INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS goals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  goal_type TEXT NOT NULL,       -- 'debt' | 'savings'
  cost REAL NOT NULL,            -- custo para quitar / meta de acúmulo
  monthly_relief REAL DEFAULT 0, -- p/ dívidas: parcela/juros evitados (alívio mensal)
  interest_pa REAL,              -- juros ao ano (opcional)
  priority_weight REAL DEFAULT 0 -- para estratégia 'custom'
);

CREATE TABLE IF NOT EXISTS transactions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  description TEXT,
  t_type TEXT NOT NULL,          -- 'in' | 'out' | 'transfer'
  value REAL NOT NULL,
  account_id INTEGER,
  bucket_id INTEGER,             -- referência a accounts.id (tipo bucket)
  goal_id INTEGER,               -- opcional, vincular a um objetivo
  store TEXT,                    -- loja/origem
  FOREIGN KEY(account_id) REFERENCES accounts(id),
  FOREIGN KEY(bucket_id) REFERENCES accounts(id),
  FOREIGN KEY(goal_id) REFERENCES goals(id)
);

CREATE TABLE IF NOT EXISTS rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  key TEXT NOT NULL,             -- 'tithe_enabled', 'tithe_pct', etc.
  value TEXT NOT NULL
);

-- Defaults de regra
INSERT OR IGNORE INTO rules (id, key, value) VALUES
  (1, 'tithe_enabled', 'true'),
  (2, 'tithe_pct', '0.10');

-- Buckets padrão
INSERT OR IGNORE INTO accounts (id, name, kind, priority_pre, percentage, active) VALUES
  (1, 'Dízimo', 'bucket', 1, 0.10, 1),
  (2, 'Stone OPEX', 'bucket', 0, 0.60, 1),
  (3, 'BNB Empréstimos', 'bucket', 0, 0.20, 1),
  (4, 'NuPJ Cartões', 'bucket', 0, 0.15, 1),
  (5, 'Nu PF Ataque', 'bucket', 0, 0.05, 1);
"""

def init_db():
    with engine.begin() as conn:
        for stmt in SCHEMA_SQL.split(";"):
            s = stmt.strip()
            if s:
                conn.execute(text(s + ";"))