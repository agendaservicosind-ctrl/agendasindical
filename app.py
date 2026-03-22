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

# ================== FUNÇÕES DE SENHA ==================
def hash_password(password: str) -> str:
    salt = os.urandom(32)
    iterations = 100_000
    key = hashlib.pbkdf2_hmac('sha512', password.encode('utf-8'), salt, iterations, dklen=64)
    salt_hex = binascii.hexlify(salt).decode('ascii')
    key_hex = binascii.hexlify(key).decode('ascii')
    return f"pbkdf2_sha512${iterations}${salt_hex}${key_hex}"

def check_password(provided: str, stored) -> bool:
    if stored is None or not provided:
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
        parts = stored.split('$')
        if len(parts) != 4:
            return False
        algo, iters_str, salt_hex, stored_hash = parts
        if algo != "pbkdf2_sha512":
            return False
        iterations = int(iters_str)
        salt = binascii.unhexlify(salt_hex)
        computed_key = hashlib.pbkdf2_hmac(
            'sha512', provided.encode('utf-8'), salt, iterations, dklen=64
        )
        computed_hex = binascii.hexlify(computed_key).decode('ascii')
        return computed_hex == stored_hash
    except Exception as e:
        st.error(f"Erro na verificação de senha: {str(e)}")
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
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        cursor = conn.cursor()
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
            except:
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
                validado_por TEXT,
                motivo_cancelamento TEXT
            )
        ''')
        for col in ['data_realizado', 'validado_por', 'motivo_cancelamento']:
            try:
                cursor.execute(f"ALTER TABLE agendamentos ADD COLUMN {col} TEXT")
            except:
                pass
        conn.commit()

def deve_resetar_master():
    try:
        with sqlite3.connect(DB_NAME) as conn:
            row = conn.execute(
                "SELECT senha_padrao FROM usuarios WHERE UPPER(username) = 'MASTER'"
            ).fetchone()
            return row is None or row[0] == 1
    except:
        return True

def force_reset_master():
    senha_hash = hash_password(SENHA_INICIAL)
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM usuarios WHERE UPPER(username) = 'MASTER'")
        cursor.execute("""
            INSERT INTO usuarios (username, password, tipo_acesso, senha_padrao)
            VALUES ('MASTER', ?, 'Master', 1)
        """, (senha_hash,))
        conn.commit()
    st.info("Senha do MASTER foi RESETADA para 'Sindicato@2026!'. Faça login agora e troque imediatamente.")

init_db()
if deve_resetar_master():
    force_reset_master()

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
                    try:
                        with sqlite3.connect(DB_NAME) as conn:
                            conn.execute("UPDATE usuarios SET password = ?, senha_padrao = 0 WHERE username = ?",
                                         (hashed, nome_user))
                            conn.commit()
                        st.success("Senha alterada! Faça login novamente.")
                        st.session_state.user_data = None
                        st.session_state.forcar_troca_senha = False
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erro ao salvar: {str(e)}")

    else:
        # Menus
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
                           OR UPPER(nome) LIKE ?
                           OR matricula LIKE ?
                        ORDER BY CASE WHEN tipo = 'Titular' THEN 0 ELSE 1 END, nome
                    """, (busca_limpa, busca_nome, f"%{busca_limpa}%")).fetchall()

                if rows:
                    st.info(f"Encontrados {len(rows)} registros.")
                    if len(rows) == 1:
                        socio_encontrado = rows[0]
                        st.success(f"Encontrado: {socio_encontrado[1]} ({socio_encontrado[4]})")
                    else:
                        opcoes = [f"{r[1]} ({'Titular' if r[4]=='Titular' else 'Dependente'}) – Matr. {r[0]}" for r in rows]
                        escolha_idx = st.radio("Selecione quem vai utilizar o serviço:", range(len(opcoes)), format_func=lambda i: opcoes[i])
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

                # Horários disponíveis dinâmicos
                horarios_disponiveis = HORARIOS[:]
                if prestador and data_atendimento:
                    data_iso = data_atendimento.strftime("%Y-%m-%d")
                    with sqlite3.connect(DB_NAME) as conn:
                        ocupados = conn.execute("""
                            SELECT horario FROM agendamentos
                            WHERE prestador_nome = ?
                              AND data_atendimento = ?
                              AND status NOT IN ('Cancelado', 'Realizado')
                        """, (prestador, data_iso)).fetchall()
                    horarios_ocupados = {r[0] for r in ocupados}
                    horarios_disponiveis = [h for h in HORARIOS if h not in horarios_ocupados]

                if not horarios_disponiveis:
                    horario = col1.selectbox("Horário disponível", ["Nenhum horário disponível nesta data"])
                else:
                    horario = col1.selectbox("Horário disponível", horarios_disponiveis)

                diretor_solicitante = col2.text_input("Diretor solicitante", value=nome_user, disabled=True)

                pode_agendar_manual = tipo_user in ["master", "adm", "recepção"]
                submit_disabled = (nao_associado and not pode_agendar_manual) or (prestador is None) or (not horarios_disponiveis)

                if nao_associado and not pode_agendar_manual:
                    st.warning("Apenas Master, ADM ou Recepção podem agendar para não associados.")
                if not horarios_disponiveis and prestador:
                    st.error("Todos os horários estão ocupados para este prestador nesta data.")

                if st.form_submit_button("Confirmar Agendamento", type="primary", disabled=submit_disabled):
                    if not nome.strip():
                        st.error("Nome obrigatório.")
                    elif prestador is None:
                        st.error("Selecione um prestador válido.")
                    elif not horarios_disponiveis:
                        st.error("Escolha uma data/horário disponível.")
                    else:
                        data_iso = data_atendimento.strftime("%Y-%m-%d")
                        with sqlite3.connect(DB_NAME) as conn:
                            # Verificação dupla de conflito (por segurança)
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
            else:
                st.title("Lista de Atendimentos")

            filtro_status = st.selectbox("Filtrar por status", ["Todos", "Pendente", "Realizado", "Cancelado"])

            with sqlite3.connect(DB_NAME) as conn:
                query = """
                    SELECT id, nome_socio, tipo_servico, unidade, data_atendimento, horario, status, diretor_solicitante, motivo_cancelamento
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
                        status_text = row["status"]
                        if row["status"] == "Cancelado" and row["motivo_cancelamento"]:
                            status_text += f" ({row['motivo_cancelamento']})"

                        st.markdown(f"**{row['nome_socio']}** – {row['tipo_servico']} | {row['unidade']} | {row['Data']} {row['horario']} **({status_text})**")

                        if row["status"] == "Pendente":
                            col1, col2 = st.columns(2)
                            with col1:
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
                            with col2:
                                if st.button("❌ Cancelar", key=f"cancelar_{row['id']}"):
                                    motivo = st.text_input("Motivo do cancelamento (opcional)", key=f"motivo_{row['id']}")
                                    if st.button("Confirmar Cancelamento", key=f"confcancel_{row['id']}"):
                                        with sqlite3.connect(DB_NAME) as conn:
                                            conn.execute("""
                                                UPDATE agendamentos
                                                SET status = 'Cancelado',
                                                    data_realizado = CURRENT_TIMESTAMP,
                                                    validado_por = ?,
                                                    motivo_cancelamento = ?
                                                WHERE id = ?
                                            """, (nome_user, motivo.strip() or None, row['id']))
                                            conn.commit()
                                        st.success("Agendamento cancelado!")
                                        st.rerun()
                        st.markdown("---")
                else:
                    st.dataframe(df, use_container_width=True)

        # ─── IMPORTAR SÓCIOS (com correção openpyxl) ────────────────────────────────
        elif escolha == "Importar Sócios" and tipo_user in ["master", "adm"]:
            st.title("Importar Sócios do Excel")
            st.info("""
            **Formato esperado do arquivo:**
            - Arquivo .xlsx
            - Aba chamada **Sócio**
            - Colunas obrigatórias: **Matrícula**, **Nome**, **Empresa**
            - Dependentes geralmente têm a coluna Empresa vazia ou em branco
            """)
            uploaded_file = st.file_uploader("Escolha o arquivo Excel", type=["xlsx"])
            if uploaded_file is not None:
                try:
                    df = pd.read_excel(uploaded_file, sheet_name="Sócio", engine="openpyxl")
                    required_cols = ["Matrícula", "Nome", "Empresa"]
                    missing = [col for col in required_cols if col not in df.columns]
                    if missing:
                        st.error(f"Colunas faltando: {', '.join(missing)}")
                    else:
                        df["Matrícula"] = df["Matrícula"].astype(str).str.strip()
                        df["Nome"] = df["Nome"].astype(str).str.strip().str.upper()
                        df["Empresa"] = df["Empresa"].astype(str).str.strip().str.upper().replace(["NAN", "nan", ""], None)
                        df["tipo"] = df["Empresa"].apply(lambda x: "Titular" if pd.notna(x) else "Dependente")
                        df = df.dropna(subset=["Matrícula", "Nome"])
                        df = df[df["Matrícula"].str.strip() != ""]
                        st.success(f"Foram encontrados **{len(df)}** registros válidos.")
                        st.subheader("Pré-visualização (primeiros 10)")
                        st.dataframe(df.head(10), use_container_width=True)

                        if st.button("IMPORTAR PARA O BANCO", type="primary"):
                            with st.spinner("Importando..."):
                                conn = sqlite3.connect(DB_NAME)
                                cursor = conn.cursor()
                                inserted = 0
                                updated = 0
                                for _, row in df.iterrows():
                                    mat = row["Matrícula"]
                                    nome = row["Nome"]
                                    empresa = row["Empresa"]
                                    tipo = row["tipo"]
                                    cursor.execute("SELECT 1 FROM socios WHERE matricula = ?", (mat,))
                                    exists = cursor.fetchone() is not None
                                    if exists:
                                        cursor.execute("""
                                            UPDATE socios
                                            SET nome = ?, empresa = ?, tipo = ?
                                            WHERE matricula = ?
                                        """, (nome, empresa, tipo, mat))
                                        updated += 1
                                    else:
                                        cursor.execute("""
                                            INSERT INTO socios (matricula, nome, empresa, tipo)
                                            VALUES (?, ?, ?, ?)
                                        """, (mat, nome, empresa, tipo))
                                        inserted += 1
                                conn.commit()
                                conn.close()
                            st.success(f"Importação finalizada!\nNovos: **{inserted}**\nAtualizados: **{updated}**")
                            st.balloons()
                except Exception as e:
                    st.error(f"Erro ao ler/processar o arquivo: {str(e)}")
                    st.info("Verifique se o arquivo tem a aba 'Sócio' e as colunas corretas.")

        # As outras seções (Prestadores, Diretoria, Relatório, Redefinir Senhas) 
        # permanecem exatamente como no seu código original
        # Se quiser que eu inclua alguma delas atualizada também, avise

        # Fim das seções principais
