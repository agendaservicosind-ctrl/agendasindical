importar streamlit como st

importar sqlite3

import pandas as pd

Importe data e hora a partir de datetime e timedelta.

importar dados unicode

importar base64

importar os

importar io

import hashlib

importar segredos



st.set_page_config(

    título_da_página="Sistema Sindical",

    layout="amplo",

    page_icon="logo.png",

    initial_sidebar_state="expandido"

)



DB_DIR = os.path.dirname(os.path.abspath(__file__))

DB_NAME = os.path.join(DB_DIR, "union.db")



SERVIÇOS = [

    "Odontologia", "Psicologia", "Direito", "Cabeleireiro", "Manicure"

    "Eletricista", "Jardineiro", "Pedreiro"

]



UNIDADES = [

    "Quartel-General de Jundiaí",

    "Sub Sede Franco da Rocha",

    "Jundiaí externo",

    "Franco da Rocha externo"

]



NIVEIS_ACESSO = ["Mestre", "ADM", "Recepção", "Provedor"]

SCHEDULES = [f"{h:02d}:{m:02d}" para h em range(8, 18) para m em (0, 30)]

SENHA_INICIAL = "União@2026!"



# ================= FUNÇÕES DE SENHA ==================

def hash_password(password: str) -> str:

    sal = secrets.token_hex(16)

    hash = hashlib.sha256((salt + password).encode('utf-8')).hexdigest()

    retornar f"{salt}${hashed}"



def verificar_senha(fornecido: str, armazenado) -> bool:

    Se o valor armazenado for None:

        retornar Falso

    se isinstance(stored, (bytes, bytearray)):

        tentar:

            armazenado = armazenado.decodificar('utf-8')

        exceto:

            retornar Falso

    armazenado = str(armazenado).strip()

    fornecido = str(fornecido).strip()

    se não estiver armazenado:

        retornar Falso

    Se '$' não estiver armazenado:

        retorno armazenado == fornecido

    tentar:

        sal, hash = armazenado.split('$', 1)

        computado = hashlib.sha256((salt + fornecido).encode('utf-8')).hexdigest()

        retornar calculado == hash

    exceto:

        retornar Falso



# ================== FUNÇÕES AUXILIARES ==================

def normalize_for_db(text: str) -> str:

    se não for texto ou não for uma instância de (texto, str):

        retornar ""

    texto = unicodedata.normalize('NFD', texto.strip())

    texto = ''.join(c para c em texto se unicodedata.category(c) != 'Mn')

    retornar texto.maiúsculo()



def normalize_matricula(mat: str) -> str:

    retornar str(mat ou "").strip().replace(" ", "")



def limpar_cpf(valor):

    retornar "".join(c para c em str(valor ou "") se c.édigito())



def format_phone(value):

    valor = limpar_cpf(valor)

    se len(valor) == 11:

        retornar f"({valor[:2]}) {valor[2:7]}-{valor[7:]}"

    se len(valor) == 10:

        retornar f"({valor[:2]}) {valor[2:6]}-{valor[6:]}"

    valor de retorno



# ================== BANCO DE DADOS ==================

def init_db():

    com sqlite3.connect(DB_NAME) como conexão:

        cursor = conn.cursor()

        cursor.execute('''

            CRIAR TABELA SE NÃO EXISTIR parceiros (

                TEXTO de registro,

                nome TEXTO,

                Empresa de TEXTO,

                texto cpf,

                SMS,

                Tipo de texto padrão: 'Título'

            )

        ''')

        para coluna em ['company', 'cpf', 'phone', 'type']:

            tentar:

                cursor.execute(f"ALTER TABLE partners ADD COLUMN {coluna} TEXT")

            exceto sqlite3.OperationalError:

                passar

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_matricula ON associates(matricula)")



        cursor.execute('''

            CRIAR TABELA SE NÃO EXISTIR usuários (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                nome de usuário TEXTO ÚNICO NÃO NULO,

                senha TEXTO NÃO NULO,

                access_type TEXT NOT NULL,

                senha_padrao INTEIRO PADRÃO 1

            )

        ''')

        cursor.execute('''

            CRIAR TABELA SE NÃO EXISTIR provedores (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                nome TEXTO NÃO NULO,

                texto cpf,

                unidade TEXTO NÃO NULO,

                tipo_de_serviço TEXTO NÃO NULO

            )

        ''')

        cursor.execute('''

            CRIAR TABELA SE NÃO EXISTIR diretórios (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                nome TEXTO NÃO NULO,

                texto cpf,

                área_responsavel TEXTO,

                nível_de_acesso TEXTO,

                nome de usuário TEXTO,

                foto BLOB

            )

        ''')

        cursor.execute('''

            CRIAR TABELA SE NÃO EXISTIR agendas (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                texto de registro de parceiros,

                nome_socio TEXTO NÃO NULO,

                texto da empresa parceira,

                texto do parceiro de telefone,

                service_type TEXT NOT NULL,

                unidade TEXTO NÃO NULO,

                prestador_nome TEXTO NÃO NULO,

                data_atendimento TEXTO NÃO NULO,

                agendar TEXTO NÃO NULO,

                status TEXTO PADRÃO 'Pendente',

                texto do diretor do candidato NÃO NULO,

                servant_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                data_realizado TIMESTAMP,

                validado_por TEXTO

            )

        ''')

        tentar:

            cursor.execute("ALTER TABLE agendas ADD COLUMN data_made TIMESTAMP")

        exceto:

            passar

        tentar:

            cursor.execute("ALTER TABLE agendas ADD COLUMN validated_by TEXT")

        exceto:

            passar

        conexão.commit()



def corrigir_coluna_foto():

    com sqlite3.connect(DB_NAME) como conexão:

        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(directories)")

        colunas = {col[1] for col in cursor.fetchall()}

        Se 'foto' não estiver em colunas:

            cursor.execute("ALTER TABLE directors ADD COLUMN photo BLOB")

            conexão.commit()



init_db()

foto_coluna_correta()



se 'user_data' não estiver em st.session_state:

    st.session_state.user_data = None

se 'forcar_troca_senha' não estiver em st.session_state:

    st.session_state.forcar_troca_senha = Falso



# ─── LOGIN ───────────────────────────────────── ─────────────────────────────────────

Se st.session_state.user_data for None:

    st.title("Login - Sistema Union")

    com st.form("login_form"):

        nome_de_usuário = st.text_input("Usuário")

        senha = st.text_input("Senha", type="senha")

        if st.form_submit_button("Enter", type="primary"):

            se não username.strip():

                st.error("Digite o nome de usuário.")

            senão se não for senha:

                st.error("Digite a senha.")

            outro:

                com sqlite3.connect(DB_NAME) como conexão:

                    usuário = conn.execute(

                        "SELECT username, password, access_type, senha_padrao FROM users WHERE UPPER(username) = ?",

                        (username.strip().upper(),)

                    ).fetchone()

                se o usuário:

                    nome_usuário_armazenado, senha_armazenada, tipo_armazenado, senha_padrao = usuário

                    se isinstance(stored_password, (bytes, bytearray)):

                        senha_armazenada = senha_armazenada.decode('utf-8', erros='replace')

                    se check_password(senha, senha_armazenada):

                        st.session_state.user_data = {

                            "nome de usuário": nome_de_usuário_armazenado,

                            "tipo": stored_type.strip().lower(),

                        }

                        st.session_state.forcar_troca_senha = bool(senha_padrao)

                        se senha_padrao:

                            st.info("Sua senha está em branco. Por motivos de segurança, altere-a agora.")

                        st.success("Login realizado com sucesso!")

                        st.rerun()

                    outro:

                        st.error("Senha incorreta.")

                outro:

                    st.error("Usuário não encontrado.")

outro:

    user_info = st.session_state.user_data

    user_type = user_info["type"].lower()

    nome_usuário = informações_do_usuário["nome de usuário"]

    photo_bytes = Nenhum

    com sqlite3.connect(DB_NAME) como conexão:

        cursor = conn.cursor()

        cursor.execute("SELECT photo FROM directores WHERE username = ?", (nome_user,))

        resultado = cursor.fetchone()

        se resultado e resultado[0]:

            photo_bytes = result[0]

    com st.sidebar:

        se foto_bytes:

            foto_base64 = base64.b64encode(foto_bytes).decode('utf-8')

            col_foto, col_texto = st.columns([1, 3])

            com col_foto:

                st.markdown(

                    F"""

                    <div style="text-align:center; margin:10px 0;">

                        <img src="data:image/jpeg;base64,{photo_base64}"

                             estilo="largura:80px; altura:80px; raio da borda:50%;

                                    object-fit:cover; border:3px solid #e0e0e0;

                                    box-shadow:0 4px 12px rgba(0,0,0,0.15);">

                    </div>

                    "",

                    unsafe_allow_html=True

                )

            com col_texto:

                st.markdown(f"<h4 style='margin:12px 0 0 0;'>{nome_user.upper()}</h4>", unsafe_allow_html=True)

                st.markdown(f"<small>({user_type.upper()})</small>", unsafe_allow_html=True)

        outro:

            st.markdown(f"👤 **{nome_usuário.upper()}** ({tipo_usuário.upper()})")

        st.markdown("---")



    if st.session_state.forcar_troca_senha:

        st.title("Alterar Senha Inicial (obrigatório)")

        st.warning(f"Olá {nome_user.upper()}, defina uma nova senha agora.")

        com st.form("form_troca_senha"):

            nova_senha = st.text_input("Nova senha", type="senha")

            confirm = st.text_input("Confirme a nova senha", type="password")

            if st.form_submit_button("Confirm", type="primary"):

                se não for nova_senha ou len(nova_senha) < 6:

                    st.error("A deve ter pelo menos 6 caracteres.")

                elif nova_senha != confirm:

                    st.error("As senhas não coincidem.")

                elif nova_senha == SENHA INICIAL:

                    st.error("Não use a senha inicial novamente.")

                outro:

                    hash = hash_senha(nova_senha)

                    hashed = str(hashed) # Garante que seja uma string pura

                    st.write("DEBUG - Novo hash gerado (primeiros 50 caracteres):", hashed[:50])

                    tentar:

                        com sqlite3.connect(DB_NAME) como conexão:

                            conn.execute("UPDATE users SET password = ?, senha_padrao = 0 WHERE username = ?",

                                         (hash, nome de usuário)

                            conexão.commit()

                        st.success("Senha alterada com sucesso! Faça login novamente com uma nova senha.")

                        st.session_state.user_data = None

                        st.session_state.forcar_troca_senha = Falso

                        st.rerun()

                    exceto Exception como e:

                        st.error(f"ERRO AO SALVAR NOVA SENHA: {str(e)}")

                        st.info("Possível causa: problema com o banco ou valor inválido. Por favor, utilize métodos mais simples (sem caracteres especiais) ou entre em contato conosco para obter suporte.")

    outro:

        # Menus de Navegação

        se tipo_user == "prestador":

            menu = ["Minhas Agendas", "Sair"]

        outro:

            menu = ["Programação", "Participantes"]

            se user_type estiver em ["master", "adm", "reception"]:

                menu.extend(["Provedores", "Diretório"])

            se user_type estiver em ["master", "adm"]:

                menu.append("Parceiros de Importação")

            se user_type == "master":

                menu.extend(["Relatório de Serviço", "Redefinir Senhas"])

            menu.append("Sair")

        escolha = st.sidebar.radio("Navegação", menu)

        se escolha == "Sair":

            st.session_state.user_data = None

            st.rerun()



        # ─── CRONOGRAMA ───────────────────────────────── ─────────────────────────────────

        se escolha == "Agenda":

            st.title("Nova Agenda")

            pesquisa = st.text_input("Pesquisar parceiro ou dependente (registro ou nome)")

            parceiro_encontrado = Nenhum

            se busca.strip():

                clean_search = normalize_matricula(search.strip())

                search_nome = f"%{normalize_for_db(search.strip())}%"

                com sqlite3.connect(DB_NAME) como conexão:

                    linhas = conn.execute("""

                        SELECIONE registro, nome, empresa, telefone, tipo

                        DE parceiros

                        ONDE matrícula = ?

                        ENCOMENDAR POR

                            CASO QUANDO tipo = 'Holder' ENTÃO 0 SENÃO 1 FIM,

                            nome

                    "", (find_find,)).fetchall()

                    se não houver linhas:

                        linhas = conn.execute("""

                            SELECIONE registro, nome, empresa, telefone, tipo

                            DE parceiros

                            ONDE UPPER(nome) COMO? OU registro COMO?

                            ENCOMENDAR POR

                                CASO QUANDO tipo = 'Holder' ENTÃO 0 SENÃO 1 FIM,

                                nome

                        """, (search_nome, f"%{search_limpa}%")).fetchall()

                se houver linhas:

                    st.info(f"Encontrados {len(rows)} registros.")

                    se len(linhas) == 1:

                        parceiro_encontrado = linhas[0]

                        st.success(f"Encontrado: {found_partner[1]} ({found_partner[4]})")

                    outro:

                        opcoes = []

                        para r em linhas:

                            text_type = "Proprietário" se r[4] == "Proprietário" senão "Dependente"

                            opcoes.append(f"{r[1]} ({text_type}) – Matr. {r[0]}")

                        escolha_idx = st.radio(

                            "Selecione o que você vai usar ou o serviço:"

                            intervalo(comprimento(opcoes)),

                            format_func=lambda i: opcoes[i],

                            índice=0

                        )

                        parceiro_encontrado = linhas[escolha_idx]

                outro:

                    st.warning("Nenhum parceiro ou dependente encontrado.")

            se socio_encontrado:

                mat, nome_def, emp_def, tel_def_db, type_pessoa = parceiro_fundado

                tel_def = format_telefone(tel_def_db) se tel_def_db senão ""

                campos_desativados = Verdadeiro

                nao_associado = Falso

                st.caption(f"**Tipo:** {type_pessoa}")

            senão se search.strip():

                tapete = "N/A"

                nome_def = emp_def = tel_def = ""

                campos_desativados = Falso

                nao_associado = True

            outro:

                mat = nome_def = emp_def = tel_def = ""

                campos_desativados = Falso

                nao_associado = Falso

            st.markdown("---")

            col1, col2 = st.columns(2)

            serv_default = st.session_state.get('agendamento_servico', SERVICES[0])

            Se serv_default não estiver em SERVICES:

                serv_default = SERVICES[0]

            servico = col1.selectbox("Serviço solicitado", SERVICOS, index=SERVICOS.index(serv_default))

            st.session_state.servico_agendamento = serviço

            uni_default = st.session_state.get('agendamento_unit', UNITS[0])

            se uni_default não estiver em UNITS:

                uni_default = UNIDADES[0]

            unidade = col2.selectbox("Unidade de Serviço", UNIDADES, índice=UNITAS.index(uni_default))

            st.session_state.unite_agendamento = unidade

            com sqlite3.connect(DB_NAME) como conexão:

                serv_norm = normalize_for_db(servico)

                uni_norm = normalizar_para_db(unit)

                se "Externo" na unidade:

                    consulta = "SELECT nome FROM providers WHERE service_type = ? ORDER BY nome"

                    parâmetros = (serv_norm,)

                outro:

                    consulta = "SELECT nome FROM providers WHERE unit = ? AND service_type = ? ORDER BY nome"

                    parâmetros = (norma_uni, norma_serv)

                resultado = conn.execute(query, params).fetchall()

                lista_provedor = [r[0].strip() para r em resultado se r e r[0] e r[0].strip()]

            se lista_prestadores:

                perst_default = st.session_state.get('agendamento_provider', provider_list[0])

                se perst_default não estiver em provider_list:

                    perst_default = lender_list[0]

                provedor = st.selectbox("Credor / Responsável", list_provedores,

                                         index=list_providers.index(prest_default))

                st.session_state.prestador_agendamento = provedor

            outro:

                st.warning(f"Nenhum provedor encontrado para {servico} em {unite}.")

                credor = Nenhum

            st.markdown("---")

            com st.form("form_agendamento", clear_on_submit=True):

                col1, col2 = st.columns(2)

                nome = col1.text_input("Nome completo", value=nome_def, disabled=fields_disabled)

                empresa = col2.text_input("Empresa / Local de Trabalho", value=emp_def, disabled=campos_disabled)

                telefone_raw = col1.text_input("Telefone para contato", value=tel_def, disabled=campos_disabled)

                telefone = limpar_cpf(telefone_raw)

                data_atendimento = col2.date_input("Dados do atendimento", min_value=date.today(),

                                                   valor_máximo=data.hoje() + timedelta(dias=120))

                agendamento = col1.selectbox("Agendamentos disponíveis", HORÁRIOS)

                requesting_director = col2.text_input("Requesting director", value=nome_user, disabled=True)

                pode_agendar_manual = user_type in ["master", "adm", "recepção"]

                submit_disabled = (nao_associado e não pode_agendar_manual) ou (provider is None)

                se não_associado e não pode_agendar_manual:

                    st.warning("Somente o Mestre, o Administrador Adjunto ou a Recepção podem agendar para não-funcionários.")

                if st.form_submit_button("Confirmar Agendamento", type="primary", disabled=submit_disabled):

                    se não name.strip():

                        st.error("Nome obrigatório.")

                    elifθr é Nenhum:

                        st.error("Por favor, selecione um provedor válido.")

                    outro:

                        data_iso = data_atendimento.strftime("%Y-%m-%d")

                        com sqlite3.connect(DB_NAME) como conexão:

                            conflito = conn.execute("""

                                SELECIONE 1 DE agendamentos

                                ONDE prestador_nome = ?

                                  E data_atendimento = ?

                                  E o cronograma = ?

                                  E o status NÃO ESTÁ EM ('Cancelado', 'Concluído')

                            "", (provedor, data_iso, agendamento)).fetchone()

                            Em caso de conflito:

                                st.error(f"Conflito de agendamento com {provedor}.")

                            outro:

                                conn.execute("""

                                    INSERIR EM agendamentos

                                    (cadastro_de_parceiro, nome_do_parceiro, empresa_do_parceiro, telefone_do_parceiro,

                                     tipo_de_serviço, unidade, nome_do_provedor, dados_do_serviço, agendamento, diretor_solicitante)

                                    VALORES (?,?,?,?,?,?,?,?,?,?)

                                "", (

                                    tapete se tapete != "N/A" senão Nenhum,

                                    nome.strip(),

                                    empresa.strip() ou None,

                                    Telefone ou Nenhum,

                                    serviço,

                                    unidade,

                                    emprestador,

                                    dados_iso,

                                    agendar,

                                    candidato_diretor

                                ))

                                conexão.commit()

                                st.success("Agenda registrada com sucesso!")

                                st.rerun()

        # ─── ATENDIMENTOS / MEUS AGENDAMENTOS ───────────────────────────────────────

        elif escolha in ["Atendimentos", "Meus Agendamentos"]:

            se tipo_user == "prestador":

                st.title("Meus Horários")

                status_filter = st.selectbox("Filtrar por status", ["Todos", "Pendente", "Concluído", "Cancelado"])

            outro:

                st.title("Lista de Presença")

                status_filter = st.selectbox("Filtrar por status", ["Todos", "Pendente", "Concluído", "Cancelado"])

            com sqlite3.connect(DB_NAME) como conexão:

                consulta = """

                    SELECIONE id, nome_do_parceiro, tipo_de_serviço, unidade, dados_do_serviço, agendamento, status, diretor_solicitante

                    DE agendas

                    ONDE 1=1

                """

                parâmetros = []

                se tipo_user == "prestador":

                    consulta += " E nome_do_provedor = ?"

                    params.append(name_user)

                se filter_status != "Todos":

                    consulta += " E status = ?"

                    params.append(filtro_status)

                consulta += "ORDER BY data_atendimento DESC, agendamento DESC"

                df = pd.read_sql_query(query, conn, params=params)

            se df.vazio:

                st.info("Nenhum agendamento encontrado.")

            outro:

                df["Data"] = pd.to_datetime(df["data_atendimento"]).dt.strftime("%d/%m/%Y")

                df = df.drop(columns=["data_atendimento"])

                se tipo_user == "prestador":

                    para _, linha em df.iterrows():

                        se row["status"] == "Pendente":

                            cols = st.columns([5, 1])

                            com cols[0]:

                                st.write(f"**{row['partner_name']}** – {row['service_type']} | {row['unit']} | {row['Data']} {row['schedule']}")

                            com cols[1]:

                                if st.button("✓ Marcar como Concluído", key=f"do_{row['id']}"):

                                    com st.spinner("Validando..."):

                                        com sqlite3.connect(DB_NAME) como conexão:

                                            conn.execute("""

                                                ATUALIZAR agendamento

                                                DEFINIR status = 'Concluído',

                                                    data_realized = CURRENT_TIMESTAMP,

                                                    validado_por = ?

                                                ONDE id = ?

                                            "", (nome_usuário, linha['id']))

                                            conexão.commit()

                                    st.success(f"Serviço marcado como realizado por {nome_user}!")

                                    st.rerun()

                        outro:

                            st.markdown(f"**{row['partner_name']}** – {row['service_type']} | {row['unit']} | {row['Data']} {row['schedule']} **({row['status']})**")

                        st.markdown("---")

                outro:

                    st.dataframe(df, use_container_width=True)

        # ─── FORNECEDORES ─────────────────────────────── ───────────────────────────────

        elif escolha == "Provedores" e user_type em ["master", "adm", "recepção"]:

            st.title("Gestão de Empréstimos")

            com st.expander("Cadastro novo provedor"):

                com st.form("cad_lender", clear_on_submit=True):

                    nome_p = st.text_input("Nome completo do provedor", key="cad_nome_provider")

                    cpf_p = st.text_input("CPF (opcional)", key="cad_cpf_lender")

                    unit_p = st.selectbox("Unidade", UNITS, key="cad_unite_provider")

                    servico_p = st.selectbox("Serviço", SERVICOS, key="cad_servico_prestador")

                    username_p = st.text_input("Nome de usuário para login (ex: CHIUINHO)", key="cad_username_provider")

                    if st.form_submit_button("Cadastrar Provider + Access"):

                        se name_p.strip() e username_p.strip():

                            norma_da_unidade = normalizar_para_db(unidade_p)

                            norma_servico = normalize_for_db(servico_p)

                            nome_de_usuário_limpo = nome_de_usuário_p.strip().upper()

                            conexão = sqlite3.connect(DB_NAME)

                            tentar:

                                conn.execute("BEGIN TRANSACTION")

                                conn.execute("""

                                    INSERT INTO providers (name, cpf, unit, service_type)

                                    VALORES (?, ?, ?, ?)

                                """, (nome_p.strip(), limpar_cpf(cpf_p), unit_norm, servico_norm))

                                cursor = conn.cursor()

                                cursor.execute("SELECT 1 FROM users WHERE username = ?", (username_clean,))

                                se cursor.fetchone():

                                    raise ValueError("Usuário não existe. Digite outro nome.")

                                senha_para_inserir = hash_password(SENHA_INICIAL)

                                conn.execute("""

                                    INSERT INTO users (username, password, access_type, senha_padrao)

                                    VALORES (?, ?, 'Credor', 1)

                                """, (username_clean, senha_para_inserir))

                                conexão.commit()

                                st.success(f"Provedor **{nome_p}** cadastrado!\n\n"

                                           f"**Acesso Creed:**\n"

                                           f"• Usuário: **{username_clean}**\n"

                                           f"• Senha inicial: **{INICIAL_SENHA}**\n"

                                           f"→ Faça login e insira o primeiro acesso."

                                st.rerun()

                            exceto ValueError como ve:

                                se conn.in_transaction:

                                    conexão.rollback()

                                st.error(str(ve))

                            exceto Exception como e:

                                se conn.in_transaction:

                                    conexão.rollback()

                                st.error(f"Erro ao cadastrar: {str(e)}")

                            finalmente:

                                conexão.fechar()

                        outro:

                            st.error("Nome completo e nome de usuário obrigatório.")

            com sqlite3.connect(DB_NAME) como conexão:

                df_p = pd.read_sql_query("SELECT id, nome, cpf, unit, service_type FROM providers ORDER BY nome", conn)

            se df_p.vazio:

                st.info("Provedor Nenhum cadastrado.")

            outro:

                para _, linha em df_p.iterrows():

                    expander_key = f"prest_exp_{row['id']}"

                    com st.expander(f"{row['nome']} – {row['service_type']} ({row['unit']})", expanded=False):

                        col1, col2 = st.columns([4, 1])

                        com col1:

                            com st.form(f"edit_prest_{row['id']}"):

                                nome_edit = st.text_input("Nome", value=row['nome'], key=f"nome_edit_{row['id']}")

                                cpf_edit = st.text_input("CPF", value=row['cpf'] or "", key=f"cpf_edit_{row['id']}")

                                unit_edit = st.selectbox("Unidade", UNITS, index=UNITS.index(row['unit']) if row['unit'] in UNITS else 0, key=f"uni_edit_{row['id']}")

                                servico_edit = st.selectbox("Serviço", SERVICOS, index=SERVICOS.index(row['tipo_servico']) if row['tipo_servico'] em SERVICOS else 0, key=f"serv_edit_{row['id']}")

                                if st.form_submit_button("Salvar alterações", key=f"save_prest_{row['id']}"):

                                    norma_da_unidade = normalizar_para_db(edição_da_unidade)

                                    norma_servico = normalize_for_db(servico_edit)

                                    com sqlite3.connect(DB_NAME) como conexão:

                                        conn.execute("""

                                            ATUALIZAR fornecedores

                                            DEFINIR nome = ?, cpf = ?, unidade = ?, tipo_de_serviço = ?

                                            ONDE id = ?

                                        """, (nome_edit.strip(), limpar_cpf(cpf_edit), unit_norm, servico_norm, row['id']))

                                        conexão.commit()

                                    st.success("Provedor atualizado!")

                                    st.rerun()

                        com col2:

                            if st.button("Excluir", key=f"del_btn_prest_{row['id']}"):

                                st.session_state[f"show_confirm_del_prest_{row['id']}"] = True

                            se st.session_state.get(f"show_confirm_del_prest_{row['id']}", False):

                                st.warning("Tem certeza de que deseja excluir este provedor?")

                                col_del1, col_del2 = st.columns(2)

                                com col_del1:

                                    if st.button("Sim, excluir", key=f"conf_del_prest_{row['id']}", type="primary"):

                                        conexão = sqlite3.connect(DB_NAME)

                                        tentar:

                                            cursor = conn.cursor()

                                            cursor.execute("SELECT nome FROM providers WHERE id = ?", (row['id'],))

                                            perst_nome_raw = cursor.fetchone()

                                            se prest_nome_raw:

                                                perst_nome_clean = perst_nome_raw[0].upper().replace(" ", "")

                                                conn.execute("DELETE FROM users WHERE username = ?", (prest_nome_clean,))

                                            conn.execute("DELETE FROM providers WHERE id = ?", (row['id'],))

                                            conexão.commit()

                                            st.success(f"Provedor **{row['nome']}** e possível acesso associado excluídos!")

                                            st.rerun()

                                        exceto Exception como e:

                                            se conn.in_transaction:

                                                conexão.rollback()

                                            st.error(f"Erro ao excluir: {str(e)}")

                                        finalmente:

                                            conexão.fechar()

                                com col_del2:

                                    if st.button("Cancelar", key=f"cancel_del_prest_{row['id']}"):

                                        st.session_state[f"show_confirm_del_prest_{row['id']}"] = False

                                        st.rerun()

        # ─── DIRETÓRIO ──────────────────────────────── ────────────────────────────────

        elif escolha == "Diretório" e user_type em ["master", "adm", "recepção"]:

            st.title("Gerenciamento de diretórios")

            é_mestre = (tipo_de_usuário == "mestre")

            com st.expander("Cadastrar novo usuário (diretor ou provedor)" se is_master senão "Somente o Master pode cadastrar"):
