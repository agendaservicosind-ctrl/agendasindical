import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, timedelta
import unicodedata
import base64
import os
import io
import hashlib
import binascii

st.set_page_config(
    page_title="Sistema Sindicato",
    layout="wide",
    page_icon="logo.png",
    initial_sidebar_state="expanded"
)

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(DB_DIR, "sindicato.db")

SERVICOS = [
    "Odontologia", "Psicologia", "Jurídico", "Cabeleireiro", "Manicure",
    "Eletricista", "Jardineiro", "Pedreiro"
]

UNIDADES = [
    "Sede Jundiaí",
    "Sub Sede Franco da Rocha",
    "Externo Jundiaí",
    "Externo Franco da Rocha"
]

NIVEIS_ACESSO = ["Master", "ADM", "Recepção", "Prestador"]

HORARIOS = [f"{h:02d}:{m:02d}" for h in range(8, 18) for m in (0, 30)]

SENHA_INICIAL = "Sindicato@2026!"

# ─── FUNÇÕES DE SENHA ───────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = os.urandom(32)
    iterations = 100_000
    key = hashlib.pbkdf2_hmac('sha512', password.encode('utf-8'), salt, iterations, dklen=64)
    salt_hex = binascii.hexlify(salt).decode('ascii')
    key_hex = binascii.hexlify(key).decode('ascii')
    return f"pbkdf2_sha512${iterations}${salt_hex}${key_hex}"

def check_password(provided: str, stored) -> bool:
    if stored is None:
        return False
    if isinstance(stored, (bytes, bytearray)):
        try:
            stored = stored.decode('utf-8')
        except UnicodeDecodeError:
            stored = stored.decode('latin1', errors='replace')
    provided = str(provided).strip()
    stored = str(stored).strip()
    if not stored:
        return False
    if not stored.startswith("pbkdf2_sha512"):
        if '$' not in stored:
            return stored == provided
        try:
            salt, hashed = stored.split('$', 1)
            computed = hashlib.sha256((salt + provided).encode('utf-8')).hexdigest()
            return computed == hashed
        except:
            return False
    try:
        algo, iters_str, salt_hex, stored_hash = stored.split('$', 3)
        if algo != "pbkdf2_sha512":
            return False
        iterations = int(iters_str)
        salt = binascii.unhexlify(salt_hex)
        key = hashlib.pbkdf2_hmac('sha512', provided.encode('utf-8'), salt, iterations, dklen=64)
        return binascii.hexlify(key).decode('ascii') == stored_hash
    except:
        return False

# ─── AUXILIARES ─────────────────────────────────────────────────────────────────
def normalize_for_db(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    text = unicodedata.normalize('NFD', text.strip())
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return text.upper()

def normalize_matricula(mat: str) -> str:
    return str(mat or "").strip().replace(" ", "")

def limpar_cpf(valor):
    return "".join(c for c in str(valor or "") if c.isdigit())

def formatar_telefone(valor):
    valor = limpar_cpf(valor)
    if len(valor) == 11:
        return f"({valor[:2]}) {valor[2:7]}-{valor[7:]}"
    if len(valor) == 10:
        return f"({valor[:2]}) {valor[2:6]}-{valor[6:]}"
    return valor

# ─── BANCO DE DADOS ─────────────────────────────────────────────────────────────
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        cursor = conn.cursor()

        # socios
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS socios (
                matricula TEXT PRIMARY KEY,
                nome TEXT,
                empresa TEXT,
                cpf TEXT,
                telefone TEXT,
                tipo TEXT DEFAULT 'Titular'
            )
        ''')
        for coluna in ['empresa', 'cpf', 'telefone', 'tipo']:
            try:
                cursor.execute(f"ALTER TABLE socios ADD COLUMN {coluna} TEXT")
            except sqlite3.OperationalError:
                pass
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_matricula ON socios(matricula)")

        # usuarios
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                tipo_acesso TEXT NOT NULL,
                senha_padrao INTEGER DEFAULT 1
            )
        ''')

        # prestadores
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prestadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                cpf TEXT,
                unidade TEXT NOT NULL,
                tipo_servico TEXT NOT NULL
            )
        ''')

        # diretores
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS diretores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                cpf TEXT,
                area_responsavel TEXT,
                nivel_acesso TEXT,
                username TEXT,
                foto BLOB
            )
        ''')

        # agendamentos
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agendamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matricula_socio TEXT,
                nome_socio TEXT NOT NULL,
                empresa_socio TEXT,
                telefone_socio TEXT,
                tipo_servico TEXT NOT NULL,
                unidade TEXT NOT NULL,
                prestador_nome TEXT NOT NULL,
                data_atendimento TEXT NOT NULL,
                horario TEXT NOT NULL,
                status TEXT DEFAULT 'Pendente',
                diretor_solicitante TEXT NOT NULL,
                criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                data_realizado TIMESTAMP,
                validado_por TEXT
            )
        ''')
        try:
            cursor.execute("ALTER TABLE agendamentos ADD COLUMN data_realizado TIMESTAMP")
        except:
            pass
        try:
            cursor.execute("ALTER TABLE agendamentos ADD COLUMN validado_por TEXT")
        except:
            pass

        # Cria MASTER apenas se NÃO existir (não sobrescreve mais)
        cursor.execute("SELECT 1 FROM usuarios WHERE username = 'MASTER'")
        if not cursor.fetchone():
            master_hash = hash_password(SENHA_INICIAL)
            cursor.execute("""
                INSERT INTO usuarios 
                (username, password, tipo_acesso, senha_padrao)
                VALUES ('MASTER', ?, 'Master', 1)
            """, (master_hash,))
            conn.commit()
            st.info("Usuário MASTER criado pela primeira vez com senha inicial.")

def corrigir_coluna_foto():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(diretores)")
        colunas = {col[1] for col in cursor.fetchall()}
        if 'foto' not in colunas:
            cursor.execute("ALTER TABLE diretores ADD COLUMN foto BLOB")
            conn.commit()

init_db()
corrigir_coluna_foto()

if 'user_data' not in st.session_state:
    st.session_state.user_data = None
if 'forcar_troca_senha' not in st.session_state:
    st.session_state.forcar_troca_senha = False

# ─── LOGIN ──────────────────────────────────────────────────────────────────────
if st.session_state.user_data is None:
    st.title("Login - Sistema Sindicato")
    with st.form("login_form"):
        username = st.text_input("Usuário").strip().upper()
        password = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            if not username:
                st.error("Digite o usuário.")
            elif not password:
                st.error("Digite a senha.")
            else:
                with sqlite3.connect(DB_NAME) as conn:
                    user = conn.execute(
                        "SELECT username, password, tipo_acesso, senha_padrao "
                        "FROM usuarios WHERE username = ?",
                        (username,)
                    ).fetchone()
                if user:
                    stored_username, stored_password, stored_tipo, senha_padrao = user
                    
                    # DEBUG VISÍVEL (mantenha até funcionar)
                    st.info(f"**DEBUG** - Usuário encontrado: `{stored_username}`")
                    st.info(f"**DEBUG** - Tipo do campo password: `{type(stored_password)}`")
                    if isinstance(stored_password, str):
                        st.info(f"**DEBUG** - Hash armazenado (início):")
                        st.code(stored_password[:120] + "..." if len(stored_password) > 120 else stored_password)
                    elif isinstance(stored_password, bytes):
                        st.info(f"**DEBUG** - Hash como bytes (início):")
                        st.code(repr(stored_password[:80]))
                    st.info(f"**DEBUG** - senha_padrao (1=inicial): `{senha_padrao}`")

                    if check_password(password, stored_password):
                        st.session_state.user_data = {
                            "username": stored_username,
                            "tipo": stored_tipo.strip().lower(),
                        }
                        st.session_state.forcar_troca_senha = bool(senha_padrao)
                        if senha_padrao:
                            st.info("Sua senha é a inicial. Por segurança, altere-a agora.")
                        st.success("Login realizado com sucesso!")
                        st.rerun()
                    else:
                        st.error("Senha incorreta.")
                else:
                    st.error("Usuário não encontrado.")

# ─── ÁREA LOGADA ────────────────────────────────────────────────────────────────
else:
    user_info = st.session_state.user_data
    tipo_user = user_info["tipo"].lower()
    nome_user = user_info["username"]

    foto_bytes = None
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT foto FROM diretores WHERE username = ?", (nome_user,))
        result = cursor.fetchone()
        if result and result[0]:
            foto_bytes = result[0]

    with st.sidebar:
        if foto_bytes:
            foto_base64 = base64.b64encode(foto_bytes).decode('utf-8')
            col_foto, col_texto = st.columns([1, 3])
            with col_foto:
                st.markdown(
                    f"""
                    <div style="text-align:center; margin:10px 0;">
                        <img src="data:image/jpeg;base64,{foto_base64}"
                             style="width:80px; height:80px; border-radius:50%;
                                    object-fit:cover; border:3px solid #e0e0e0;
                                    box-shadow:0 4px 12px rgba(0,0,0,0.15);">
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            with col_texto:
                st.markdown(f"<h4 style='margin:12px 0 0 0;'>{nome_user.upper()}</h4>", unsafe_allow_html=True)
                st.markdown(f"<small>({tipo_user.upper()})</small>", unsafe_allow_html=True)
        else:
            st.markdown(f"👤 **{nome_user.upper()}** ({tipo_user.upper()})")
        st.markdown("---")

    if st.session_state.forcar_troca_senha:
        st.title("Alterar Senha Inicial (obrigatório)")
        st.warning(f"Olá {nome_user.upper()}, defina uma nova senha agora.")
        with st.form("form_troca_senha"):
            nova_senha = st.text_input("Nova senha", type="password")
            confirma = st.text_input("Confirmar nova senha", type="password")
            if st.form_submit_button("Confirmar", type="primary"):
                if not nova_senha or len(nova_senha) < 6:
                    st.error("A senha deve ter pelo menos 6 caracteres.")
                elif nova_senha != confirma:
                    st.error("As senhas não coincidem.")
                elif nova_senha == SENHA_INICIAL:
                    st.error("Não use a senha inicial novamente.")
                else:
                    hashed = hash_password(nova_senha)
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("UPDATE usuarios SET password = ?, senha_padrao = 0 WHERE username = ?",
                                     (hashed, nome_user))
                        conn.commit()
                    st.success("Senha alterada com sucesso! Faça login novamente.")
                    st.session_state.user_data = None
                    st.session_state.forcar_troca_senha = False
                    st.rerun()

    else:
        # Menus de navegação
        if tipo_user == "prestador":
            menu = ["Meus Agendamentos", "Sair"]
        else:
            menu = ["Agendar", "Atendimentos"]
            if tipo_user in ["master", "adm", "recepção"]:
                menu.extend(["Prestadores", "Diretoria"])
            if tipo_user in ["master", "adm"]:
                menu.append("Importar Sócios")
            if tipo_user == "master":
                menu.extend(["Relatório de Serviços", "Redefinir Senhas"])
            menu.append("Sair")

        escolha = st.sidebar.radio("Navegação", menu)

        if escolha == "Sair":
            st.session_state.user_data = None
            st.rerun()

        # ─── AGENDAR ────────────────────────────────────────────────────────────────
        if escolha == "Agendar":
            st.title("Novo Agendamento")
            busca = st.text_input("Busca do Sócio ou Dependente (Matrícula ou Nome)")
            socio_encontrado = None
            if busca.strip():
                busca_limpa = normalize_matricula(busca.strip())
                busca_nome = f"%{normalize_for_db(busca.strip())}%"
                with sqlite3.connect(DB_NAME) as conn:
                    rows = conn.execute("""
                        SELECT matricula, nome, empresa, telefone, tipo
                        FROM socios
                        WHERE matricula = ?
                        ORDER BY CASE WHEN tipo = 'Titular' THEN 0 ELSE 1 END, nome
                    """, (busca_limpa,)).fetchall()
                    if not rows:
                        rows = conn.execute("""
                            SELECT matricula, nome, empresa, telefone, tipo
                            FROM socios
                            WHERE UPPER(nome) LIKE ? OR matricula LIKE ?
                            ORDER BY CASE WHEN tipo = 'Titular' THEN 0 ELSE 1 END, nome
                        """, (busca_nome, f"%{busca_limpa}%")).fetchall()
                if rows:
                    st.info(f"Encontrados {len(rows)} registros.")
                    if len(rows) == 1:
                        socio_encontrado = rows[0]
                        st.success(f"Encontrado: {socio_encontrado[1]} ({socio_encontrado[4]})")
                    else:
                        opcoes = []
                        for r in rows:
                            tipo_txt = "Titular" if r[4] == "Titular" else "Dependente"
                            opcoes.append(f"{r[1]} ({tipo_txt}) – Matr. {r[0]}")
                        escolha_idx = st.radio("Selecione:", range(len(opcoes)), format_func=lambda i: opcoes[i])
                        socio_encontrado = rows[escolha_idx]
                else:
                    st.warning("Nenhum sócio ou dependente encontrado.")
            if socio_encontrado:
                mat, nome_def, emp_def, tel_def_db, tipo_pessoa = socio_encontrado
                tel_def = formatar_telefone(tel_def_db) if tel_def_db else ""
                campos_disabled = True
                nao_associado = False
                st.caption(f"**Tipo:** {tipo_pessoa}")
            elif busca.strip():
                mat = "N/A"
                nome_def = emp_def = tel_def = ""
                campos_disabled = False
                nao_associado = True
            else:
                mat = nome_def = emp_def = tel_def = ""
                campos_disabled = False
                nao_associado = False
            st.markdown("---")
            col1, col2 = st.columns(2)
            servico = col1.selectbox("Serviço solicitado", SERVICOS)
            unidade = col2.selectbox("Unidade de atendimento", UNIDADES)
            with sqlite3.connect(DB_NAME) as conn:
                serv_norm = normalize_for_db(servico)
                uni_norm = normalize_for_db(unidade)
                if "Externo" in unidade:
                    query = "SELECT nome FROM prestadores WHERE tipo_servico = ? ORDER BY nome"
                    params = (serv_norm,)
                else:
                    query = "SELECT nome FROM prestadores WHERE unidade = ? AND tipo_servico = ? ORDER BY nome"
                    params = (uni_norm, serv_norm)
                result = conn.execute(query, params).fetchall()
                lista_prestadores = [r[0].strip() for r in result if r and r[0] and r[0].strip()]
            prestador = None
            if lista_prestadores:
                prestador = st.selectbox("Prestador / Responsável", lista_prestadores)
            else:
                st.warning(f"Nenhum prestador para {servico} na {unidade}.")
            st.markdown("---")
            with st.form("form_agendamento", clear_on_submit=True):
                col1, col2 = st.columns(2)
                nome = col1.text_input("Nome completo", value=nome_def, disabled=campos_disabled)
                empresa = col2.text_input("Empresa / Local de trabalho", value=emp_def, disabled=campos_disabled)
                telefone_raw = col1.text_input("Telefone para contato", value=tel_def, disabled=campos_disabled)
                telefone = limpar_cpf(telefone_raw)
                data_atendimento = col2.date_input("Data do atendimento", min_value=date.today(),
                                                   max_value=date.today() + timedelta(days=120))
                horario = col1.selectbox("Horário disponível", HORARIOS)
                diretor_solicitante = col2.text_input("Diretor solicitante", value=nome_user, disabled=True)
                pode_agendar_manual = tipo_user in ["master", "adm", "recepção"]
                submit_disabled = (nao_associado and not pode_agendar_manual) or (prestador is None)
                if nao_associado and not pode_agendar_manual:
                    st.warning("Apenas Master, ADM ou Recepção podem agendar para não associados.")
                if st.form_submit_button("Confirmar Agendamento", type="primary", disabled=submit_disabled):
                    if not nome.strip():
                        st.error("Nome obrigatório.")
                    elif prestador is None:
                        st.error("Selecione um prestador válido.")
                    else:
                        data_iso = data_atendimento.strftime("%Y-%m-%d")
                        with sqlite3.connect(DB_NAME) as conn:
                            conflito = conn.execute("""
                                SELECT 1 FROM agendamentos
                                WHERE prestador_nome = ?
                                  AND data_atendimento = ?
                                  AND horario = ?
                                  AND status NOT IN ('Cancelado', 'Realizado')
                            """, (prestador, data_iso, horario)).fetchone()
                            if conflito:
                                st.error(f"Conflito de horário com {prestador}.")
                            else:
                                conn.execute("""
                                    INSERT INTO agendamentos
                                    (matricula_socio, nome_socio, empresa_socio, telefone_socio,
                                     tipo_servico, unidade, prestador_nome, data_atendimento, horario, diretor_solicitante)
                                    VALUES (?,?,?,?,?,?,?,?,?,?)
                                """, (
                                    mat if mat != "N/A" else None,
                                    nome.strip(),
                                    empresa.strip() or None,
                                    telefone or None,
                                    servico,
                                    unidade,
                                    prestador,
                                    data_iso,
                                    horario,
                                    diretor_solicitante
                                ))
                                conn.commit()
                                st.success("Agendamento registrado!")
                                st.rerun()

        # ─── ATENDIMENTOS / MEUS AGENDAMENTOS ───────────────────────────────────────
        elif escolha in ["Atendimentos", "Meus Agendamentos"]:
            if tipo_user == "prestador":
                st.title("Meus Agendamentos")
            else:
                st.title("Lista de Atendimentos")
            filtro_status = st.selectbox("Filtrar por status", ["Todos", "Pendente", "Realizado", "Cancelado"])
            with sqlite3.connect(DB_NAME) as conn:
                query = """
                    SELECT id, nome_socio, tipo_servico, unidade, data_atendimento, horario, status, diretor_solicitante
                    FROM agendamentos
                    WHERE 1=1
                """
                params = []
                if tipo_user == "prestador":
                    query += " AND prestador_nome = ?"
                    params.append(nome_user)
                if filtro_status != "Todos":
                    query += " AND status = ?"
                    params.append(filtro_status)
                query += " ORDER BY data_atendimento DESC, horario DESC"
                df = pd.read_sql_query(query, conn, params=params)
            if df.empty:
                st.info("Nenhum agendamento encontrado.")
            else:
                df["Data"] = pd.to_datetime(df["data_atendimento"]).dt.strftime("%d/%m/%Y")
                df = df.drop(columns=["data_atendimento"])
                if tipo_user == "prestador":
                    for _, row in df.iterrows():
                        if row["status"] == "Pendente":
                            cols = st.columns([5, 1])
                            with cols[0]:
                                st.write(f"**{row['nome_socio']}** – {row['tipo_servico']} | {row['unidade']} | {row['Data']} {row['horario']}")
                            with cols[1]:
                                if st.button("✓ Marcar como Realizado", key=f"realizar_{row['id']}"):
                                    with sqlite3.connect(DB_NAME) as conn:
                                        conn.execute("""
                                            UPDATE agendamentos
                                            SET status = 'Realizado',
                                                data_realizado = CURRENT_TIMESTAMP,
                                                validado_por = ?
                                            WHERE id = ?
                                        """, (nome_user, row['id']))
                                        conn.commit()
                                    st.success("Atendimento marcado como Realizado!")
                                    st.rerun()
                        else:
                            st.markdown(f"**{row['nome_socio']}** – {row['tipo_servico']} | {row['unidade']} | {row['Data']} {row['horario']} **({row['status']})**")
                        st.markdown("---")
                else:
                    st.dataframe(df, use_container_width=True)

        # ─── PRESTADORES ────────────────────────────────────────────────────────────
        elif escolha == "Prestadores" and tipo_user in ["master", "adm", "recepção"]:
            st.title("Gestão de Prestadores")
            with st.expander("Cadastrar novo prestador"):
                with st.form("cad_prestador", clear_on_submit=True):
                    nome_p = st.text_input("Nome completo do prestador")
                    cpf_p = st.text_input("CPF (opcional)")
                    unidade_p = st.selectbox("Unidade", UNIDADES)
                    servico_p = st.selectbox("Serviço", SERVICOS)
                    username_p = st.text_input("Nome de usuário para login")
                    if st.form_submit_button("Cadastrar Prestador + Acesso"):
                        if nome_p.strip() and username_p.strip():
                            unidade_norm = normalize_for_db(unidade_p)
                            servico_norm = normalize_for_db(servico_p)
                            username_clean = username_p.strip().upper()
                            conn = sqlite3.connect(DB_NAME)
                            try:
                                conn.execute("BEGIN TRANSACTION")
                                conn.execute("""
                                    INSERT INTO prestadores (nome, cpf, unidade, tipo_servico)
                                    VALUES (?, ?, ?, ?)
                                """, (nome_p.strip(), limpar_cpf(cpf_p), unidade_norm, servico_norm))
                                cursor = conn.cursor()
                                cursor.execute("SELECT 1 FROM usuarios WHERE username = ?", (username_clean,))
                                if cursor.fetchone():
                                    raise ValueError("Usuário já existe. Escolha outro nome.")
                                senha_hash = hash_password(SENHA_INICIAL)
                                conn.execute("""
                                    INSERT INTO usuarios (username, password, tipo_acesso, senha_padrao)
                                    VALUES (?, ?, 'Prestador', 1)
                                """, (username_clean, senha_hash))
                                conn.commit()
                                st.success(f"Prestador cadastrado!\nUsuário: **{username_clean}**\nSenha inicial: **{SENHA_INICIAL}**")
                                st.rerun()
                            except ValueError as ve:
                                conn.rollback()
                                st.error(str(ve))
                            except Exception as e:
                                conn.rollback()
                                st.error(f"Erro ao cadastrar: {str(e)}")
                            finally:
                                conn.close()
            with sqlite3.connect(DB_NAME) as conn:
                df_p = pd.read_sql_query("SELECT id, nome, cpf, unidade, tipo_servico FROM prestadores ORDER BY nome", conn)
            if df_p.empty:
                st.info("Nenhum prestador cadastrado.")
            else:
                for _, row in df_p.iterrows():
                    expander_key = f"prest_exp_{row['id']}"
                    with st.expander(f"{row['nome']} – {row['tipo_servico']} ({row['unidade']})"):
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            with st.form(f"edit_prest_{row['id']}"):
                                nome_edit = st.text_input("Nome", value=row['nome'], key=f"nome_edit_{row['id']}")
                                cpf_edit = st.text_input("CPF", value=row['cpf'] or "", key=f"cpf_edit_{row['id']}")
                                unidade_edit = st.selectbox("Unidade", UNIDADES, index=UNIDADES.index(row['unidade']), key=f"uni_edit_{row['id']}")
                                servico_edit = st.selectbox("Serviço", SERVICOS, index=SERVICOS.index(row['tipo_servico']), key=f"serv_edit_{row['id']}")
                                if st.form_submit_button("Salvar alterações", key=f"salvar_prest_{row['id']}"):
                                    unidade_norm = normalize_for_db(unidade_edit)
                                    servico_norm = normalize_for_db(servico_edit)
                                    with sqlite3.connect(DB_NAME) as conn:
                                        conn.execute("""
                                            UPDATE prestadores
                                            SET nome = ?, cpf = ?, unidade = ?, tipo_servico = ?
                                            WHERE id = ?
                                        """, (nome_edit.strip(), limpar_cpf(cpf_edit), unidade_norm, servico_norm, row['id']))
                                        conn.commit()
                                    st.success("Prestador atualizado!")
                                    st.rerun()
                        with col2:
                            if st.button("Excluir", key=f"del_btn_prest_{row['id']}"):
                                with sqlite3.connect(DB_NAME) as conn:
                                    cursor = conn.cursor()
                                    cursor.execute("SELECT nome FROM prestadores WHERE id = ?", (row['id'],))
                                    nome_prest_raw = cursor.fetchone()
                                    if nome_prest_raw:
                                        nome_prest_clean = nome_prest_raw[0].upper().replace(" ", "")
                                        conn.execute("DELETE FROM usuarios WHERE username = ?", (nome_prest_clean,))
                                    conn.execute("DELETE FROM prestadores WHERE id = ?", (row['id'],))
                                    conn.commit()
                                st.success("Prestador excluído!")
                                st.rerun()

        # ─── DIRETORIA ──────────────────────────────────────────────────────────────
        elif escolha == "Diretoria" and tipo_user in ["master", "adm", "recepção"]:
            st.title("Gestão da Diretoria")
            with st.expander("Cadastrar novo usuário (diretor)"):
                with st.form("cad_diretor"):
                    nome_d = st.text_input("Nome completo")
                    cpf_d = st.text_input("CPF (opcional)")
                    area_d = st.text_input("Área de responsabilidade (opcional)")
                    nivel_d = st.selectbox("Nível de acesso", NIVEIS_ACESSO)
                    usuario_d = st.text_input("Nome de usuário (login)")
                    foto_upload = st.file_uploader("Foto (opcional)", type=["jpg", "jpeg", "png"])
                    if st.form_submit_button("Cadastrar"):
                        if nome_d.strip() and usuario_d.strip():
                            foto_bytes = foto_upload.read() if foto_upload else None
                            conn = sqlite3.connect(DB_NAME)
                            try:
                                conn.execute("BEGIN TRANSACTION")
                                conn.execute("""
                                    INSERT INTO diretores (nome, cpf, area_responsavel, nivel_acesso, username, foto)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                """, (nome_d.strip(), limpar_cpf(cpf_d), area_d or None, nivel_d, usuario_d.strip(), foto_bytes))
                                senha_hash = hash_password(SENHA_INICIAL)
                                conn.execute("""
                                    INSERT INTO usuarios (username, password, tipo_acesso, senha_padrao)
                                    VALUES (?, ?, ?, 1)
                                """, (usuario_d.strip(), senha_hash, nivel_d))
                                conn.commit()
                                st.success("Usuário cadastrado! Senha inicial definida.")
                                st.rerun()
                            except sqlite3.IntegrityError:
                                conn.rollback()
                                st.error("Usuário já existe.")
                            except Exception as e:
                                conn.rollback()
                                st.error(f"Erro ao cadastrar: {str(e)}")
                            finally:
                                conn.close()
                        else:
                            st.error("Nome e usuário são obrigatórios.")
            with sqlite3.connect(DB_NAME) as conn:
                df_d = pd.read_sql_query("""
                    SELECT d.id, d.nome, d.cpf, d.area_responsavel, d.nivel_acesso, d.username,
                           u.senha_padrao, d.foto
                    FROM diretores d
                    LEFT JOIN usuarios u ON d.username = u.username
                    ORDER BY d.nome
                """, conn)
            if df_d.empty:
                st.info("Nenhum usuário cadastrado.")
            else:
                for _, row in df_d.iterrows():
                    titulo = f"{row['nome']} – {row['nivel_acesso']} ({row['username']})"
                    if row['senha_padrao']:
                        titulo += " (senha inicial)"
                    with st.expander(titulo):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            with st.form(f"edit_dir_{row['id']}"):
                                nome_edit = st.text_input("Nome", value=row['nome'])
                                cpf_edit = st.text_input("CPF", value=row['cpf'] or "")
                                area_edit = st.text_input("Área", value=row['area_responsavel'] or "")
                                nivel_edit = st.selectbox("Nível", NIVEIS_ACESSO,
                                                          index=NIVEIS_ACESSO.index(row['nivel_acesso']) if row['nivel_acesso'] in NIVEIS_ACESSO else 0)
                                foto_edit = st.file_uploader("Atualizar foto (opcional)", type=["jpg", "jpeg", "png"], key=f"foto_edit_{row['id']}")
                                if st.form_submit_button("Salvar alterações"):
                                    foto_bytes_edit = foto_edit.read() if foto_edit else None
                                    with sqlite3.connect(DB_NAME) as conn:
                                        if foto_bytes_edit is not None:
                                            conn.execute("""
                                                UPDATE diretores
                                                SET nome = ?, cpf = ?, area_responsavel = ?, nivel_acesso = ?, foto = ?
                                                WHERE id = ?
                                            """, (nome_edit.strip(), limpar_cpf(cpf_edit), area_edit or None, nivel_edit, foto_bytes_edit, row['id']))
                                        else:
                                            conn.execute("""
                                                UPDATE diretores
                                                SET nome = ?, cpf = ?, area_responsavel = ?, nivel_acesso = ?
                                                WHERE id = ?
                                            """, (nome_edit.strip(), limpar_cpf(cpf_edit), area_edit or None, nivel_edit, row['id']))
                                        conn.commit()
                                    st.success("Usuário atualizado!")
                                    st.rerun()
                        with col2:
                            if row['foto']:
                                foto_base64 = base64.b64encode(row['foto']).decode('utf-8')
                                st.markdown(
                                    f"""
                                    <div style="text-align:center; margin:10px 0;">
                                        <img src="data:image/jpeg;base64,{foto_base64}"
                                             style="width:150px; height:150px; border-radius:50%; object-fit:cover; border:3px solid #ddd;">
                                    </div>
                                    """,
                                    unsafe_allow_html=True
                                )
                            else:
                                st.markdown("<div style='text-align:center; color:#aaa;'>Sem foto</div>", unsafe_allow_html=True)

        # ─── IMPORTAR SÓCIOS ────────────────────────────────────────────────────────
        elif escolha == "Importar Sócios" and tipo_user in ["master", "adm"]:
            st.title("Importar Sócios e Dependentes")
            st.info("""
            Formato esperado:
            • Aba 'Sócio' → Col A: Matrícula | Col B: Nome | Col C: Empresa
            • Aba 'Dependentes' → Col A: Matrícula | Col B: Nome | Col C: Empresa (geralmente em branco)
            """)
            arquivo = st.file_uploader("Planilha Excel", type=["xlsx"])
            if arquivo:
                try:
                    xl = pd.ExcelFile(arquivo)
                    df_final = pd.DataFrame()
                    for aba, tipo in [("Sócio", "Titular"), ("Dependentes", "Dependente")]:
                        if aba in xl.sheet_names:
                            df = pd.read_excel(xl, sheet_name=aba, header=None, dtype=str)
                            df = df.iloc[:, :3].copy()
                            df.columns = ['matricula', 'nome', 'empresa']
                            df['tipo'] = tipo
                            df['matricula'] = df['matricula'].apply(normalize_matricula)
                            df['nome'] = df['nome'].astype(str).str.strip().str.upper()
                            df = df.dropna(subset=['matricula', 'nome'])
                            df_final = pd.concat([df_final, df], ignore_index=True)
                    if df_final.empty:
                        st.error("Nenhum dado válido.")
                    else:
                        st.subheader("Pré-visualização")
                        st.dataframe(df_final.head(10), use_container_width=True)
                        if st.button("Confirmar importação"):
                            with sqlite3.connect(DB_NAME) as conn:
                                df_final.to_sql("socios", conn, if_exists="replace", index=False)
                                conn.execute("CREATE INDEX IF NOT EXISTS idx_matricula ON socios(matricula)")
                            st.success(f"Importados {len(df_final)} registros!")
                            st.rerun()
                except Exception as e:
                    st.error(f"Erro ao processar planilha: {str(e)}")

        # ─── RELATÓRIO DE SERVIÇOS ─────────────────────────────────────────────────
        elif escolha == "Relatório de Serviços" and tipo_user == "master":
            st.title("Relatório de Serviços")
            with sqlite3.connect(DB_NAME) as conn:
                prestadores_df = pd.read_sql_query("SELECT DISTINCT nome FROM prestadores ORDER BY nome", conn)
                lista_prestadores = ["Todos"] + prestadores_df["nome"].tolist()
                diretores_df = pd.read_sql_query("SELECT DISTINCT diretor_solicitante FROM agendamentos WHERE diretor_solicitante IS NOT NULL ORDER BY diretor_solicitante", conn)
                lista_diretores = ["Todos"] + diretores_df["diretor_solicitante"].tolist()
            col1, col2, col3, col4 = st.columns(4)
            prestador_filtro = col1.selectbox("Prestador", lista_prestadores)
            diretor_filtro = col2.selectbox("Diretor solicitante", lista_diretores)
            data_inicio = col3.date_input("Data inicial", value=date.today() - timedelta(days=30))
            data_fim = col4.date_input("Data final", value=date.today())
            status_filtro = st.selectbox("Status", ["Todos", "Pendente", "Realizado", "Cancelado"])
            if st.button("Gerar Relatório", type="primary"):
                query = """
                    SELECT
                        data_atendimento AS "Data",
                        horario AS "Horário",
                        nome_socio AS "Nome",
                        CASE WHEN matricula_socio IS NULL THEN 'Não associado' ELSE matricula_socio END AS "Matrícula",
                        tipo_servico AS "Serviço",
                        unidade AS "Unidade",
                        prestador_nome AS "Prestador",
                        diretor_solicitante AS "Diretor",
                        status AS "Status",
                        criado_em AS "Criado em",
                        data_realizado AS "Validado em",
                        validado_por AS "Validado por"
                    FROM agendamentos
                    WHERE 1=1
                """
                params = []
                if prestador_filtro != "Todos":
                    query += " AND prestador_nome = ?"
                    params.append(prestador_filtro)
                if diretor_filtro != "Todos":
                    query += " AND diretor_solicitante = ?"
                    params.append(diretor_filtro)
                if data_inicio:
                    query += " AND data_atendimento >= ?"
                    params.append(data_inicio.strftime("%Y-%m-%d"))
                if data_fim:
                    query += " AND data_atendimento <= ?"
                    params.append(data_fim.strftime("%Y-%m-%d"))
                if status_filtro != "Todos":
                    query += " AND status = ?"
                    params.append(status_filtro)
                query += " ORDER BY data_atendimento DESC, horario DESC"
                with sqlite3.connect(DB_NAME) as conn:
                    df_relatorio = pd.read_sql_query(query, conn, params=params)
                if df_relatorio.empty:
                    st.info("Nenhum agendamento encontrado.")
                else:
                    df_display = df_relatorio.copy()
                    df_display["Data"] = pd.to_datetime(df_display["Data"]).dt.strftime("%d/%m/%Y")
                    df_display["Criado em"] = pd.to_datetime(df_display["Criado em"]).dt.strftime("%d/%m/%Y %H:%M")
                    if "Validado em" in df_display.columns:
                        df_display["Validado em"] = pd.to_datetime(df_display["Validado em"], errors='coerce').dt.strftime("%d/%m/%Y %H:%M")
                    st.dataframe(df_display, use_container_width=True, hide_index=True)

        # ─── REDEFINIR SENHAS ───────────────────────────────────────────────────────
        elif escolha == "Redefinir Senhas" and tipo_user == "master":
            st.title("Redefinir Senhas de Usuários")
            with sqlite3.connect(DB_NAME) as conn:
                df_usu = pd.read_sql_query("SELECT username, tipo_acesso FROM usuarios ORDER BY username", conn)
            for _, row in df_usu.iterrows():
                if st.button(f"Resetar senha de {row['username']} ({row['tipo_acesso']})", key=f"reset_{row['username']}"):
                    hashed = hash_password(SENHA_INICIAL)
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("UPDATE usuarios SET password = ?, senha_padrao = 1 WHERE username = ?",
                                     (hashed, row['username']))
                        conn.commit()
                    st.success(f"Senha de {row['username']} redefinida para a inicial.")
                    st.rerun()
