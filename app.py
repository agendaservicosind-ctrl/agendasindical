import streamlit as st
import psycopg2
import pandas as pd
from datetime import date, timedelta
import unicodedata
import hashlib
import secrets
import os

# ================= CONFIG =================
st.set_page_config(page_title="Sistema Sindicato", layout="wide")

DATABASE_URL = st.secrets["DATABASE_URL"]

# ================= CONEXÃO =================
def get_conn():
    return psycopg2.connect(DATABASE_URL)

# ================= SENHA =================
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${hashed}"

def check_password(provided: str, stored: str) -> bool:
    if not stored or '$' not in stored:
        return False
    salt, hashed = stored.split('$')
    return hashlib.sha256((salt + provided).encode()).hexdigest() == hashed

# ================= DB INIT =================
def init_db():
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE,
            password TEXT,
            tipo_acesso TEXT,
            senha_padrao INTEGER DEFAULT 1
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS socios (
            matricula TEXT,
            nome TEXT,
            empresa TEXT,
            telefone TEXT,
            tipo TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS prestadores (
            id SERIAL PRIMARY KEY,
            nome TEXT,
            unidade TEXT,
            tipo_servico TEXT
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS agendamentos (
            id SERIAL PRIMARY KEY,
            nome_socio TEXT,
            tipo_servico TEXT,
            unidade TEXT,
            prestador_nome TEXT,
            data_atendimento DATE,
            horario TEXT,
            status TEXT DEFAULT 'Pendente',
            diretor_solicitante TEXT,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        conn.commit()

# ================= MASTER =================
def garantir_master():
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("SELECT * FROM usuarios WHERE UPPER(username) = 'MASTER'")
        if not cur.fetchone():
            cur.execute("""
                INSERT INTO usuarios (username, password, tipo_acesso)
                VALUES (%s, %s, %s)
            """, ("MASTER", hash_password("Sindicato@2026!"), "Master"))
            conn.commit()

# ================= LOGIN =================
def login():
    st.title("Login - Sistema Sindicato")

    with st.form("login"):
        user = st.text_input("Usuário")
        pwd = st.text_input("Senha", type="password")

        if st.form_submit_button("Entrar"):
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute("SELECT username, password FROM usuarios WHERE UPPER(username)=%s",
                            (user.upper(),))
                data = cur.fetchone()

            if data and check_password(pwd, data[1]):
                st.session_state["user"] = data[0]
                st.success("Login OK")
                st.rerun()
            else:
                st.error("Senha incorreta")

# ================= APP =================
def app():
    st.sidebar.write(f"👤 {st.session_state['user']}")
    if st.sidebar.button("Sair"):
        st.session_state.clear()
        st.rerun()

    st.title("Sistema funcionando com banco em nuvem 🚀")

    # Exemplo de gravação
    if st.button("Criar agendamento teste"):
        with get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO agendamentos
                (nome_socio, tipo_servico, unidade, prestador_nome, data_atendimento, horario, diretor_solicitante)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, ("Teste", "Odontologia", "Sede", "João", date.today(), "10:00", "MASTER"))
            conn.commit()
        st.success("Gravado no banco!")

    # Listar
    with get_conn() as conn:
        df = pd.read_sql("SELECT * FROM agendamentos ORDER BY id DESC", conn)

    st.dataframe(df)

# ================= START =================
init_db()
garantir_master()

if "user" not in st.session_state:
    login()
else:
    app()
