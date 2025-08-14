from sqlalchemy import text
from db import engine
from typing import Dict

def get_rules(conn) -> Dict[str, str]:
    rows = conn.execute(text("SELECT key, value FROM rules")).fetchall()
    return {r[0]: r[1] for r in rows}

def get_buckets(conn):
    return conn.execute(text(
        "SELECT id, name, priority_pre, percentage "
        "FROM accounts WHERE kind='bucket' AND active=1 "
        "ORDER BY priority_pre DESC, id ASC"
    )).fetchall()

def add_transaction(conn, tx: dict):
    keys = ",".join(tx.keys())
    placeholders = ":" + ",:".join(tx.keys())
    conn.execute(text(f"INSERT INTO transactions ({keys}) VALUES ({placeholders})"), tx)

def balances_by_bucket(conn):
    rows = conn.execute(text("""
      SELECT a.id, a.name,
             COALESCE(SUM(CASE WHEN t.t_type='in'  THEN t.value WHEN t.t_type='transfer' THEN t.value ELSE 0 END),0) -
             COALESCE(SUM(CASE WHEN t.t_type='out' THEN t.value END),0) AS balance
      FROM accounts a
      LEFT JOIN transactions t ON t.bucket_id = a.id
      WHERE a.kind='bucket' AND a.active=1
      GROUP BY a.id, a.name
      ORDER BY a.id
    """)).fetchall()
    return rows

def distribute_daily(value: float, date: str, description: str = "Entrada diária", store: str = None):
    """
    1) Aplica buckets com priority_pre = 1 (ex.: Dízimo 10%) sobre o valor total (prioridade).
    2) Redistribui o restante proporcionalmente entre os demais buckets, respeitando seus percentuais.
    """
    with engine.begin() as conn:
        buckets = get_buckets(conn)

        allocated = []
        remaining = value

        # 1) Prioridade (ex.: dízimo)
        for b in buckets:
            b_id, b_name, priority_pre, pct = b
            if priority_pre:
                amount = round(value * float(pct), 2)
                allocated.append((b_id, b_name, amount))
                remaining -= amount
                add_transaction(conn, {
                    'date': date, 'description': f"{description} — {b_name} (prioridade)",
                    't_type': 'in', 'value': amount,
                    'account_id': None, 'bucket_id': b_id, 'goal_id': None, 'store': store
                })

        # 2) Distribuição do restante proporcional aos não prioritários
        non_prior = [(b[0], b[1], float(b[3])) for b in buckets if not b[2]]
        total_pct = sum(p for _,_,p in non_prior) or 1.0

        for b_id, b_name, pct in non_prior:
            amount = round(remaining * (pct / total_pct), 2)
            allocated.append((b_id, b_name, amount))
            add_transaction(conn, {
                'date': date, 'description': f"{description} — {b_name}",
                't_type': 'in', 'value': amount,
                'account_id': None, 'bucket_id': b_id, 'goal_id': None, 'store': store
            })

        return allocated

def goals_with_scores(conn, strategy: str = 'avalanche'):
    rows = conn.execute(text(
        "SELECT id, name, goal_type, cost, monthly_relief, COALESCE(priority_weight,0) FROM goals"
    )).fetchall()
    scored = []
    for r in rows:
        gid, name, gtype, cost, relief, weight = r
        if strategy == 'avalanche' and cost > 0:
            score = (relief or 0.0) / cost  # Payoff Efficiency (alívio por R$1)
        elif strategy == 'snowball':
            score = -cost                   # menor custo primeiro
        else:
            score = weight                  # custom
        scored.append((gid, name, gtype, cost, relief, score))
    scored.sort(key=lambda x: x[-1], reverse=True)
    return scored

def attack_ready(conn):
    """
    Retorna (nome_objetivo_alvo, saldo_ataque, custo_alvo)
    Alvo = melhor segundo 'avalanche'. Mostra 'PRONTO PARA QUITAR' se saldo_ataque >= custo_alvo.
    """
    ranked = goals_with_scores(conn, 'avalanche')
    if not ranked:
        return None, 0.0, 0.0
    gid, name, gtype, cost, relief, score = ranked[0]
    attack_bucket = conn.execute(text("SELECT id FROM accounts WHERE name='Nu PF Ataque' LIMIT 1")).fetchone()
    if not attack_bucket:
        return None, 0.0, cost
    bid = attack_bucket[0]
    bal = conn.execute(text("""
      SELECT COALESCE(SUM(CASE WHEN t.t_type='in' THEN t.value WHEN t.t_type='transfer' THEN t.value ELSE 0 END),0) -
             COALESCE(SUM(CASE WHEN t.t_type='out' THEN t.value END),0) AS balance
      FROM transactions t WHERE t.bucket_id=:bid
    """), {'bid': bid}).scalar() or 0.0
    return name, bal, cost
