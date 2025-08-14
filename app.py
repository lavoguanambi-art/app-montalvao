import streamlit as st
import pandas as pd
from sqlalchemy import text
from db import engine, init_db
from logic import distribute_daily, balances_by_bucket, goals_with_scores, attack_ready

st.set_page_config(page_title="Sistema Financeiro Local", layout="wide")
init_db()

st.title("💼 Sistema Financeiro Local — Baldes + Objetivos")

tab_dash, tab_dist, tab_buckets, tab_goals, tab_tx = st.tabs(["Dashboard", "Distribuição diária", "Baldes", "Objetivos", "Movimentações"])

# ===== Dashboard =====
with tab_dash:
    st.subheader("Visão Geral")
    with engine.begin() as conn:
        rows = balances_by_bucket(conn)
        df_bal = pd.DataFrame(rows, columns=["id","Balde","Saldo (R$)"])
        ataque_val = float(df_bal[df_bal['Balde']=="Nu PF Ataque"]["Saldo (R$)"].sum()) if not df_bal.empty else 0.0
        st.metric("Balde 'Nu PF Ataque' (R$)", f"R$ {ataque_val:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
        st.dataframe(df_bal[["Balde","Saldo (R$)"]], use_container_width=True)

        tgt_name, atk_bal, tgt_cost = attack_ready(conn)
        if tgt_name:
            col1, col2, col3 = st.columns(3)
            col1.metric("Objetivo Alvo (Avalanche)", tgt_name)
            col2.metric("Saldo Ataque", f"R$ {atk_bal:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
            col3.metric("Custo para Quitar", f"R$ {tgt_cost:,.2f}".replace(",", "X").replace(".", ",").replace("X","."))
            if atk_bal >= tgt_cost and tgt_cost > 0:
                st.success("✅ PRONTO PARA QUITAR este objetivo.")
        else:
            st.info("Cadastre objetivos na aba **Objetivos**.")

# ===== Distribuição diária =====
with tab_dist:
    st.subheader("Distribuição de entrada (rateio automático)")
    with st.form("daily_dist"):
        colA, colB, colC = st.columns([1,1,2])
        date = colA.date_input("Data")
        value = colB.number_input("Entrada do dia (R$)", min_value=0.0, step=50.0, format="%.2f")
        desc  = colC.text_input("Descrição (ex.: Caixa do dia)")
        store = st.text_input("Origem/Loja (Guanambi, Caetité, Escritório)")
        submitted = st.form_submit_button("Distribuir")
    if submitted and value > 0:
        alloc = distribute_daily(value, str(date), desc, store)
        st.success("Distribuição realizada.")
        st.dataframe(pd.DataFrame(alloc, columns=["bucket_id","Balde","Valor (R$)"]))

# ===== Baldes =====
with tab_buckets:
    st.subheader("Configuração de Baldes e Regras")
    with engine.begin() as conn:
        df = pd.read_sql("SELECT id, name, priority_pre, percentage, active FROM accounts WHERE kind='bucket' ORDER BY id", conn)
    st.write("Use 0..1 nos percentuais. Ex.: 0.60 = 60%")
    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    if st.button("Salvar alterações de baldes"):
        with engine.begin() as conn:
            for _, row in edited.iterrows():
                conn.execute(text(
                    "UPDATE accounts SET name=:n, priority_pre=:p, percentage=:pct, active=:a WHERE id=:id"
                ), {"n": row["name"], "p": int(row["priority_pre"]), "pct": float(row["percentage"]), "a": int(row["active"]), "id": int(row["id"])})
        st.success("Baldes atualizados.")

# ===== Objetivos =====
with tab_goals:
    st.subheader("Objetivos financeiros")
    with engine.begin() as conn:
        df_goals = pd.read_sql("SELECT id, name, goal_type, cost, monthly_relief, COALESCE(priority_weight,0) as priority_weight FROM goals ORDER BY id", conn)
    mode = st.radio("Estratégia de priorização", ["avalanche","snowball","custom"], horizontal=True)
    st.dataframe(df_goals, use_container_width=True)
    with st.form("new_goal"):
        c1,c2,c3 = st.columns(3)
        name = c1.text_input("Nome do objetivo")
        goal_type = c2.selectbox("Tipo", ["debt","savings"])
        cost = c3.number_input("Custo/Meta (R$)", min_value=0.0, step=100.0, format="%.2f")
        c4,c5,_ = st.columns(3)
        relief = c4.number_input("Alívio Mensal (R$) — dívidas", min_value=0.0, step=50.0, format="%.2f")
        weight = c5.number_input("Peso (custom)", min_value=0.0, step=1.0, format="%.2f")
        submitted_goal = st.form_submit_button("Adicionar objetivo")
    if submitted_goal and name and cost>0:
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO goals (name, goal_type, cost, monthly_relief, priority_weight) VALUES (:n,:t,:c,:r,:w)"
            ), {"n":name,"t":goal_type,"c":cost,"r":relief,"w":weight})
        st.success("Objetivo adicionado.")
    st.divider()
    st.caption("Ranking (maior prioridade no topo)")
    with engine.begin() as conn:
        ranked = goals_with_scores(conn, mode)
    if ranked:
        st.dataframe(pd.DataFrame(ranked, columns=["id","Nome","Tipo","Custo","Alívio","Score"]), use_container_width=True)
    else:
        st.info("Sem objetivos cadastrados.")

# ===== Movimentações =====
with tab_tx:
    st.subheader("Movimentações (entradas/saídas)")
    with engine.begin() as conn:
        df_tx = pd.read_sql("SELECT id, date, description, t_type, value, bucket_id, store FROM transactions ORDER BY date DESC, id DESC", conn)
    st.dataframe(df_tx, use_container_width=True, height=360)
    csv = df_tx.to_csv(index=False).encode("utf-8")
    st.download_button("Exportar CSV", data=csv, file_name="movimentacoes.csv", mime="text/csv")
