"""Painel principal: define critérios de busca, revisa vagas encontradas
e aprova ou não a candidatura de cada uma.

A busca real usa `buscar_vagas_reais` (LinkedIn, Indeed e Google, via
JobSpy). `buscar_vagas_mock` continua disponível como opção na tela,
útil para testar a interface sem gastar tentativas contra o LinkedIn e
o Indeed, que bloqueiam IPs que buscam demais em pouco tempo.

O preenchimento automático via Playwright (Gupy / site da empresa)
ainda não está ligado aqui — é a próxima etapa.
"""

import os

import streamlit as st

from models import CriteriosBusca, Vaga
from resume_matcher import calcular_compatibilidade, extrair_texto_curriculo
from scrapers import buscar_vagas_reais
from storage import HistoricoCandidaturas

st.set_page_config(page_title="Buscador de Vagas", layout="wide")
st.title("Buscador e candidato automático de vagas")


# O caminho vem do ambiente para que o nome do arquivo de credencial não
# fique fixo no código. Foi o nome fixo aqui que furou o .gitignore do
# scrapper e levou uma chave de service account para dentro de um commit.
# O arquivo em si nunca entra no repositório, só o caminho até ele.
CAMINHO_CREDENCIAIS = os.getenv(
    "SCRAPPER_CREDENCIAIS_GOOGLE", "credenciais_google.json"
)


@st.cache_resource
def carregar_historico() -> HistoricoCandidaturas:
    # O Streamlit reexecuta o arquivo inteiro a cada clique; @st.cache_resource
    # garante que a conexão com o Google Sheets seja feita uma única vez.
    return HistoricoCandidaturas(
        caminho_credenciais=CAMINHO_CREDENCIAIS,
        id_planilha="1SV1ou8jiZHJs6BfzPn_tiRueyfOcQgm1uBFRUvMwdUE",
    )


historico = None
try:
    historico = carregar_historico()
except Exception as erro_conexao:
    st.error(
        "Não consegui conectar no Google Sheets para carregar o histórico de candidaturas.\n\n"
        f"Detalhe técnico: {erro_conexao}\n\n"
        "Se o erro mencionar DNS/getaddrinfo, é problema de rede (sem internet, VPN ou "
        "proxy corporativo bloqueando googleapis.com), não do código. "
        "Verifique a conexão e recarregue a página."
    )
    st.stop()


def buscar_vagas_mock(criterios: CriteriosBusca) -> list[Vaga]:
    """Substituir por chamadas reais aos scrapers de LinkedIn/Indeed/Google."""
    return [
        Vaga(
            titulo=f"{criterios.cargo} Pleno",
            empresa="Empresa Exemplo",
            fonte="linkedin",
            url="https://exemplo.com/vaga1",
            descricao=(
                "Buscamos profissional com experiência em desenvolvimento backend, "
                "Python, APIs REST e bancos de dados relacionais."
            ),
            modelo_trabalho="Remoto",
            salario="R$ 6.000 - R$ 8.000",
            tipo_candidatura="candidatura_simplificada",
        ),
        Vaga(
            titulo=f"{criterios.cargo} Sênior",
            empresa="Outra Empresa",
            fonte="gupy",
            url="https://exemplo.com/vaga2",
            descricao=(
                "Vaga para atuar com automações, integração de sistemas e "
                "boas práticas de segurança da informação."
            ),
            modelo_trabalho="Híbrido",
            salario="A combinar",
            tipo_candidatura="gupy",
        ),
    ]


with st.sidebar:
    st.header("Critérios de busca")
    cargo = st.text_input("Cargo desejado", "Desenvolvedor Python")
    modelo_trabalho = st.selectbox("Modelo de trabalho", ["Qualquer", "Remoto", "Híbrido", "Presencial"])
    col_a, col_b = st.columns(2)
    with col_a:
        salario_min = st.number_input("Salário mín. (R$)", min_value=0, value=0, step=500)
    with col_b:
        salario_max = st.number_input("Salário máx. (R$)", min_value=0, value=0, step=500)
    localizacao = st.text_input("Localização (opcional)", "")

    st.divider()
    arquivo_curriculo = st.file_uploader("Seu currículo (PDF ou DOCX)", type=["pdf", "docx"])

    usar_dados_teste = st.checkbox(
        "Usar vagas de teste (não faz scraping real)",
        value=False,
        help="Útil pra testar a tela sem gastar tentativas contra o LinkedIn/Indeed.",
    )

    buscar = st.button("Buscar vagas", type="primary", use_container_width=True)

if "vagas" not in st.session_state:
    st.session_state.vagas = []
if "candidatadas" not in st.session_state:
    st.session_state.candidatadas = set()
if "ignoradas" not in st.session_state:
    st.session_state.ignoradas = set()

if buscar:
    criterios = CriteriosBusca(
        cargo=cargo,
        modelo_trabalho=modelo_trabalho,
        salario_minimo=salario_min or None,
        salario_maximo=salario_max or None,
        localizacao=localizacao or None,
    )

    texto_curriculo = ""
    if arquivo_curriculo is not None:
        texto_curriculo = extrair_texto_curriculo(arquivo_curriculo, arquivo_curriculo.name)

    if usar_dados_teste:
        vagas = buscar_vagas_mock(criterios)
    else:
        with st.spinner("Buscando vagas no LinkedIn, Indeed e Google..."):
            try:
                vagas = buscar_vagas_reais(criterios)
            except Exception as erro:
                import traceback

                st.error(f"Erro ao buscar vagas: {erro}")
                st.code(traceback.format_exc(), language="text")
                vagas = []

    vagas = [v for v in vagas if not historico.ja_candidatou(v.id)]

    if texto_curriculo:
        for vaga in vagas:
            resultado = calcular_compatibilidade(texto_curriculo, vaga.descricao)
            vaga.score_compatibilidade = resultado["score"]
            vaga.palavras_em_comum = resultado["palavras_em_comum"]
            vaga.palavras_faltando = resultado["palavras_faltando"]

    st.session_state.vagas = vagas

vagas_visiveis = [v for v in st.session_state.vagas if v.id not in st.session_state.ignoradas]

if not vagas_visiveis:
    st.info("Defina os critérios ao lado e clique em 'Buscar vagas'." if not st.session_state.vagas else "Todas as vagas encontradas foram ignoradas ou já candidatadas.")

for vaga in st.session_state.vagas:
    if vaga.id in st.session_state.ignoradas:
        continue

    with st.container(border=True):
        col_info, col_acao = st.columns([4, 1])

        with col_info:
            st.subheader(f"{vaga.titulo} — {vaga.empresa}")
            st.caption(f"Fonte: {vaga.fonte} · Tipo de candidatura: {vaga.tipo_candidatura} · {vaga.modelo_trabalho or 'Modelo não informado'} · {vaga.salario or 'Salário não informado'}")
            st.write(vaga.descricao)
            st.markdown(f"[Abrir vaga original]({vaga.url})")

            if vaga.score_compatibilidade is not None:
                st.progress(min(vaga.score_compatibilidade / 100, 1.0), text=f"Compatibilidade: {vaga.score_compatibilidade}%")
                if vaga.palavras_em_comum:
                    st.caption("Pontos em comum: " + ", ".join(vaga.palavras_em_comum[:8]))
                if vaga.palavras_faltando:
                    st.caption("Não aparecem no currículo: " + ", ".join(vaga.palavras_faltando[:8]))

        with col_acao:
            ja_candidatou = vaga.id in st.session_state.candidatadas
            if ja_candidatou:
                st.success("Candidatura enviada")
            else:
                if vaga.tipo_candidatura in ("gupy", "site_empresa"):
                    rotulo = "Candidatar automaticamente"
                else:
                    rotulo = "Marcar como candidatado"

                if st.button(rotulo, key=f"apply_{vaga.id}", use_container_width=True):
                    # Aqui entra a chamada real ao preenchimento automático
                    # (Gupy / site da empresa) quando esse módulo existir.
                    # No caso de LinkedIn/Indeed, o registro abaixo serve
                    # para marcar que você mesmo se candidatou manualmente.
                    historico.registrar_candidatura(vaga)
                    st.session_state.candidatadas.add(vaga.id)
                    st.rerun()

                if st.button("Ignorar", key=f"skip_{vaga.id}", use_container_width=True):
                    st.session_state.ignoradas.add(vaga.id)
                    st.rerun()