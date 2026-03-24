import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, timedelta
import unicodedata
import base64
import os
import hashlib
import binascii
from io import BytesIO

st.set_page_config(
    page_title="Sistema Sindicato",
    layout="wide",
    page_icon="🛡️",
    initial_sidebar_state="expanded"
)

DB_NAME = "sindicato.db"
SERVICOS = ["Odontologia", "Psicologia", "Jurídico", "Cabeleireiro", "Manicure", "Eletricista", "Jardineiro", "Pedreiro"]
UNIDADES = ["Sede Jundiaí", "Sub Sede Franco da Rocha", "Externo Jundiaí", "Externo Franco da Rocha"]
HORARIOS = [f"{h:02d}:{m:02d}" for h in range(8, 18) for m in (0, 30)]
SENHA_INICIAL = "Sindicato@2026!"

# ====================== CARREGAR LOGO ======================
LOGO_PATH = "logo1.png"

def get_base64_logo():
    if os.path.exists(LOGO_PATH):
        try:
            with open(LOGO_PATH, "rb") as f:
                return base64.b64encode(f.read()).decode()
        except:
            return None
    return None

logo_base64 = get_base64_logo()

# ====================== FUNÇÕES ======================
def hash_password(password: str) -> str:
    salt = os.urandom(32)
    iterations = 100_000
    key = hashlib.pbkdf2_hmac('sha512', password.encode('utf-8'), salt, iterations, dklen=64)
    salt_hex = binascii.hexlify(salt).decode('ascii')
    key_hex = binascii.hexlify(key).decode('ascii')
    return f"pbkdf2_sha512${iterations}${salt_hex}${key_hex}"

def check_password(provided: str, stored) -> bool:
    if not provided or not stored:
        return False
    try:
        if isinstance(stored, (bytes, bytearray)):
            stored = stored.decode('utf-8')
        provided = str(provided).strip()
        stored = str(stored).strip()
        if not stored.startswith("pbkdf2_sha512"):
            if '$' not in stored:
                return stored == provided
            salt, hashed = stored.split('$', 1)
            computed = hashlib.sha256((salt + provided).encode('utf-8')).hexdigest()
            return computed == hashed
        parts = stored.split('$')
        if len(parts) != 4: return False
        _, iters_str, salt_hex, stored_hash = parts
        iterations = int(iters_str)
        salt = binascii.unhexlify(salt_hex)
        computed_key = hashlib.pbkdf2_hmac('sha512', provided.encode('utf-8'), salt, iterations, dklen=64)
        return binascii.hexlify(computed_key).decode('ascii') == stored_hash
    except:
        return False

def normalize_for_db(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    text = unicodedata.normalize('NFD', text.strip())
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return text.upper()

def limpar_numero(valor):
    return "".join(c for c in str(valor or "") if c.isdigit())

def formatar_telefone(valor):
    v = limpar_numero(valor)
    if len(v) == 11: return f"({v[:2]}) {v[2:7]}-{v[7:]}"
    if len(v) == 10: return f"({v[:2]}) {v[2:6]}-{v[6:]}"
    return v

# ====================== BANCO DE DADOS ======================
def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        c = conn.cursor()
        c.execute('''
            CREATE TABLE IF NOT EXISTS socios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                matricula TEXT NOT NULL,
                nome TEXT NOT NULL,
                empresa TEXT,
                cpf TEXT,
                telefone TEXT,
                tipo TEXT DEFAULT 'Titular'
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                tipo_acesso TEXT NOT NULL,
                senha_padrao INTEGER DEFAULT 1
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS prestadores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                cpf TEXT,
                unidade TEXT NOT NULL,
                tipo_servico TEXT NOT NULL
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS diretores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                cpf TEXT,
                area_responsavel TEXT,
                nivel_acesso TEXT,
                username TEXT UNIQUE,
                foto BLOB
            )
        ''')
        c.execute('''
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
                validado_por TEXT,
                motivo_cancelamento TEXT
            )
        ''')
        conn.commit()

def force_reset_master():
    senha_hash = hash_password(SENHA_INICIAL)
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM usuarios WHERE UPPER(username) = 'MASTER'")
        c.execute("INSERT INTO usuarios (username, password, tipo_acesso, senha_padrao) VALUES ('MASTER', ?, 'Master', 1)", (senha_hash,))
        conn.commit()

init_db()
if not sqlite3.connect(DB_NAME).execute("SELECT 1 FROM usuarios WHERE UPPER(username)='MASTER'").fetchone():
    force_reset_master()

# ====================== SESSION STATE ======================
if 'user_data' not in st.session_state:
    st.session_state.user_data = None
if 'forcar_troca_senha' not in st.session_state:
    st.session_state.forcar_troca_senha = False

# ====================== LOGIN ======================
if st.session_state.user_data is None:
    st.title("🔐 Login - Sistema Sindicato")
    with st.form("login_form"):
        username = st.text_input("Usuário").strip().upper()
        password = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar", type="primary"):
            with sqlite3.connect(DB_NAME) as conn:
                user = conn.execute("SELECT username, password, tipo_acesso, senha_padrao FROM usuarios WHERE username = ?", (username,)).fetchone()
            if user and check_password(password, user[1]):
                st.session_state.user_data = {"username": user[0], "tipo": user[2].strip().lower()}
                st.session_state.forcar_troca_senha = bool(user[3])
                st.success("Login realizado com sucesso!")
                st.rerun()
            else:
                st.error("Usuário ou senha incorretos.")
else:
    user_info = st.session_state.user_data
    tipo_user = user_info["tipo"]
    nome_user = user_info["username"]

    with st.sidebar:
        st.markdown(f"**👤 {nome_user.upper()}** \n({tipo_user.upper()})")
        st.markdown("---")

    if st.session_state.forcar_troca_senha:
        st.title("🔑 Alterar Senha Inicial (Obrigatório)")
        with st.form("form_troca_senha"):
            nova_senha = st.text_input("Nova senha", type="password")
            confirma = st.text_input("Confirmar nova senha", type="password")
            if st.form_submit_button("Salvar Senha", type="primary"):
                if len(nova_senha) < 6 or nova_senha != confirma or nova_senha == SENHA_INICIAL:
                    st.error("Senha inválida.")
                else:
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("UPDATE usuarios SET password = ?, senha_padrao = 0 WHERE username = ?", 
                                    (hash_password(nova_senha), nome_user))
                        conn.commit()
                    st.success("Senha alterada com sucesso!")
                    st.session_state.user_data = None
                    st.rerun()
    else:
        # ====================== MENU ======================
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

        # ====================== AGENDAR ======================
        if escolha == "Agendar":
            st.title("📅 Novo Agendamento")
            busca = st.text_input("🔍 Buscar Sócio ou Dependente (Matrícula ou Nome)")
            socio_encontrado = None
            rows = []
            if busca.strip():
                busca_limpa = busca.strip()
                busca_nome = f"%{normalize_for_db(busca)}%"
                with sqlite3.connect(DB_NAME) as conn:
                    rows = conn.execute("""
                        SELECT matricula, nome, empresa, telefone, tipo
                        FROM socios
                        WHERE matricula = ? OR matricula LIKE ? OR UPPER(nome) LIKE ?
                        ORDER BY matricula, CASE WHEN tipo = 'Titular' THEN 0 ELSE 1 END, nome
                    """, (busca_limpa, f"%{busca_limpa}%", busca_nome)).fetchall()
                if rows:
                    st.success(f"✅ Encontrados **{len(rows)}** registro(s)")
                    opcoes = []
                    for r in rows:
                        empresa_str = f" — {r[2]}" if r[2] else ""
                        label = f"{r[1]} — Matrícula {r[0]} ({r[4]}){empresa_str}"
                        opcoes.append((label, r))
                    idx = st.radio("Selecione quem vai utilizar o serviço:", range(len(opcoes)), format_func=lambda i: opcoes[i][0])
                    socio_encontrado = opcoes[idx][1]

            col1, col2 = st.columns(2)
            servico = col1.selectbox("Serviço solicitado", SERVICOS)
            unidade = col2.selectbox("Unidade de atendimento", UNIDADES)

            with sqlite3.connect(DB_NAME) as conn:
                if "Externo" in unidade:
                    lista_prestadores = [r[0] for r in conn.execute("SELECT nome FROM prestadores WHERE tipo_servico = ? ORDER BY nome", (servico,)).fetchall()]
                else:
                    lista_prestadores = [r[0] for r in conn.execute("SELECT nome FROM prestadores WHERE unidade = ? AND tipo_servico = ? ORDER BY nome", (unidade, servico)).fetchall()]

            if not lista_prestadores:
                st.error(f"⚠️ Nenhum prestador cadastrado para **{servico}** na **{unidade}**.")
                st.info("Cadastre prestadores em 'Prestadores' no menu lateral.")
                prestador = None
            else:
                prestador = st.selectbox("Prestador / Responsável", lista_prestadores)

            with st.form("form_agendamento", clear_on_submit=True):
                nome = st.text_input("Nome completo", value=socio_encontrado[1] if socio_encontrado else "")
                empresa = st.text_input("Empresa / Local de trabalho", value=socio_encontrado[2] if socio_encontrado else "")
                telefone_raw = st.text_input("Telefone para contato", value=formatar_telefone(socio_encontrado[3]) if socio_encontrado else "")
                col1, col2 = st.columns(2)
                data_atendimento = col1.date_input("Data do atendimento", min_value=date.today(), max_value=date.today() + timedelta(days=120))

                horarios_disponiveis = HORARIOS[:]
                if prestador and data_atendimento:
                    data_iso = data_atendimento.strftime("%Y-%m-%d")
                    with sqlite3.connect(DB_NAME) as conn:
                        ocupados = conn.execute("SELECT horario FROM agendamentos WHERE prestador_nome = ? AND data_atendimento = ? AND status NOT IN ('Cancelado', 'Realizado')", (prestador, data_iso)).fetchall()
                    horarios_ocupados = {r[0] for r in ocupados}
                    horarios_disponiveis = [h for h in HORARIOS if h not in horarios_ocupados]

                horario = col1.selectbox("Horário disponível", horarios_disponiveis if horarios_disponiveis else ["Nenhum horário disponível"])
                st.text_input("Diretor solicitante", value=nome_user, disabled=True)

                if st.form_submit_button("✅ Confirmar Agendamento", type="primary"):
                    if not nome.strip() or not prestador:
                        st.error("Preencha todos os campos obrigatórios.")
                    else:
                        data_iso = data_atendimento.strftime("%Y-%m-%d")
                        with sqlite3.connect(DB_NAME) as conn:
                            conflito = conn.execute("SELECT 1 FROM agendamentos WHERE prestador_nome = ? AND data_atendimento = ? AND horario = ? AND status NOT IN ('Cancelado', 'Realizado')", (prestador, data_iso, horario)).fetchone()
                            if conflito:
                                st.error("❌ Horário já ocupado.")
                            else:
                                conn.execute("""
                                    INSERT INTO agendamentos
                                    (matricula_socio, nome_socio, empresa_socio, telefone_socio, tipo_servico, unidade, prestador_nome, data_atendimento, horario, diretor_solicitante)
                                    VALUES (?,?,?,?,?,?,?,?,?,?)
                                """, (socio_encontrado[0] if socio_encontrado else None, nome.strip(), empresa.strip() or None, 
                                      limpar_numero(telefone_raw) or None, servico, unidade, prestador, data_iso, horario, nome_user))
                                conn.commit()
                        st.success("✅ Agendamento registrado com sucesso!")
                        st.rerun()

        # ====================== CADASTRO DE DIRETORIA ======================
        elif escolha == "Diretoria" and tipo_user in ["master", "adm", "recepção"]:
            st.title("👔 Cadastro de Diretoria")

            tab1, tab2 = st.tabs(["📝 Cadastrar Novo Diretor", "📋 Diretores Cadastrados"])

            with tab1:
                with st.form("form_diretor", clear_on_submit=True):
                    col1, col2 = st.columns(2)
                    nome_d = col1.text_input("Nome completo do Diretor *")
                    cpf_d = col2.text_input("CPF")   # CPF opcional
                    area = col1.selectbox("Área Responsável", 
                                        ["Diretor", "Presidência", "Vice-Presidência", "Financeiro", 
                                         "Jurídico", "Saúde", "Eventos", "Outros"])
                    nivel = col2.selectbox("Nível de Acesso", ["Master", "Adm", "Recepção"])
                    username_d = st.text_input("Username para login *", help="Será usado para acessar o sistema")

                    foto = st.file_uploader("Foto do Diretor (opcional)", type=["png", "jpg", "jpeg"])

                    if st.form_submit_button("✅ Cadastrar Diretor", type="primary"):
                        if not nome_d or not username_d:
                            st.error("❌ Nome e Username são obrigatórios.")
                        else:
                            foto_blob = foto.read() if foto else None
                            with sqlite3.connect(DB_NAME) as conn:
                                try:
                                    conn.execute("""
                                        INSERT INTO diretores (nome, cpf, area_responsavel, nivel_acesso, username, foto)
                                        VALUES (?,?,?,?,?,?)
                                    """, (nome_d.strip(), cpf_d.strip() if cpf_d else None, area, nivel, username_d.strip().upper(), foto_blob))
                                    conn.commit()
                                    st.success(f"✅ Diretor **{nome_d}** cadastrado com sucesso!")
                                except sqlite3.IntegrityError:
                                    st.error("❌ Username já existe. Escolha outro.")
                                except Exception as e:
                                    st.error(f"Erro ao cadastrar: {e}")

            with tab2:
                st.subheader("Diretores Cadastrados")
                with sqlite3.connect(DB_NAME) as conn:
                    df_dir = pd.read_sql_query("""
                        SELECT id, nome, cpf, area_responsavel AS Área, nivel_acesso AS Nível, username 
                        FROM diretores ORDER BY nome
                    """, conn)

                if df_dir.empty:
                    st.info("Nenhum diretor cadastrado ainda.")
                else:
                    st.dataframe(df_dir, use_container_width=True, hide_index=True)

                    st.subheader("🗑️ Remover Diretor")
                    diretor_remover = st.selectbox("Selecione o diretor para remover", 
                                                 df_dir["nome"].tolist() if not df_dir.empty else [])
                    if st.button("🗑️ Remover Diretor Selecionado", type="secondary"):
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute("DELETE FROM diretores WHERE nome = ?", (diretor_remover,))
                            conn.commit()
                        st.success(f"Diretor **{diretor_remover}** removido!")
                        st.rerun()

        # ====================== RELATÓRIO DE SERVIÇOS (AGORA COM DOWNLOAD) ======================
        elif escolha == "Relatório de Serviços" and tipo_user == "master":
            st.title("📊 Relatório de Serviços")

            col1, col2, col3 = st.columns(3)
            with col1:
                data_inicio = st.date_input("Data Inicial", value=date.today() - timedelta(days=30))
            with col2:
                data_fim = st.date_input("Data Final", value=date.today())
            with col3:
                servico_filtro = st.selectbox("Serviço", ["Todos"] + SERVICOS)

            query = """
                SELECT tipo_servico AS Serviço, 
                       unidade AS Unidade, 
                       status AS Status, 
                       COUNT(*) AS Quantidade
                FROM agendamentos 
                WHERE data_atendimento BETWEEN ? AND ?
            """
            params = [data_inicio.strftime("%Y-%m-%d"), data_fim.strftime("%Y-%m-%d")]

            if servico_filtro != "Todos":
                query += " AND tipo_servico = ?"
                params.append(servico_filtro)

            query += " GROUP BY tipo_servico, unidade, status ORDER BY Quantidade DESC"

            with sqlite3.connect(DB_NAME) as conn:
                df = pd.read_sql_query(query, conn, params=params)

            if df.empty:
                st.warning("Nenhum agendamento encontrado no período selecionado.")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)

                total = df["Quantidade"].sum()
                st.success(f"**Total de atendimentos no período: {total}**")

                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("📥 Baixar Relatório em Excel", type="primary"):
                        output = BytesIO()
                        with pd.ExcelWriter(output, engine='openpyxl') as writer:
                            df.to_excel(writer, index=False, sheet_name="Relatorio_Servicos")
                        output.seek(0)
                        st.download_button(
                            label="Clique para baixar o arquivo Excel",
                            data=output.getvalue(),
                            file_name=f"Relatorio_Servicos_{date.today()}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )

                with col_b:
                    if st.button("📄 Baixar PDF (em breve)"):
                        st.info("Funcionalidade de PDF será implementada em breve.")

        # ====================== OUTRAS TELAS ======================
        elif escolha in ["Atendimentos", "Meus Agendamentos"]:
            st.title("📋 Meus Agendamentos" if tipo_user == "prestador" else "📋 Lista de Atendimentos")
            filtro_status = st.selectbox("Filtrar por status", ["Todos", "Pendente", "Realizado", "Cancelado"])
            with sqlite3.connect(DB_NAME) as conn:
                query = "SELECT id, nome_socio, tipo_servico, unidade, data_atendimento, horario, status FROM agendamentos WHERE 1=1"
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
                st.dataframe(df, use_container_width=True)

        elif escolha == "Prestadores" and tipo_user in ["master", "adm", "recepção"]:
            st.title("👷 Cadastro de Prestadores")
            with st.form("form_prestador"):
                col1, col2 = st.columns(2)
                nome_p = col1.text_input("Nome completo do prestador")
                cpf_p = col2.text_input("CPF")
                uni_p = col1.selectbox("Unidade", UNIDADES)
                serv_p = col2.selectbox("Serviço", SERVICOS)
                if st.form_submit_button("Cadastrar Prestador", type="primary"):
                    if nome_p and uni_p and serv_p:
                        username_p = "".join(nome_p.split()).upper()[:30]
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute("INSERT INTO prestadores (nome, cpf, unidade, tipo_servico) VALUES (?,?,?,?)", (nome_p.strip(), cpf_p, uni_p, serv_p))
                            senha_hash = hash_password(SENHA_INICIAL)
                            try:
                                conn.execute("INSERT INTO usuarios (username, password, tipo_acesso, senha_padrao) VALUES (?, ?, 'Prestador', 1)", (username_p, senha_hash))
                                st.success(f"✅ Prestador cadastrado!\nUsuário: `{username_p}`\nSenha inicial: `{SENHA_INICIAL}`")
                            except:
                                st.warning("Prestador cadastrado (usuário já existia).")
                            conn.commit()
                        st.rerun()
            st.subheader("Prestadores Cadastrados")
            with sqlite3.connect(DB_NAME) as conn:
                df_p = pd.read_sql_query("SELECT * FROM prestadores ORDER BY nome", conn)
            st.dataframe(df_p, use_container_width=True)

        elif escolha == "Importar Sócios" and tipo_user in ["master", "adm"]:
            st.title("📤 Importar Sócios do Excel")
            uploaded = st.file_uploader("Escolha o arquivo Excel", type=["xlsx"])
            if uploaded:
                try:
                    df = pd.read_excel(uploaded, sheet_name="Sócio", engine="openpyxl")
                    df["Matrícula"] = df["Matrícula"].astype(str).str.strip()
                    df["Nome"] = df["Nome"].astype(str).str.strip().str.upper()
                    df["Empresa"] = df["Empresa"].astype(str).str.strip().str.upper().replace(["NAN","nan",""], None)
                    df["tipo"] = df["Empresa"].apply(lambda x: "Titular" if pd.notna(x) else "Dependente")
                    df = df.drop_duplicates(subset=["Matrícula", "Nome"], keep="first")
                    df = df.dropna(subset=["Matrícula", "Nome"])

                    st.success(f"✅ {len(df)} registros válidos.")
                    st.dataframe(df.head(10))

                    if st.button("🚀 IMPORTAR", type="primary"):
                        with sqlite3.connect(DB_NAME) as conn:
                            inserted = 0
                            for _, row in df.iterrows():
                                try:
                                    conn.execute("INSERT INTO socios (matricula, nome, empresa, tipo) VALUES (?,?,?,?)",
                                                 (row["Matrícula"], row["Nome"], row["Empresa"], row["tipo"]))
                                    inserted += 1
                                except:
                                    pass
                            conn.commit()
                        st.success(f"✅ Importação concluída! {inserted} sócios inseridos.")
                        if logo_base64:
                            st.markdown(
                                f"""
                                <div style="text-align: center; margin: 40px 0;">
                                    <img src="data:image/png;base64,{logo_base64}" 
                                         style="max-width: 450px; width: 100%; height: auto; border-radius: 15px; box-shadow: 0 8px 20px rgba(0,0,0,0.15);">
                                </div>
                                """,
                                unsafe_allow_html=True
                            )
                except Exception as e:
                    st.error(f"Erro na importação: {e}")

        elif escolha == "Redefinir Senhas" and tipo_user == "master":
            st.title("🔑 Redefinir Senhas")
            with sqlite3.connect(DB_NAME) as conn:
                users = conn.execute("SELECT username, tipo_acesso FROM usuarios").fetchall()
            for u in users:
                if st.button(f"🔄 Resetar {u[0]}", key=f"reset_{u[0]}"):
                    with sqlite3.connect(DB_NAME) as conn:
                        conn.execute("UPDATE usuarios SET password = ?, senha_padrao = 1 WHERE username = ?", 
                                   (hash_password(SENHA_INICIAL), u[0]))
                        conn.commit()
                    st.success(f"Senha de {u[0]} resetada!")
                    st.rerun()

        else:
            st.info("Selecione uma opção no menu lateral.")
