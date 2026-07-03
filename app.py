import streamlit as st
import pandas as pd
import random
import itertools
import os
import csv
import requests
import math
import mercadopago
import time
from dotenv import load_dotenv
from sklearn.ensemble import RandomForestRegressor
from sklearn.neighbors import KNeighborsRegressor
from sklearn.neural_network import MLPRegressor

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="GeraLoto - Premium", page_icon="🎲", layout="wide")
load_dotenv()

# --- CHAVES E TOKENS ---
FIREBASE_WEB_API_KEY = os.environ.get("FIREBASE_WEB_API_KEY", "AIzaSyARvB207Vwg3ghFq5MDi-YVKjBKpXM7evg")
PROJECT_ID = os.environ.get("PROJECT_ID", "geraloto-lotogera")
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN") # Puxa do arquivo .env

# ==========================================
# 1. FUNÇÕES DO BANCO DE DADOS (FIRESTORE)
# ==========================================
def obter_saldo_nuvem(uid, id_token):
    url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents/usuarios/{uid}"
    headers = {"Authorization": f"Bearer {id_token}"}
    
    try:
        resposta = requests.get(url, headers=headers)
        
        if resposta.status_code == 200:
            dados = resposta.json()
            # Retorna o valor real do banco
            return int(dados['fields']['fichas']['integerValue'])
        
        elif resposta.status_code == 404:
            # Usuário novo, ganha 1000 de bônus
            atualizar_saldo_nuvem(uid, id_token, 1000)
            return 1000
        else:
            # Erro de API (ex: erro de permissão), avisa no sidebar e retorna 0
            st.sidebar.error("Erro ao carregar saldo do servidor.")
            return 0
            
    except Exception as e:
        # Falha de conexão, avisa no sidebar e retorna 0
        st.sidebar.error("Sem conexão com o banco de dados.")
        return 0

def atualizar_saldo_nuvem(uid, id_token, novo_saldo):
    url = f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}/databases/(default)/documents/usuarios/{uid}"
    headers = {"Authorization": f"Bearer {id_token}"}
    payload = {"fields": {"fichas": {"integerValue": str(novo_saldo)}}}
    requests.patch(url, headers=headers, json=payload)

# ==========================================
# 2. FUNÇÕES DE AUTENTICAÇÃO (FIREBASE)
# ==========================================
def registar_utilizador(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signUp?key={FIREBASE_WEB_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    return requests.post(url, json=payload).json()

def iniciar_sessao(email, password):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FIREBASE_WEB_API_KEY}"
    payload = {"email": email, "password": password, "returnSecureToken": True}
    return requests.post(url, json=payload).json()

def redefinir_senha(email):
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode?key={FIREBASE_WEB_API_KEY}"
    payload = {"requestType": "PASSWORD_RESET", "email": email}
    return requests.post(url, json=payload).json()

# ==========================================
# 3. PAGAMENTO E SINCRONIZAÇÃO (MERCADO PAGO)
# ==========================================
def gerar_link_pagamento(uid, preco, qtd_fichas, ref_id):
    sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
    dados = {
        "items": [{"title": f"{qtd_fichas} Fichas - GeraLoto Premium", "quantity": 1, "unit_price": float(preco)}],
        "external_reference": ref_id,  # <-- Agora usa o recibo único
        "back_urls": {"success": "https://geraloto.streamlit.app/", "pending": "https://geraloto.streamlit.app/"},
        "auto_return": "approved"
    }
    try:
        res = sdk.preference().create(dados)
        return res["response"]["init_point"]
    except:
        return None

def verificar_e_creditar_pagamentos(uid, id_token, saldo_atual):
    ref_id = st.session_state.get("payment_ref")
    fichas_para_adicionar = st.session_state.get("fichas_a_adicionar", 0)
    
    # Trava de segurança: Se não houver compra iniciada, ele barra na hora
    if not ref_id or fichas_para_adicionar == 0:
        st.sidebar.warning("Você precisa gerar um link de pagamento primeiro.")
        return

    sdk = mercadopago.SDK(MP_ACCESS_TOKEN)
    # Busca especificamente o recibo único desta compra
    filtros = {"external_reference": ref_id, "status": "approved"}
    
    try:
        busca = sdk.payment().search(filtros)
        pagamentos = busca.get("response", {}).get("results", [])
        
        if pagamentos:
            st.sidebar.success("💳 Pagamento aprovado encontrado!")
            novo_saldo = saldo_atual + fichas_para_adicionar
            
            atualizar_saldo_nuvem(uid, id_token, novo_saldo)
            st.session_state["fichas"] = novo_saldo
            
            # Apaga o recibo da memória para não creditar de novo
            st.session_state["payment_ref"] = None
            st.session_state["fichas_a_adicionar"] = 0 
            
            st.toast(f"{fichas_para_adicionar} Fichas creditadas com sucesso! 🎉")
            st.rerun()
        else:
            st.sidebar.warning("Pagamento ainda não aprovado ou não encontrado.")
    except Exception as e:
        st.sidebar.error("Erro ao verificar pagamentos.")

# ==========================================
# 4. TELA DE LOGIN / REGISTRO
# ==========================================
if "user_uid" not in st.session_state:
    st.title("🔒 Bem-vindo ao GeraLoto Premium")
    st.write("Inicie sessão ou crie uma conta para acessar o sistema de previsões.")
    
    escolha = st.radio("Selecione uma opção:", ["Iniciar Sessão", "Criar Conta Nova", "Esqueci minha senha"])
    email_input = st.text_input("E-mail")
    
    # Oculta o campo de senha se o usuário estiver recuperando a conta
    if escolha != "Esqueci minha senha":
        senha_input = st.text_input("Senha (Mínimo 6 caracteres)", type="password")
    
    if escolha == "Criar Conta Nova" and st.button("Registrar Conta"):
        if email_input and senha_input:
            with st.spinner("Criando conta..."):
                res = registar_utilizador(email_input, senha_input)
                if "error" in res: st.error(res["error"]["message"])
                else: st.success("Conta criada! Pode iniciar sessão agora.")
        else:
            st.warning("Preencha e-mail e senha.")
                    
    elif escolha == "Iniciar Sessão" and st.button("Entrar no Sistema"):
        if email_input and senha_input:
            with st.spinner("Autenticando..."):
                res = iniciar_sessao(email_input, senha_input)
                if "error" in res: st.error("Credenciais inválidas.")
                else:
                    st.session_state["user_uid"] = res["localId"]
                    st.session_state["user_email"] = res["email"]
                    st.session_state["id_token"] = res["idToken"]
                    # 🌟 FORÇA A BUSCA DO SALDO IMEDIATAMENTE
                    st.session_state["fichas"] = obter_saldo_nuvem(res["localId"], res["idToken"])
                    st.rerun()
        else:
            st.warning("Preencha e-mail e senha.")
            
    elif escolha == "Esqueci minha senha" and st.button("Enviar e-mail de recuperação"):
        if email_input:
            with st.spinner("Processando..."):
                res = redefinir_senha(email_input)
                if "error" in res: 
                    st.error("Erro ao enviar e-mail. Verifique se o endereço está correto.")
                else: 
                    st.success("✅ E-mail de recuperação enviado! Verifique sua caixa de entrada e também a pasta de Spam.")
        else:
            st.warning("Por favor, digite seu e-mail acima para receber o link de recuperação.")
            
    st.stop()

# ==========================================
# 5. BARRA LATERAL (PERFIL E LOJA)
# ==========================================
st.sidebar.title("👤 Seu Perfil")
st.sidebar.success(f"**Usuário:**\n{st.session_state['user_email']}")

if "fichas" not in st.session_state:
    st.session_state["fichas"] = obter_saldo_nuvem(st.session_state["user_uid"], st.session_state["id_token"])

st.sidebar.info(f"🪙 **Saldo:** {st.session_state['fichas']} fichas")
st.sidebar.markdown("---")

# LOJA DE FICHAS 
st.sidebar.subheader("🛒 Recarregar Fichas")
opcoes_pacotes = {"1.000 Fichas = R$ 10,00": (10.00, 1000), "2.500 Fichas = R$ 22,00": (22.00, 2500)}
escolha_pacote = st.sidebar.selectbox("Escolha um pacote:", list(opcoes_pacotes.keys()))
preco, fichas_pacote = opcoes_pacotes[escolha_pacote]

if st.sidebar.button("Gerar Link de Pagamento"):
    # Cria o recibo único (Ex: seu_id_1714500000)
    ref_id_unico = f"{st.session_state['user_uid']}_{int(time.time())}"
    
    link = gerar_link_pagamento(st.session_state["user_uid"], preco, fichas_pacote, ref_id_unico)
    if link:
        st.sidebar.link_button("💳 Pagar Agora (Mercado Pago)", link)
        # Salva o recibo e as fichas na memória
        st.session_state["payment_ref"] = ref_id_unico
        st.session_state["fichas_a_adicionar"] = fichas_pacote
        st.sidebar.caption("Após pagar, clique em Sincronizar Saldo abaixo.")
    else:
        st.sidebar.error("Erro ao gerar pagamento.")

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Sincronizar Saldo"):
    with st.sidebar.spinner("Verificando..."):
        verificar_e_creditar_pagamentos(st.session_state["user_uid"], st.session_state["id_token"], st.session_state["fichas"])

if st.sidebar.button("🚪 Sair (Logout)"):
    st.session_state.clear()
    st.rerun()
    
# ==========================================
# 6. MOTOR DO GERADOR (IA E MATEMÁTICA)
# ==========================================
class GeradorLoterias:
    def __init__(self, caminho_historico, total_bolas_sorteadas, faixa_numeros, caminho_gerados):
        self.caminho_historico = caminho_historico
        self.caminho_gerados = caminho_gerados
        self.total_bolas = total_bolas_sorteadas
        self.faixa_numeros = faixa_numeros
        self.historico_lista = [] 
        self.historico_oficial = self._carregar_historico()
        self.historico_gerados = self._carregar_gerados()
        self.jogos_proibidos = self.historico_oficial.union(self.historico_gerados)

    def obter_ultimo_concurso(self):
        try:
            try: df = pd.read_csv(self.caminho_historico, encoding='latin1', sep=',', header=0)
            except: df = pd.read_csv(self.caminho_historico, encoding='latin1', sep=';', header=0)
            coluna_zero = df.iloc[:, 0].dropna().astype(str)
            return coluna_zero[coluna_zero.str.strip() != ''].iloc[-1]
        except Exception as e: return f"Erro: {e}"

    def resetar_gerados(self):
        if os.path.exists(self.caminho_gerados):
            os.remove(self.caminho_gerados)
            self.historico_gerados = set()
            self.jogos_proibidos = self.historico_oficial 
            return True
        return False

    def _carregar_historico(self):
        jogos_oficiais = set()
        self.historico_lista = []
        if not os.path.exists(self.caminho_historico): return jogos_oficiais
        with open(self.caminho_historico, mode='r', encoding='latin1') as ficheiro:
            leitor = csv.DictReader(ficheiro, delimiter=',')
            if 'Bola1' not in leitor.fieldnames:
                ficheiro.seek(0)
                leitor = csv.DictReader(ficheiro, delimiter=';')
            for linha in leitor:
                try:
                    jogo = [int(linha[f'Bola{i}']) for i in range(1, self.total_bolas + 1)]
                    jogo_ordenado = tuple(sorted(jogo))
                    jogos_oficiais.add(jogo_ordenado)
                    self.historico_lista.append(list(jogo_ordenado))
                except: continue
        return jogos_oficiais

    def _carregar_gerados(self):
        jogos = set()
        if os.path.exists(self.caminho_gerados):
            with open(self.caminho_gerados, mode='r', encoding='utf-8') as f:
                for linha in csv.reader(f):
                    if not linha or 'Bola' in str(linha[0]): continue
                    try: jogos.add(tuple(sorted([int(x) for x in linha])))
                    except: continue
        return jogos

    def _salvar_gerados(self, novos_jogos):
        if not novos_jogos: return
        arquivo_existe = os.path.exists(self.caminho_gerados)
        with open(self.caminho_gerados, mode='a', newline='', encoding='utf-8') as f:
            escritor = csv.writer(f)
            if not arquivo_existe:
                escritor.writerow([f'Bola{i}' for i in range(1, len(novos_jogos[0]) + 1)])
            for jogo in novos_jogos: escritor.writerow(jogo)

    def _gerar_base_equilibrada(self, tamanho):
        pares = [n for n in range(2, self.faixa_numeros + 1, 2)]
        impares = [n for n in range(1, self.faixa_numeros + 1, 2)]
        qtd_pares = min(tamanho // 2, len(pares))
        qtd_impares = tamanho - qtd_pares
        if qtd_impares > len(impares):
            qtd_impares = len(impares)
            qtd_pares = tamanho - qtd_impares
        return sorted(random.sample(pares, qtd_pares) + random.sample(impares, qtd_impares))

    def _gerar_base_com_ml(self, tamanho_base, modelo_escolhido):
        if len(self.historico_lista) < 10: return sorted(random.sample(range(1, self.faixa_numeros + 1), tamanho_base))
        X = self.historico_lista[:-1]
        y = self.historico_lista[1:]
        ultimo_sorteio = [self.historico_lista[-1]]

        if modelo_escolhido == "Random Forest": modelo = RandomForestRegressor(n_estimators=50, random_state=42)
        elif modelo_escolhido == "KNN (Vizinhos Próximos)": modelo = KNeighborsRegressor(n_neighbors=5)
        elif modelo_escolhido == "Rede Neural (MLP)": modelo = MLPRegressor(hidden_layer_sizes=(50, 50), max_iter=500, random_state=42)
        else: modelo = RandomForestRegressor()

        modelo.fit(X, y)
        previsao = modelo.predict(ultimo_sorteio)[0]

        numeros_preditos = set()
        for p in previsao:
            num = int(round(p))
            num = max(1, min(self.faixa_numeros, num))
            numeros_preditos.add(num)

        while len(numeros_preditos) < tamanho_base: numeros_preditos.add(random.randint(1, self.faixa_numeros))
        return sorted(list(numeros_preditos))[:tamanho_base]

    def gerar_jogos(self, tamanho_base, tamanho_bilhete, tecnica='simples', equilibrar=False, usar_ml=False, modelo_ml=None, quantidade_pedida=1):
        jogos_validados = []
        
        if tecnica == 'desdobramento' and tamanho_base > self.total_bolas:
            # Sem limite de tentativas e sem travas de histórico. Apenas gera e aceita na hora.
            base = self._gerar_base_com_ml(tamanho_base, modelo_ml) if usar_ml else (self._gerar_base_equilibrada(tamanho_base) if equilibrar else sorted(random.sample(range(1, self.faixa_numeros + 1), tamanho_base)))
            
            # Cria o desdobramento matemático completo
            possiveis = list(itertools.combinations(base, tamanho_bilhete))
            jogos_validados.extend(possiveis)
            
        else:
            # Modo Jogo Único também sem verificação de histórico
            while len(jogos_validados) < quantidade_pedida:
                jogo = tuple(self._gerar_base_com_ml(tamanho_base, modelo_ml)) if usar_ml else (tuple(self._gerar_base_equilibrada(tamanho_base)) if equilibrar else tuple(sorted(random.sample(range(1, self.faixa_numeros + 1), tamanho_base))))
                jogos_validados.append(jogo)
                
        # Salva o log apenas por controle, mas não barra as próximas gerações
        self._salvar_gerados(jogos_validados)
        
        return jogos_validados

# ==========================================
# 7. INTERFACE PRINCIPAL
# ==========================================
st.title("🎲 Gerador de Jogos Premium")

modalidade = st.selectbox("Escolha a Modalidade:", ["Mega-Sena", "Lotofácil"])
modo_geracao = st.radio("Motor de Geração:", ["Tradicional / Aleatório", "Inteligência Artificial 🧠"])

if modalidade == "Mega-Sena":
    arquivo_selecionado = "Mega-Sena.csv"; arquivo_gerados = "jogos_ja_gerados_mega.csv"
    total_bolas = 6; faixa_maxima = 60; min_permitido = 6; max_permitido = 20
else:
    arquivo_selecionado = "Lotofacil.csv"; arquivo_gerados = "jogos_ja_gerados_lotofacil.csv"
    total_bolas = 15; faixa_maxima = 25; min_permitido = 15; max_permitido = 20

@st.cache_resource
def carregar_gerador(caminho, bolas, faixa, arq_gerados): 
    return GeradorLoterias(caminho, bolas, faixa, arq_gerados)

if not os.path.exists(arquivo_selecionado):
    st.error(f"Erro: O arquivo '{arquivo_selecionado}' não foi encontrado. Adicione o histórico na mesma pasta.")
else:
    gerador = carregar_gerador(arquivo_selecionado, total_bolas, faixa_maxima, arquivo_gerados)
    ultimo = gerador.obter_ultimo_concurso()
    st.info(f"Último concurso analisado ({modalidade}): **{ultimo}**")

    st.subheader("Configurações do Jogo")
    
    tecnica = st.radio("Escolha a técnica:", ["Jogo Único", "Desdobramento"])
    
    if tecnica == "Desdobramento":
        tamanho_base = st.slider("Quantos números totais na base?", min_value=min_permitido + 1, max_value=max_permitido, value=min_permitido + 1)
        tamanho_bilhete = st.number_input("Tamanho de cada bilhete?", min_value=min_permitido, max_value=tamanho_base - 1, value=min_permitido)
    else:
        # 🌟 Agora o usuário pode escolher bilhetes maiores no Jogo Único!
        tamanho_bilhete = st.slider("Quantos números no seu bilhete único?", min_value=min_permitido, max_value=max_permitido, value=min_permitido)
        tamanho_base = tamanho_bilhete # A base e o bilhete têm o mesmo tamanho
    
    equilibrar = False
    modelo_escolhido = None
    usar_ml = False

    if modo_geracao == "Tradicional / Aleatório":
        equilibrar = st.checkbox("Forçar equilíbrio Pares/Ímpares?")
    else:
        usar_ml = True
        st.markdown("### 🧠 Configurações da IA")
        modelo_escolhido = st.selectbox("Escolha o Algoritmo Preditivo:", ["Random Forest", "KNN (Vizinhos Próximos)", "Rede Neural (MLP)"])
        
        # 💡 NOVA PARTE: Caixa expansível com as explicações dinâmicas
        with st.expander("💡 Entenda como esta Inteligência Artificial funciona"):
            if modelo_escolhido == "Random Forest":
                st.write("**🌳 Random Forest (Floresta Aleatória)**")
                st.write("Funciona como um 'conselho de especialistas'. O algoritmo cria dezenas de árvores de decisão que analisam o histórico de sorteios de formas diferentes. No final, elas fazem uma 'votação' para escolher as dezenas com maior força estatística. É excelente para lidar com grandes volumes de dados e encontrar padrões que o olho humano não vê.")
            elif modelo_escolhido == "KNN (Vizinhos Próximos)":
                st.write("**🔍 KNN (Vizinhos Próximos)**")
                st.write("É o detetive de semelhanças do sistema. Ele pega o resultado do último sorteio e varre todo o histórico buscando os concursos que foram mais parecidos com ele (seus 'vizinhos'). A partir daí, ele analisa quais números costumam ser sorteados logo na sequência desses padrões para montar a previsão.")
            else:
                st.write("**🧠 Rede Neural (MLP - Perceptron de Múltiplas Camadas)**")
                st.write("Inspirada no cérebro humano, essa IA usa camadas de 'neurônios' artificiais para aprender conexões complexas. Ela não olha apenas para a frequência, mas tenta entender o 'ritmo' e as mudanças de comportamento dos sorteios ao longo do tempo. É a tecnologia mais avançada do sistema para tentar rastrear tendências ocultas.")
            
            st.caption("⚠️ **Aviso de Transparência:** A loteria é um evento matematicamente aleatório. Nossas IAs analisam tendências e frequências reais do passado para otimizar suas escolhas baseadas em dados, mas nenhum sistema pode garantir 100% de acerto em sorteios futuros.")

    st.markdown("---")
    
    if tecnica == "Desdobramento":
        qtd_esperada = math.comb(tamanho_base, tamanho_bilhete)
    else:
        qtd_esperada = 1
        
    custo_total = qtd_esperada * 10
    
    col1, col2 = st.columns(2)
    
    # Capturamos o clique do botão de gerar
    gerou = col1.button(f"Gerar {qtd_esperada} Jogo(s) 🚀 (Custa {custo_total} Fichas)", use_container_width=True)
    
    # 🛡️ Proteção do Admin: O botão de apagar só aparece e só funciona se for o seu e-mail
    if st.session_state.get("user_email") == "alvarosantos2010@gmail.com":
        if col2.button("🗑️ [ADMIN] Apagar histórico", use_container_width=True):
            if gerador.resetar_gerados(): 
                st.success("Histórico apagado com sucesso!")
            else: 
                st.warning("Nenhum histórico para apagar.")
    
    # 🌟 Toda a ação de gerar a tabela agora acontece FORA das colunas, na tela inteira
    if gerou:
        if st.session_state["fichas"] >= custo_total:
            with st.spinner('Analisando e gerando números...'):
                jogos = gerador.gerar_jogos(tamanho_base, tamanho_bilhete, tecnica.lower().replace(" ", "_"), equilibrar, usar_ml, modelo_escolhido)
                
                if jogos:
                    fichas_gastas = len(jogos) * 10 
                    st.session_state["fichas"] -= fichas_gastas 
                    atualizar_saldo_nuvem(st.session_state["user_uid"], st.session_state["id_token"], st.session_state["fichas"])
                    
                    # --- LÓGICA LIMPA: APENAS AS BOLAS ---
                    resultado_formatado = []
                    for jogo in jogos:
                        jogo_dict = {f"Bola {i+1}": num for i, num in enumerate(sorted(jogo))}
                        resultado_formatado.append(jogo_dict)
                    
                    df_final = pd.DataFrame(resultado_formatado)
                    
                    st.success(f"Sucesso! {len(jogos)} jogo(s) gerado(s). Foram debitadas {fichas_gastas} fichas.")
                    
                    # Tabela ocupando 100% da largura
                    st.dataframe(df_final, use_container_width=True)
                else:
                    st.error("Não foi possível gerar novos jogos inéditos com essa base. A probabilidade de colisão com o histórico é muito alta.")
        else:
            st.error(f"❌ Saldo insuficiente! Você precisa de {custo_total} fichas, mas só tem {st.session_state['fichas']}.")
