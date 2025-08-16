from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DB_URL = "sqlite:///./davi.db"

engine = create_engine(DB_URL, connect_args={"check_same_thread": False})

# Garantir integridade referencial no SQLite
with engine.connect() as con:
    con.exec_driver_sql("PRAGMA foreign_keys=ON;")

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()