import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, timedelta
import unicodedata
import base64
import os
import io
import hashlib
import secrets

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

# ================== FUNÇÕES DE SENHA ==================
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()
    return f"{salt}${hashed}"

def check_password(provided: str, stored) -> bool:
    if stored is None:
        return False

    # Converte bytes para str (problema comum no Streamlit Cloud)
    if isinstance(stored, (bytes, bytearray)):
        try:
            stored = stored.decode('utf-8')
        except UnicodeDecodeError:
            return False

    stored = str(stored).strip()
    provided = str(provided).strip()

    if not stored:
        return False

    # Senha antiga em texto plano
    if '$' not in stored:
        return stored == provided

    # Formato salt$hash
    try:
        salt, hashed = stored.split('$', 1)
        computed = hashlib.sha256((salt + provided).encode('utf-8')).hexdigest()
        return computed == hashed
    except Exception:
        return False

# ================== FUNÇÕES AUXILIARES ==================
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

# ================== BANCO DE DADOS ==================
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS socios (
                matricula TEXT,
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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                tipo_acesso TEXT NOT NULL,
                senha_padrao INTEGER DEFAULT 1
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS prestadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                cpf TEXT,
                unidade TEXT NOT NULL,
                tipo_servico TEXT NOT NULL
            )
        ''')
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
        conn.commit()

def create_default_master_if_needed():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM usuarios WHERE username = 'master'")
        row = cursor.fetchone()

        senha_hash = hash_password(SENHA_INICIAL)

        if row is None:
            cursor.execute("""
                INSERT INTO usuarios (username, password, tipo_acesso, senha_padrao)
                VALUES ('master', ?, 'Master', 1)
            """, (senha_hash,))
            conn.commit()
            st.info("Usuário master criado com senha padrão.")
        else:
            # Força atualização para garantir que o hash seja compatível com o ambiente atual
            cursor.execute("""
                UPDATE usuarios 
                SET password = ?, senha_padrao = 1 
                WHERE username = 'master'
            """, (senha_hash,))
            conn.commit()
            st.info("Senha do master foi redefinida para padrão (Sindicato@2026!). Pode logar.")

def corrigir_coluna_foto():
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(diretores)")
        colunas = {col[1] for col in cursor.fetchall()}
        if 'foto' not in colunas:
            cursor.execute("ALTER TABLE diretores ADD COLUMN foto BLOB")
            conn.commit()

init_db()
create_default_master_if_needed()
corrigir_coluna_foto()

if 'user_data' not in st.session_state:
    st.session_state.user_data = None
if 'forcar_troca_senha' not in st.session_state:
    st.session_state.forcar_troca_senha = False

# ─── LOGIN ──────────────────────────────────────────────────────────────────────
if st.session_state.user_data is None:
    st.title("Login - Sistema Sindicato")
    with st.form("login_form"):
        username = st.text_input("Usuário")
        password = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            if not username.strip():
                st.error("Digite o usuário.")
            elif not password:
                st.error("Digite a senha.")
            else:
                with sqlite3.connect(DB_NAME) as conn:
                    user = conn.execute(
                        "SELECT username, password, tipo_acesso, senha_padrao FROM usuarios WHERE UPPER(username) = ?",
                        (username.strip().upper(),)
                    ).fetchone()

                if user:
                    stored_username, stored_password, stored_tipo, senha_padrao = user

                    # Debug temporário (remova depois de testar)
                    st.write("DEBUG - Tipo da senha no banco:", type(stored_password))
                    st.write("DEBUG - Senha armazenada (primeiros 50 chars):", str(stored_password)[:50] if stored_password else "None")

                    # Converte se for bytes
                    if isinstance(stored_password, (bytes, bytearray)):
                        try:
                            stored_password = stored_password.decode('utf-8')
                        except:
                            stored_password = ""

                    if check_password(password, stored_password):
                        st.session_state.user_data = {
                            "username": stored_username,
                            "tipo": stored_tipo.strip().lower(),
                        }
                        st.session_state.forcar_troca_senha = bool(senha_padrao)
                        if senha_padrao:
                            st.info("Sua senha é a inicial. Por segurança, altere-a agora.")
                        st.success("Login realizado!")
                        st.rerun()
                    else:
                        st.error("Senha incorreta.")
                else:
                    st.error("Usuário não encontrado.")
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
                    # Garante que o valor seja sempre string
                    if not isinstance(hashed, str):
                        hashed = str(hashed)

                    try:
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute("""
                                UPDATE usuarios 
                                SET password = ?, senha_padrao = 0 
                                WHERE username = ?
                            """, (hashed, nome_user))
                            conn.commit()
                        st.success("Senha alterada com sucesso! Faça login novamente com a nova senha.")
                        st.session_state.user_data = None
                        st.session_state.forcar_troca_senha = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar nova senha: {str(e)}")
                        st.info("Tente novamente ou verifique se o banco está acessível.")
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
                        ORDER BY
                            CASE WHEN tipo = 'Titular' THEN 0 ELSE 1 END,
                            nome
                    """, (busca_limpa,)).fetchall()
                    if not rows:
                        rows = conn.execute("""
                            SELECT matricula, nome, empresa, telefone, tipo
                            FROM socios
                            WHERE UPPER(nome) LIKE ? OR matricula LIKE ?
                            ORDER BY
                                CASE WHEN tipo = 'Titular' THEN 0 ELSE 1 END,
                                nome
                        """, (busca_nome, f"%{busca_limpa}%")).fetchall()
                if rows:
                    st.info(f"Encontrados {len(rows)} registros.")
                    if len(rows) == 1:
                        socio_encontrado = rows[0]
                        st.success(f"Encontrado: {socio_encontrado[1]} ({socio_encontrado[4]})")
                    else:
                        opcoes = []
                        for r in rows:
                            tipo_texto = "Titular" if r[4] == "Titular" else "Dependente"
                            opcoes.append(f"{r[1]} ({tipo_texto}) – Matr. {r[0]}")
                        escolha_idx = st.radio(
                            "Selecione quem vai utilizar o serviço:",
                            range(len(opcoes)),
                            format_func=lambda i: opcoes[i],
                            index=0
                        )
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
            serv_default = st.session_state.get('servico_agendamento', SERVICOS[0])
            if serv_default not in SERVICOS:
                serv_default = SERVICOS[0]
            servico = col1.selectbox("Serviço solicitado", SERVICOS, index=SERVICOS.index(serv_default))
            st.session_state.servico_agendamento = servico
            uni_default = st.session_state.get('unidade_agendamento', UNIDADES[0])
            if uni_default not in UNIDADES:
                uni_default = UNIDADES[0]
            unidade = col2.selectbox("Unidade de atendimento", UNIDADES, index=UNIDADES.index(uni_default))
            st.session_state.unidade_agendamento = unidade
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
            if lista_prestadores:
                prest_default = st.session_state.get('prestador_agendamento', lista_prestadores[0])
                if prest_default not in lista_prestadores:
                    prest_default = lista_prestadores[0]
                prestador = st.selectbox("Prestador / Responsável", lista_prestadores,
                                         index=lista_prestadores.index(prest_default))
                st.session_state.prestador_agendamento = prestador
            else:
                st.warning(f"Nenhum prestador encontrado para {servico} na {unidade}.")
                prestador = None
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
                                st.success("Agendamento registrado com sucesso!")
                                st.rerun()

        # ─── ATENDIMENTOS / MEUS AGENDAMENTOS ───────────────────────────────────────
        elif escolha in ["Atendimentos", "Meus Agendamentos"]:
            if tipo_user == "prestador":
                st.title("Meus Agendamentos")
                filtro_status = st.selectbox("Filtrar por status", ["Todos", "Pendente", "Realizado", "Cancelado"])
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
                                    with st.spinner("Validando..."):
                                        with sqlite3.connect(DB_NAME) as conn:
                                            conn.execute("""
                                                UPDATE agendamentos
                                                SET status = 'Realizado',
                                                    data_realizado = CURRENT_TIMESTAMP,
                                                    validado_por = ?
                                                WHERE id = ?
                                            """, (nome_user, row['id']))
                                            conn.commit()
                                    st.success(f"Atendimento marcado como Realizado por {nome_user}!")
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
                    nome_p = st.text_input("Nome completo do prestador", key="cad_nome_prestador")
                    cpf_p = st.text_input("CPF (opcional)", key="cad_cpf_prestador")
                    unidade_p = st.selectbox("Unidade", UNIDADES, key="cad_unidade_prestador")
                    servico_p = st.selectbox("Serviço", SERVICOS, key="cad_servico_prestador")
                    username_p = st.text_input("Nome de usuário para login (ex: CHIUINHO)", key="cad_username_prestador")
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
                                senha_para_inserir = hash_password(SENHA_INICIAL)
                                conn.execute("""
                                    INSERT INTO usuarios (username, password, tipo_acesso, senha_padrao)
                                    VALUES (?, ?, 'Prestador', 1)
                                """, (username_clean, senha_para_inserir))
                                conn.commit()
                                st.success(f"Prestador **{nome_p}** cadastrado!\n\n"
                                           f"**Acesso criado:**\n"
                                           f"• Usuário: **{username_clean}**\n"
                                           f"• Senha inicial: **{SENHA_INICIAL}**\n"
                                           f"→ Logue e troque a senha no primeiro acesso.")
                                st.rerun()
                            except ValueError as ve:
                                if conn.in_transaction:
                                    conn.rollback()
                                st.error(str(ve))
                            except Exception as e:
                                if conn.in_transaction:
                                    conn.rollback()
                                st.error(f"Erro ao cadastrar: {str(e)}")
                            finally:
                                conn.close()
                        else:
                            st.error("Nome completo e nome de usuário são obrigatórios.")
            with sqlite3.connect(DB_NAME) as conn:
                df_p = pd.read_sql_query("SELECT id, nome, cpf, unidade, tipo_servico FROM prestadores ORDER BY nome", conn)
            if df_p.empty:
                st.info("Nenhum prestador cadastrado.")
            else:
                for _, row in df_p.iterrows():
                    expander_key = f"prest_exp_{row['id']}"
                    with st.expander(f"{row['nome']} – {row['tipo_servico']} ({row['unidade']})", expanded=False):
                        col1, col2 = st.columns([4, 1])
                        with col1:
                            with st.form(f"edit_prest_{row['id']}"):
                                nome_edit = st.text_input("Nome", value=row['nome'], key=f"nome_edit_{row['id']}")
                                cpf_edit = st.text_input("CPF", value=row['cpf'] or "", key=f"cpf_edit_{row['id']}")
                                unidade_edit = st.selectbox("Unidade", UNIDADES, index=UNIDADES.index(row['unidade']) if row['unidade'] in UNIDADES else 0, key=f"uni_edit_{row['id']}")
                                servico_edit = st.selectbox("Serviço", SERVICOS, index=SERVICOS.index(row['tipo_servico']) if row['tipo_servico'] in SERVICOS else 0, key=f"serv_edit_{row['id']}")
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
                                st.session_state[f"show_confirm_del_prest_{row['id']}"] = True
                            if st.session_state.get(f"show_confirm_del_prest_{row['id']}", False):
                                st.warning("Tem certeza que deseja excluir este prestador?")
                                col_del1, col_del2 = st.columns(2)
                                with col_del1:
                                    if st.button("Sim, excluir", key=f"conf_del_prest_{row['id']}", type="primary"):
                                        conn = sqlite3.connect(DB_NAME)
                                        try:
                                            cursor = conn.cursor()
                                            cursor.execute("SELECT nome FROM prestadores WHERE id = ?", (row['id'],))
                                            prest_nome_raw = cursor.fetchone()
                                            if prest_nome_raw:
                                                prest_nome_clean = prest_nome_raw[0].upper().replace(" ", "")
                                                conn.execute("DELETE FROM usuarios WHERE username = ?", (prest_nome_clean,))
                                            conn.execute("DELETE FROM prestadores WHERE id = ?", (row['id'],))
                                            conn.commit()
                                            st.success(f"Prestador **{row['nome']}** e possível acesso associado excluídos!")
                                            st.rerun()
                                        except Exception as e:
                                            if conn.in_transaction:
                                                conn.rollback()
                                            st.error(f"Erro ao excluir: {str(e)}")
                                        finally:
                                            conn.close()
                                with col_del2:
                                    if st.button("Cancelar", key=f"cancel_del_prest_{row['id']}"):
                                        st.session_state[f"show_confirm_del_prest_{row['id']}"] = False
                                        st.rerun()

        # ─── DIRETORIA ──────────────────────────────────────────────────────────────
        elif escolha == "Diretoria" and tipo_user in ["master", "adm", "recepção"]:
            st.title("Gestão da Diretoria")
            is_master = (tipo_user == "master")
            with st.expander("Cadastrar novo usuário (diretor ou prestador)" if is_master else "Somente Master pode cadastrar"):
                if is_master:
                    with st.form("cad_diretor"):
                        nome_d = st.text_input("Nome completo")
                        cpf_d = st.text_input("CPF (opcional)")
                        area_d = st.text_input("Área de responsabilidade (opcional)")
                        nivel_d = st.selectbox("Nível de acesso", NIVEIS_ACESSO)
                        usuario_d = st.text_input("Nome de usuário (login)")
                        foto_upload = st.file_uploader("Foto (opcional)", type=["jpg", "jpeg", "png"])
                        if st.form_submit_button("Cadastrar"):
                            if nome_d.strip() and usuario_d.strip():
                                foto_bytes = None
                                if foto_upload is not None:
                                    foto_bytes = foto_upload.read()
                                conn = sqlite3.connect(DB_NAME)
                                try:
                                    conn.execute("BEGIN TRANSACTION")
                                    conn.execute("""
                                        INSERT INTO diretores (nome, cpf, area_responsavel, nivel_acesso, username, foto)
                                        VALUES (?, ?, ?, ?, ?, ?)
                                    """, (nome_d.strip(), limpar_cpf(cpf_d), area_d or None, nivel_d, usuario_d.strip(), foto_bytes))
                                    senha_diretor = hash_password(SENHA_INICIAL)
                                    conn.execute("""
                                        INSERT INTO usuarios (username, password, tipo_acesso, senha_padrao)
                                        VALUES (?, ?, ?, 1)
                                    """, (usuario_d.strip(), senha_diretor, nivel_d))
                                    conn.commit()
                                    st.success(f"Usuário cadastrado! Senha inicial definida.")
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
                else:
                    st.info("Apenas Master pode cadastrar novos usuários.")
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
                                    if is_master:
                                        foto_bytes_edit = None
                                        if foto_edit is not None:
                                            foto_bytes_edit = foto_edit.read()
                                        params = (nome_edit.strip(), limpar_cpf(cpf_edit), area_edit or None, nivel_edit, row['id'])
                                        with sqlite3.connect(DB_NAME) as conn:
                                            if foto_bytes_edit is not None:
                                                conn.execute("""
                                                    UPDATE diretores
                                                    SET nome = ?, cpf = ?, area_responsavel = ?, nivel_acesso = ?, foto = ?
                                                    WHERE id = ?
                                                """, (*params, foto_bytes_edit))
                                            else:
                                                conn.execute("""
                                                    UPDATE diretores
                                                    SET nome = ?, cpf = ?, area_responsavel = ?, nivel_acesso = ?
                                                    WHERE id = ?
                                                """, params)
                                            conn.commit()
                                        st.success("Usuário atualizado!")
                                        st.rerun()
                                    else:
                                        st.error("Apenas Master pode editar.")
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
                                st.markdown(
                                    """
                                    <div style="text-align:center; color:#aaa; font-size:14px; margin:10px 0;">
                                        Sem foto
                                    </div>
                                    """,
                                    unsafe_allow_html=True
                                )
                            if is_master:
                                if st.button("Excluir", key=f"del_dir_{row['id']}"):
                                    if st.button("Confirmar exclusão", key=f"conf_del_{row['id']}", type="primary"):
                                        with sqlite3.connect(DB_NAME) as conn:
                                            cursor = conn.cursor()
                                            cursor.execute("SELECT username FROM diretores WHERE id = ?", (row['id'],))
                                            username_dir = cursor.fetchone()
                                            if username_dir and username_dir[0]:
                                                conn.execute("DELETE FROM usuarios WHERE username = ?", (username_dir[0],))
                                            conn.execute("DELETE FROM diretores WHERE id = ?", (row['id'],))
                                            conn.commit()
                                        st.success("Usuário excluído!")
                                        st.rerun()
                                if st.button("Reset senha para inicial", key=f"reset_{row['id']}"):
                                    if st.button("Confirmar reset", key=f"conf_reset_{row['id']}", type="primary"):
                                        senha_reset = hash_password(SENHA_INICIAL)
                                        conn.execute("""
                                            UPDATE usuarios
                                            SET password = ?, senha_padrao = 1
                                            WHERE username = ?
                                        """, (senha_reset, row['username']))
                                        conn.commit()
                                        st.success("Senha redefinida para a inicial.")
                                        st.rerun()
                                    else:
                                        st.error("Não foi possível resetar (problema com hash).")
                            else:
                                st.info("Apenas Master pode excluir ou resetar senha.")

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
                    contagem = {"Sócio": 0, "Dependentes": 0}
                    for aba, tipo in [("Sócio", "Titular"), ("Dependentes", "Dependente")]:
                        if aba in xl.sheet_names:
                            df = pd.read_excel(xl, sheet_name=aba, header=None, dtype=str)
                            if len(df.columns) >= 3:
                                df = df.iloc[:, :3].copy()
                                df.columns = ['matricula', 'nome', 'empresa']
                            else:
                                df = df.iloc[:, :2].copy()
                                df.columns = ['matricula', 'nome']
                                df['empresa'] = None
                            df['tipo'] = tipo
                            df['empresa'] = df['empresa'].astype(str).str.strip().replace(['nan', 'None', ''], None)
                            if tipo == "Dependente":
                                df['empresa'] = "Dependente"
                            df['matricula'] = df['matricula'].apply(normalize_matricula)
                            df['nome'] = df['nome'].astype(str).str.strip().str.upper()
                            df['empresa'] = df['empresa'].fillna("").astype(str)
                            df = df.dropna(subset=['matricula', 'nome'])
                            df = df[df['matricula'] != '']
                            contagem[aba] = len(df)
                            df_final = pd.concat([df_final, df], ignore_index=True)
                    if df_final.empty:
                        st.error("Nenhum dado válido.")
                    else:
                        df_final = df_final.drop_duplicates(subset=['matricula', 'nome', 'tipo'], keep='last')
                        st.subheader("Pré-visualização")
                        st.dataframe(
                            df_final[['matricula', 'nome', 'empresa', 'tipo']],
                            use_container_width=True
                        )
                        st.info(f"Resumo:\n- Sócios: {contagem['Sócio']}\n- Dependentes: {contagem['Dependentes']}\nTotal: {len(df_final)}")
                        if st.button("Confirmar importação"):
                            with sqlite3.connect(DB_NAME) as conn:
                                df_final.to_sql("socios", conn, if_exists="replace", index=False)
                                conn.execute("CREATE INDEX IF NOT EXISTS idx_matricula ON socios(matricula)")
                            st.success(f"Importados {len(df_final)} registros! (todos dependentes preservados)")
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
                        CASE
                            WHEN matricula_socio IS NULL THEN 'Não associado'
                            WHEN s.tipo = 'Titular' THEN 'Titular'
                            ELSE 'Dependente'
                        END AS "Tipo",
                        tipo_servico AS "Serviço",
                        unidade AS "Unidade",
                        prestador_nome AS "Prestador",
                        diretor_solicitante AS "Diretor",
                        status AS "Status",
                        criado_em AS "Criado em",
                        data_realizado AS "Validado em",
                        validado_por AS "Validado por"
                    FROM agendamentos a
                    LEFT JOIN socios s ON a.matricula_socio = s.matricula
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
                    st.success(f"{len(df_relatorio)} registros encontrados")
                    df_display = df_relatorio.copy()
                    df_display["Data"] = pd.to_datetime(df_display["Data"]).dt.strftime("%d/%m/%Y")
                    df_display["Criado em"] = pd.to_datetime(df_display["Criado em"]).dt.strftime("%d/%m/%Y %H:%M")
                    if "Validado em" in df_display.columns:
                        df_display["Validado em"] = pd.to_datetime(df_display["Validado em"], errors='coerce').dt.strftime("%d/%m/%Y %H:%M")
                    st.dataframe(df_display, use_container_width=True, hide_index=True)
                    output_excel = io.BytesIO()
                    with pd.ExcelWriter(output_excel, engine='xlsxwriter') as writer:
                        df_relatorio.to_excel(writer, index=False, sheet_name='Relatório')
                    excel_data = output_excel.getvalue()
                    st.download_button(
                        label="Baixar em Excel (.xlsx)",
                        data=excel_data,
                        file_name=f"relatorio_servicos_{date.today().strftime('%Y-%m-%d')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    st.warning("Para gerar PDF, instale reportlab: pip install reportlab")
