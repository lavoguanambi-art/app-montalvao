import streamlit as st
import pandas as pd
from datetime import date, timedelta
import time, math
from hashlib import md5

from sqlalchemy.orm import Session
from sqlalchemy import select

from db import engine, SessionLocal, Base
from models import (
    User, Bucket, Giant, Movement, Bill,
    UserProfile, GiantPayment
)
from logic import compute_bucket_splits, payoff_efficiency

from babel.numbers import format_currency
from babel.dates   import format_date

# =========================
#  Helpers de formatação BR
# =========================
def money_br(v: float) -> str:
    try:
        return format_currency(v, 'BRL', locale='pt_BR')
    except Exception:
        s = f"{v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        return f"R$ {s}"

def date_br(d) -> str:
    try:
        return format_date(d, format='short', locale='pt_BR')  # dd/mm/aa
    except Exception:
        return d.strftime('%d/%m/%y')

def parse_money_br(s: str) -> float:
    if s is None: return 0.0
    s = s.strip().replace('.', '').replace(',', '.')
    try: return float(s)
    except Exception: return 0.0

# ==============
# App & CSS anim.
# ==============
st.set_page_config(page_title="APP DAVI", layout="wide")

def inject_animations():
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] { animation: fadeIn 600ms ease-out both; }
        @keyframes fadeIn { from {opacity:0;transform:translateY(6px);} to {opacity:1;transform:translateY(0);} }

        [data-testid="stAlert"]{ animation: slideIn .45s cubic-bezier(.2,.7,.2,1) both; }
        @keyframes slideIn { from {opacity:0;transform:translateX(-10px);} to {opacity:1;transform:translateX(0);} }

        button[kind="secondary"], button[kind="primary"] { transition: transform .06s ease, box-shadow .2s ease; }
        button[kind="secondary"]:active, button[kind="primary"]:active { transform: scale(0.98); }
        button:hover { box-shadow: 0 6px 16px rgba(0,0,0,.15); }

        .pulse { animation: pulse 2.1s ease-in-out infinite; }
        @keyframes pulse {
          0% { box-shadow: 0 0 0 0 rgba(255, 99, 132, .20); }
          70% { box-shadow: 0 0 0 12px rgba(255, 99, 132, 0); }
          100% { box-shadow: 0 0 0 0 rgba(255, 99, 132, 0); }
        }

        .stProgress > div > div {
          height: 14px; border-radius: 999px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
inject_animations()

# Bootstrap DB
Base.metadata.create_all(bind=engine)

def get_db() -> Session:
    return SessionLocal()

def get_or_create_user(db: Session, name: str) -> User:
    u = db.execute(select(User).where(User.name == name)).scalar_one_or_none()
    if u: return u
    u = User(name=name)
    db.add(u); db.commit(); db.refresh(u); return u

# ============
# Data loaders
# ============
def load_buckets(db: Session, user_id: int):
    return db.execute(select(Bucket).where(Bucket.user_id == user_id)).scalars().all()

def load_giants(db: Session, user_id: int):
    return db.execute(select(Giant).where(Giant.user_id == user_id)).scalars().all()

def load_movements(db: Session, user_id: int):
    return db.execute(
        select(Movement).where(Movement.user_id == user_id).order_by(Movement.date.desc())
    ).scalars().all()

def load_bills(db: Session, user_id: int):
    return db.execute(
        select(Bill).where(Bill.user_id == user_id).order_by(Bill.due_date.asc())
    ).scalars().all()

def get_profile(db: Session, user_id: int) -> UserProfile:
    prof = db.execute(select(UserProfile).where(UserProfile.user_id == user_id)).scalar_one_or_none()
    if not prof:
        prof = UserProfile(user_id=user_id, monthly_income=0.0, monthly_expense=0.0)
        db.add(prof); db.commit(); db.refresh(prof)
    return prof

# Aportes
def get_giant_payments(db: Session, user_id: int, giant_id: int):
    return db.execute(
        select(GiantPayment).where(
            GiantPayment.user_id == user_id,
            GiantPayment.giant_id == giant_id
        ).order_by(GiantPayment.date.desc(), GiantPayment.id.desc())
    ).scalars().all()

def get_giant_totals(db: Session, user_id: int, giant_id: int):
    pays = get_giant_payments(db, user_id, giant_id)
    total_paid = sum(p.amount for p in pays)
    return total_paid, pays

# Alertas
def check_due_alerts(db: Session, user_id: int, days: int = 3):
    today = date.today()
    bills = load_bills(db, user_id)
    overdue = [b for b in bills if (not b.paid and b.due_date < today)]
    due_soon = [b for b in bills if (not b.paid and today <= b.due_date <= today + timedelta(days=days))]
    return overdue, due_soon

def render_alerts(overdue, due_soon, money_fmt, date_fmt):
    has_any = False
    if overdue:
        has_any = True
        lines = [f"🔴 **{b.title}** — {money_fmt(b.amount)} — venceu em {date_fmt(b.due_date)}" for b in overdue]
        st.error("**Contas vencidas:**\n\n" + "\n\n".join(lines))
    if due_soon:
        has_any = True
        lines = [f"🟡 **{b.title}** — {money_fmt(b.amount)} — vence em {date_fmt(b.due_date)}" for b in due_soon]
        st.warning("**Vencendo em breve:**\n\n" + "\n\n".join(lines))
    if has_any:
        key_str = "|".join([f"o:{b.id}:{b.due_date}" for b in overdue] + [f"s:{b.id}:{b.due_date}" for b in due_soon])
        h = md5(key_str.encode()).hexdigest()
        if st.session_state.get("last_alerts_hash") != h:
            for b in overdue:
                st.toast(f"🔴 VENCIDA: {b.title} ({money_fmt(b.amount)}) — {date_fmt(b.due_date)}")
            for b in due_soon:
                st.toast(f"🟡 A VENCER: {b.title} ({money_fmt(b.amount)}) — {date_fmt(b.due_date)}")
            st.session_state["last_alerts_hash"] = h

# =========
# Sidebar
# =========
with st.sidebar:
    st.header("Usuário")
    name = st.text_input("Seu nome", value=st.session_state.get("user_name", "Gustavo"))
    if st.button("Entrar / Criar"):
        with get_db() as db:
            user = get_or_create_user(db, name.strip() or "Usuário")
            st.session_state["user_id"] = user.id
            st.session_state["user_name"] = user.name

    # Perfil financeiro
    if "user_id" in st.session_state:
        with get_db() as db:
            prof = get_profile(db, st.session_state["user_id"])
            inc_str = st.text_input("Receita mensal (R$)", value=str(prof.monthly_income).replace('.', ','))
            exp_str = st.text_input("Despesa mensal (R$)", value=str(prof.monthly_expense).replace('.', ','))
            if st.button("Salvar receita/despesa"):
                inc = parse_money_br(inc_str)
                exp = parse_money_br(exp_str)
                prof.monthly_income = inc
                prof.monthly_expense = exp
                db.commit()
                st.success("Valores salvos!")

    # Preferências de alerta
    st.subheader("Alertas")
    alert_days = st.number_input(
        "Avisar quando faltar até (dias)", min_value=1, max_value=30,
        value=int(st.session_state.get("alert_window", 3))
    )
    st.session_state["alert_window"] = int(alert_days)

    st.markdown("---")
    page = st.radio("Navegação", [
        "Dashboard", "Plano de Ataque", "Baldes", "Entrada Diária",
        "Livro Caixa", "Calendário", "Atrasos & Riscos", "Configurações"
    ])

user_id = st.session_state.get("user_id", None)
if not user_id:
    st.info("👈 Informe o seu **nome** e clique em **Entrar / Criar** para começar.")
    st.stop()

# Alertas globais ao entrar
with get_db() as _db_alert:
    ov, ds = check_due_alerts(_db_alert, user_id, days=st.session_state.get("alert_window", 3))
    render_alerts(ov, ds, money_fmt=money_br, date_fmt=date_br)

# ======
# Páginas
# ======
if page == "Dashboard":
    st.title("📊 Dashboard")
    with get_db() as db:
        buckets = load_buckets(db, user_id)
        giants  = load_giants(db, user_id)
        movs    = load_movements(db, user_id)
        total_balance = sum(b.balance for b in buckets)

        # Métricas mensais e totais (Livro Caixa)
        today = date.today()
        month_movs = [m for m in movs if m.date.month == today.month and m.date.year == today.year]
        total_income_val  = sum(m.amount for m in movs if m.kind == 'income')
        total_expense_val = sum(m.amount for m in movs if m.kind in ('expense', 'transfer'))
        month_income  = sum(m.amount for m in month_movs if m.kind == 'income')
        month_expense = sum(m.amount for m in month_movs if m.kind in ('expense', 'transfer'))

        # Perfil declarado
        prof = get_profile(db, user_id)
        renda_decl = prof.monthly_income
        desp_decl  = prof.monthly_expense
        margem     = max(renda_decl - desp_decl, 0.0)

        col1, col2, col3, col4, col5, col6, col7, col8 = st.columns(8)
        with col1:
            st.markdown('<div class="pulse" style="padding:6px;border-radius:12px;">', unsafe_allow_html=True)
            st.metric("Saldo total nos Baldes", money_br(total_balance))
            st.markdown('</div>', unsafe_allow_html=True)
        with col2:
            st.metric("Receitas (mês)", money_br(month_income))
        with col3:
            st.metric("Despesas/Transf. (mês)", money_br(month_expense))
        with col4:
            st.metric("Receitas (total)", money_br(total_income_val))
        with col5:
            st.metric("Despesas/Transf. (total)", money_br(total_expense_val))
        with col6:
            active = [g for g in giants if g.status == "active"]
            st.metric("Gigantes ativos", len(active))
        with col7:
            st.metric("Receita mensal", money_br(renda_decl))
        with col8:
            st.metric("Despesa mensal", money_br(desp_decl))

        if buckets:
            df_b = pd.DataFrame([{"Balde": b.name, "%": b.percent, "Saldo": money_br(b.balance)} for b in buckets])
            st.subheader("Distribuição por Balde")
            st.dataframe(df_b, use_container_width=True)

        if giants:
            giants_sorted = sorted(giants, key=lambda g: (g.priority, -g.total_to_pay))
            df_g = pd.DataFrame([{
                "Gigante": g.name, "Total a Quitar": money_br(g.total_to_pay),
                "Prioridade": g.priority, "Status": g.status
            } for g in giants_sorted])
            st.subheader("Gigantes")
            st.dataframe(df_g, use_container_width=True)

        defeated = [g for g in giants if g.status == "defeated"]
        st.caption(f"Vitórias: {len(defeated)} — Margem p/ atacar: {money_br(margem)}")

elif page == "Plano de Ataque":
    st.title("🛡️ Plano de Ataque — Gigantes")
    with get_db() as db:
        with st.form("novo_gigante"):
            st.subheader("Novo Gigante")
            name_g = st.text_input("Nome", placeholder="Ex.: Cartão X")
            total_str   = st.text_input("Total a Quitar (R$)", value="")
            total       = parse_money_br(total_str) if total_str else 0.0
            parcels     = st.number_input("Parcelas", min_value=0, step=1, value=0)
            months_left = st.number_input("Meses restantes", min_value=0, step=1, value=0)
            priority    = st.number_input("Prioridade (1=maior)", min_value=1, step=1, value=1)
            submitted   = st.form_submit_button("Adicionar")
            if submitted and name_g.strip():
                g = Giant(user_id=user_id, name=name_g.strip(), total_to_pay=total,
                          parcels=parcels, months_left=months_left, priority=priority, status="active")
                db.add(g); db.commit()
                st.success("Gigante criado!")

        giants = load_giants(db, user_id)
        if giants:
            giants_sorted = sorted(giants, key=lambda g: (g.priority, -g.total_to_pay))
            st.subheader("Seus Gigantes")
            for g in giants_sorted:
                with st.expander(f"{g.name} — {money_br(g.total_to_pay)} | prioridade {g.priority} | status {g.status}"):
                    monthly_str   = st.text_input(f"Aporte mensal para {g.name} (R$)", value="", key=f"mi_{g.id}")
                    monthly_input = parse_money_br(monthly_str) if monthly_str else 0.0
                    if monthly_input > 0:
                        eff = payoff_efficiency(g, monthly_input)
                        st.write(f"Eficiência (R$/1k): {eff['r_per_1k']}")
                        st.write(f"Meses até a vitória: {eff['months_to_victory']}")

                    # Totais/lançamentos deste gigante
                    total_paid, pays = get_giant_totals(db, user_id, g.id)
                    remaining = max(g.total_to_pay - total_paid, 0.0)
                    st.markdown(
                        f"**Total a quitar:** {money_br(g.total_to_pay)}  \n"
                        f"**Total aportado:** {money_br(total_paid)}  \n"
                        f"**Saldo restante:** {money_br(remaining)}"
                    )

                    # Progresso animado
                    progress = min(total_paid / g.total_to_pay, 1.0) if g.total_to_pay > 0 else 0.0
                    st.markdown(f"**Progresso:** {int(progress*100)}%")
                    prog = st.progress(0)
                    target = int(progress * 100)
                    for i in range(0, target+1, max(1, math.ceil(max(target,1)/20))):
                        prog.progress(i/100); time.sleep(0.01)
                    prog.progress(progress)
                    st.markdown(
                        f'<div class="pulse" style="padding:10px;border-radius:14px;border:1px solid rgba(255,99,132,.25);margin-top:6px;">'
                        f'🎯 <b>Saldo restante:</b> {money_br(remaining)}'
                        f'</div>',
                        unsafe_allow_html=True
                    )

                    # Formulário de aporte
                    with st.form(f"pay_{g.id}"):
                        pay_str  = st.text_input("Aporte para este Gigante (R$)", value="", key=f"pay_str_{g.id}")
                        pay_val  = parse_money_br(pay_str) if pay_str else 0.0
                        pay_date = st.date_input("Data do aporte", value=date.today(), format="DD/MM/YY", key=f"pay_date_{g.id}")
                        pay_note = st.text_input("Observação (opcional)", value="", key=f"pay_note_{g.id}")
                        submit_pay = st.form_submit_button("Salvar Aporte")

                    if submit_pay:
                        if pay_val <= 0:
                            st.warning("Informe um valor de aporte maior que zero.")
                        else:
                            p = GiantPayment(user_id=user_id, giant_id=g.id, amount=pay_val, date=pay_date, note=pay_note)
                            db.add(p)
                            total_paid_after = total_paid + pay_val
                            if total_paid_after >= g.total_to_pay and g.status != "defeated":
                                g.status = "defeated"
                                db.commit()
                                st.success("🎉 Vitória! Gigante vencido.")
                                st.balloons()
                            else:
                                db.commit()
                                st.success("Aporte registrado com sucesso.")
                            total_paid, pays = get_giant_totals(db, user_id, g.id)
                            remaining = max(g.total_to_pay - total_paid, 0.0)
                            st.info(f"Atualizado • Total aportado: {money_br(total_paid)} • Saldo: {money_br(remaining)}")

                    # Histórico
                    if pays:
                        df_hist = pd.DataFrame(
                            [{"Data": date_br(p.date), "Valor": money_br(p.amount), "Obs": p.note} for p in pays[:5]]
                        )
                        st.write("Últimos aportes:")
                        st.table(df_hist)

elif page == "Baldes":
    st.title("🪣 Baldes")
    with get_db() as db:
        with st.form("novo_balde"):
            st.subheader("Adicionar Balde")
            name_b   = st.text_input("Nome do Balde", placeholder="Ex.: Operacional")
            desc_b   = st.text_input("Descrição", placeholder="Opcional")
            percent_b= st.number_input("Percentual (%)", min_value=0.0, max_value=100.0, step=1.0)
            type_b   = st.text_input("Tipo", value="generic")
            submitted= st.form_submit_button("Salvar")
            if submitted and name_b.strip():
                b = Bucket(user_id=user_id, name=name_b.strip(), description=desc_b.strip(),
                           percent=percent_b, type=type_b, balance=0.0)
                db.add(b); db.commit()
                st.success("Balde salvo!")

        buckets = load_buckets(db, user_id)
        if buckets:
            total_percent = sum(b.percent for b in buckets)
            if total_percent < 0 or any(b.percent < 0 for b in buckets):
                st.error("Há percentuais negativos. Ajuste para continuar usando a divisão.")
            st.info(f"Percentuais atuais somam **{total_percent:.2f}%**. Se não for 100%, a divisão é normalizada na Entrada Diária.")
            if st.button("Normalizar percentuais para 100%"):
                if total_percent <= 0:
                    st.warning("Não é possível normalizar: soma é 0%.")
                else:
                    factor = 100.0 / total_percent
                    for b in buckets:
                        b.percent = round(b.percent * factor, 2)
                    db.commit()
                    st.success("Percentuais normalizados para 100%. Recarregue a página.")

            df_b = pd.DataFrame([{
                "ID": b.id, "Nome": b.name, "Descrição": b.description,
                "%": b.percent, "Tipo": b.type, "Saldo": money_br(b.balance)
            } for b in buckets])
            st.dataframe(df_b, use_container_width=True)

            st.subheader("Editar balde existente")
            ids = [b.id for b in buckets]
            sel = st.selectbox("Escolha o ID", ids) if ids else None
            if sel:
                b = next(x for x in buckets if x.id == sel)
                with st.form(f"edit_balde_{sel}"):
                    name_b2    = st.text_input("Nome", value=b.name)
                    desc_b2    = st.text_input("Descrição", value=b.description)
                    percent_b2 = st.number_input("Percentual (%)", min_value=0.0, max_value=100.0, step=1.0, value=float(b.percent))
                    type_b2    = st.text_input("Tipo", value=b.type)
                    confirm    = st.checkbox("Confirmar alterações")
                    saveb      = st.form_submit_button("Salvar alterações")
                    if saveb and confirm:
                        b.name, b.description, b.percent, b.type = name_b2, desc_b2, percent_b2, type_b2
                        db.commit(); st.success("Balde atualizado!")
                    elif saveb and not confirm:
                        st.warning("Confirme as alterações para salvar.")

            # Apagar balde 🗑️
            st.subheader("Apagar balde 🗑️")
            del_id = st.selectbox("Escolha o ID para apagar", ids, key="del_bucket_id") if buckets else None
            if del_id:
                b_del = next(x for x in buckets if x.id == del_id)
                st.warning(
                    f"Você está prestes a apagar o balde **{b_del.name}** (ID {b_del.id}). "
                    f"Saldo atual: {money_br(b_del.balance)}. "
                    "Os lançamentos existentes continuarão no Livro Caixa, mas ficarão sem vínculo de balde."
                )
                force   = st.checkbox("Confirmo que entendo e desejo apagar este balde mesmo assim.")
                type_ok = st.text_input('Digite "APAGAR" para confirmar', value="", key="confirm_del_bucket")
                if st.button("Apagar balde", type="secondary"):
                    if type_ok.strip().upper() != "APAGAR":
                        st.error("Confirmação inválida. Digite exatamente APAGAR.")
                    elif not force and b_del.balance != 0:
                        st.error("Este balde possui saldo. Marque a confirmação para prosseguir.")
                    else:
                        db.delete(b_del); db.commit()
                        st.success("Balde apagado com sucesso.")
                        st.rerun()

elif page == "Entrada Diária":
    st.title("📥 Entrada Diária")
    with get_db() as db:
        buckets = load_buckets(db, user_id)
        if not buckets:
            st.warning("Crie baldes primeiro.")
        else:
            d = st.date_input("Data", value=date.today(), format="DD/MM/YY")
            val_str = st.text_input("Valor total recebido (ex.: 10.249,00)", value="")
            val = parse_money_br(val_str) if val_str else 0.0
            if st.button("Dividir e Lançar"):
                if val <= 0:
                    st.warning("Informe um valor maior que zero.")
                else:
                    splits = compute_bucket_splits(buckets, val)
                    for s in splits:
                        m = Movement(user_id=user_id, bucket_id=s["bucket_id"], kind="income",
                                     amount=s["value"], description="Entrada diária", date=d)
                        db.add(m)
                        b = db.get(Bucket, s["bucket_id"])
                        if b and b.user_id == user_id:
                            b.balance += s["value"]
                    db.commit()
                    st.success("Entrada lançada e dividida entre os baldes.")
                    df = pd.DataFrame([{"Balde": s["name"], "% efetivo": s["percent_effective"], "Valor": money_br(s["value"])} for s in splits])
                    st.table(df)

elif page == "Livro Caixa":
    st.title("📗 Livro Caixa")
    with get_db() as db:
        st.subheader("Nova movimentação")
        kind = st.selectbox("Tipo", ["income", "expense", "transfer"], index=0)
        buckets_all = load_buckets(db, user_id)
        ids = [b.id for b in buckets_all]
        if not ids:
            st.warning("Crie ao menos um balde para lançar no Livro Caixa.")
            st.stop()
        allow_negative = st.checkbox("Permitir saldo negativo no(s) balde(s)", value=False)

        if kind == "transfer":
            orig = st.selectbox("Balde de origem", ids)
            dest = st.selectbox("Balde de destino", ids, index=0 if len(ids) < 2 else 1)
            val_str = st.text_input("Valor (R$)", value="")
            val = parse_money_br(val_str) if val_str else 0.0
            d = st.date_input("Data", value=date.today(), format="DD/MM/YY")
            desc = st.text_input("Descrição", value="Transferência entre baldes")
            if st.button("Transferir"):
                if val > 0 and orig != dest:
                    b_orig = db.get(Bucket, orig)
                    b_dest = db.get(Bucket, dest)
                    if b_orig and b_dest:
                        if not allow_negative and b_orig.balance - val < 0:
                            st.error("Saldo insuficiente no balde de origem (desmarque o bloqueio para permitir negativo).")
                        else:
                            m_out = Movement(user_id=user_id, bucket_id=orig, kind="transfer", amount=val, description=desc+" (saída)", date=d)
                            m_in  = Movement(user_id=user_id, bucket_id=dest, kind="income",   amount=val, description=desc+" (entrada)", date=d)
                            db.add(m_out); db.add(m_in)
                            b_orig.balance -= val; b_dest.balance += val
                            db.commit(); st.success("Transferência realizada.")
                else:
                    st.warning("Informe um valor > 0 e selecione baldes diferentes.")
        else:
            bucket_id = st.selectbox("Balde", ids)
            val_str = st.text_input("Valor (R$)", value="")
            val = parse_money_br(val_str) if val_str else 0.0
            d = st.date_input("Data", value=date.today(), format="DD/MM/YY")
            desc = st.text_input("Descrição", value="")
            if st.button("Lançar"):
                if val > 0 and bucket_id:
                    m = Movement(user_id=user_id, bucket_id=bucket_id, kind=kind, amount=val, description=desc, date=d)
                    db.add(m)
                    b = db.get(Bucket, bucket_id)
                    if b and b.user_id == user_id:
                        if kind == "income":
                            b.balance += val
                        elif kind in ("expense", "transfer"):
                            if not allow_negative and b.balance - val < 0:
                                st.error("Saldo insuficiente no balde selecionado (desmarque o bloqueio para permitir negativo).")
                                db.rollback(); st.stop()
                            else:
                                b.balance -= val
                    db.commit(); st.success("Movimentação lançada")
                else:
                    st.warning("Informe um valor > 0 e selecione um balde.")

        movs = load_movements(db, user_id)
        if movs:
            df = pd.DataFrame([{
                "Data": date_br(m.date), "Tipo": m.kind, "BaldeID": m.bucket_id,
                "Valor": money_br(m.amount), "Descrição": m.description
            } for m in movs])
            st.dataframe(df, use_container_width=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button("Exportar CSV", data=csv, file_name="livro_caixa.csv")
        else:
            st.info("Sem movimentações ainda.")

elif page == "Calendário":
    st.title("🗓️ Calendário de Despesas")
    with get_db() as db:
        with st.form("nova_conta"):
            title = st.text_input("Título", placeholder="Ex.: Cartão C6 - Fatura")
            amount_str = st.text_input("Valor (R$)", value="")
            amount = parse_money_br(amount_str) if amount_str else 0.0
            due = st.date_input("Vencimento", value=date.today(), format="DD/MM/YY")
            critical = st.checkbox("Crítica (cartão/ empréstimo/ consórcio)")
            submitted = st.form_submit_button("Adicionar")
            if submitted and title.strip():
                b = Bill(user_id=user_id, title=title.strip(), amount=amount, due_date=due, is_critical=critical, paid=False)
                db.add(b); db.commit()
                st.success("Conta adicionada.")

        bills = load_bills(db, user_id)
        if bills:
            df = pd.DataFrame([{
                "ID": b.id, "Título": b.title, "Valor": money_br(b.amount),
                "Vencimento": date_br(b.due_date), "Crítica": b.is_critical, "Paga": b.paid
            } for b in bills])
            st.dataframe(df, use_container_width=True)

            st.subheader("Editar conta")
            ids = [b.id for b in bills]
            sel = st.selectbox("Escolha o ID", ids) if ids else None
            if sel:
                b = next(x for x in bills if x.id == sel)
                with st.form(f"edit_bill_{sel}"):
                    title2 = st.text_input("Título", value=b.title)
                    amount2_str = st.text_input("Valor (R$)", value=str(b.amount).replace('.', ','))
                    amount2 = parse_money_br(amount2_str) if amount2_str else b.amount
                    due2 = st.date_input("Vencimento", value=b.due_date, format="DD/MM/YY")
                    critical2 = st.checkbox("Crítica", value=b.is_critical)
                    paid2 = st.checkbox("Paga", value=b.paid)
                    confirm = st.checkbox("Confirmar alterações")
                    sb = st.form_submit_button("Salvar alterações")
                    if sb and confirm:
                        b.title, b.amount, b.due_date, b.is_critical, b.paid = title2, amount2, due2, critical2, paid2
                        db.commit(); st.success("Conta atualizada!")
                    elif sb and not confirm:
                        st.warning("Confirme as alterações marcando a caixa.")

elif page == "Atrasos & Riscos":
    st.title("⏰ Atrasos & Riscos")
    today = date.today()
    with get_db() as db:
        bills = load_bills(db, user_id)
        overdue = [b for b in bills if (not b.paid and b.due_date < today)]
        due_soon = [b for b in bills if (not b.paid and today <= b.due_date <= today + timedelta(days=3))]

        # Reforço de alertas aqui também
        render_alerts(overdue, due_soon, money_fmt=money_br, date_fmt=date_br)

        st.subheader("Vencidas")
        if overdue:
            df1 = pd.DataFrame([{
                "ID": b.id, "Título": b.title, "Valor": money_br(b.amount),
                "Venceu em": date_br(b.due_date), "Crítica": b.is_critical, "Paga": b.paid
            } for b in overdue])
            st.dataframe(df1, use_container_width=True)
            ids1 = [b.id for b in overdue]
            sel1 = st.selectbox("ID vencida", ids1) if ids1 else None
            if sel1:
                b = next(x for x in bills if x.id == sel1)
                with st.form(f"edit_overdue_{sel1}"):
                    title2 = st.text_input("Título", value=b.title)
                    amount2_str = st.text_input("Valor (R$)", value=str(b.amount).replace('.', ','))
                    amount2 = parse_money_br(amount2_str) if amount2_str else b.amount
                    due2 = st.date_input("Vencimento", value=b.due_date, format="DD/MM/YY")
                    critical2 = st.checkbox("Crítica", value=b.is_critical)
                    paid2 = st.checkbox("Paga", value=b.paid)
                    confirm = st.checkbox("Confirmar alterações")
                    sb = st.form_submit_button("Salvar")
                    if sb and confirm:
                        b.title, b.amount, b.due_date, b.is_critical, b.paid = title2, amount2, due2, critical2, paid2
                        db.commit(); st.success("Atualizada!")
                    elif sb and not confirm:
                        st.warning("Confirme as alterações marcando a caixa.")
        else:
            st.write("Sem contas vencidas.")

        st.subheader("Vencendo em até 3 dias")
        if due_soon:
            df2 = pd.DataFrame([{
                "ID": b.id, "Título": b.title, "Valor": money_br(b.amount),
                "Vencimento": date_br(b.due_date), "Crítica": b.is_critical, "Paga": b.paid
            } for b in due_soon])
            st.dataframe(df2, use_container_width=True)
            ids2 = [b.id for b in due_soon]
            sel2 = st.selectbox("ID a vencer", ids2) if ids2 else None
            if sel2:
                b = next(x for x in bills if x.id == sel2)
                with st.form(f"edit_duesoon_{sel2}"):
                    title2 = st.text_input("Título", value=b.title)
                    amount2_str = st.text_input("Valor (R$)", value=str(b.amount).replace('.', ','))
                    amount2 = parse_money_br(amount2_str) if amount2_str else b.amount
                    due2 = st.date_input("Vencimento", value=b.due_date, format="DD/MM/YY")
                    critical2 = st.checkbox("Crítica", value=b.is_critical)
                    paid2 = st.checkbox("Paga", value=b.paid)
                    confirm = st.checkbox("Confirmar alterações")
                    sb = st.form_submit_button("Salvar")
                    if sb and confirm:
                        b.title, b.amount, b.due_date, b.is_critical, b.paid = title2, amount2, due2, critical2, paid2
                        db.commit(); st.success("Atualizada!")
                    elif sb and not confirm:
                        st.warning("Confirme as alterações marcando a caixa.")
        else:
            st.write("Sem contas críticas nos próximos 3 dias.")

elif page == "Configurações":
    st.title("⚙️ Configurações")
    st.write("Altere o usuário ativo pela barra lateral.")
    with get_db() as db:
        if st.button("Reset (apagar tudo)"):
            db.query(Bill).delete()
            db.query(Movement).delete()
            db.query(GiantPayment).delete()
            db.query(Giant).delete()
            db.query(Bucket).delete()
            db.query(UserProfile).delete()
            db.query(User).delete()
            db.commit()
            st.session_state.pop("user_id", None)
            st.session_state.pop("user_name", None)
            st.success("Banco limpo. Recarregue e crie um novo usuário.")