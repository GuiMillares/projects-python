"""Busca real de vagas no LinkedIn, Indeed e Google, usando a biblioteca
JobSpy (https://github.com/speedyapply/JobSpy).

Ela faz o scraping desses sites e devolve os resultados como um DataFrame
do pandas; aqui a gente só converte isso para os nossos objetos `Vaga` e
aplica um filtro extra de salário mínimo.

Limitações importantes (segundo a documentação da própria biblioteca):
- LinkedIn e Indeed bloqueiam IPs que fazem muitas buscas seguidas
  (erro HTTP 429 = "muitas requisições"). Se isso acontecer, espere
  alguns minutos entre buscas, reduza `resultados_por_site`, ou
  configure um proxy no parâmetro `proxies` do `scrape_jobs`.
- A busca no Google Jobs (`google_search_term`) precisa de uma sintaxe
  específica: pesquise "vagas [cargo]" no Google normalmente, aplique os
  filtros que quiser na caixa de vagas que aparece, e use esse texto.
  Aqui estou usando o próprio cargo como aproximação inicial.
- Nem toda vaga tem o link direto do site da empresa. Quando não tem
  (`job_url_direct` vazio), a gente usa o link do próprio agregador
  (`job_url`), que no caso do LinkedIn/Indeed é o link para a página da
  vaga lá, não necessariamente para um formulário preenchível.
"""

from inspect import signature
import re
from typing import Optional
from urllib.parse import urlparse

import pandas as pd
from jobspy import scrape_jobs

from models import CriteriosBusca, Vaga

# Parâmetros que a versão de jobspy instalada realmente aceita. A lib
# muda a assinatura de scrape_jobs entre versões (ex: google_search_term
# nem sempre existe), então montamos os kwargs dinamicamente em vez de
# arriscar um TypeError por parâmetro desconhecido.
_PARAMETROS_ACEITOS = set(signature(scrape_jobs).parameters)

MODELO_PARA_IS_REMOTE = {
    "Remoto": True,
    "Híbrido": None,  # jobspy não distingue híbrido, então não filtramos por isso
    "Presencial": False,
    "Qualquer": None,
}

# Palavras de cargo/senioridade que não ajudam a distinguir uma vaga de
# outra (ex: "Analista" aparece tanto em "Analista de Segurança" quanto
# em "Analista de QA"). Usadas para não deixar o filtro de relevância
# passar vagas só porque compartilham um termo genérico com a busca.
_PALAVRAS_GENERICAS = {
    "analista", "assistente", "auxiliar", "especialista", "consultor",
    "coordenador", "supervisor", "gerente", "diretor", "estagiario",
    "trainee", "tecnico", "profissional", "vaga", "vagas", "pleno",
    "junior", "senior", "para", "com",
}
_PALAVRA_RE = re.compile(r"[^\W\d_]{4,}", re.UNICODE)


def _remover_acentos(texto: str) -> str:
    import unicodedata

    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))


def _palavras_relevantes(texto: str) -> set:
    sem_acento = _remover_acentos(texto.lower())
    return {p for p in _PALAVRA_RE.findall(sem_acento) if p not in _PALAVRAS_GENERICAS}


def _vaga_relevante(vaga: Vaga, criterios: CriteriosBusca) -> bool:
    """Filtra vagas que só bateram com a busca por termos genéricos demais.

    LinkedIn/Indeed fazem correspondência frouxa (o Indeed, por exemplo,
    busca no texto da descrição inteira), então "Analista de Segurança da
    Informação" pode devolver vagas de QA, atendimento etc. Aqui exigimos
    que pelo menos uma palavra realmente específica do cargo buscado
    apareça no título ou na descrição da vaga.
    """
    termos_busca = _palavras_relevantes(criterios.cargo)
    if not termos_busca:
        return True  # busca só com termos genéricos: não dá pra filtrar, deixa passar

    conteudo = _palavras_relevantes(f"{vaga.titulo} {vaga.descricao}")
    return bool(termos_busca & conteudo)


def _bate_modelo_trabalho(vaga: Vaga, criterios: CriteriosBusca) -> bool:
    if criterios.modelo_trabalho in (None, "Qualquer", "Híbrido"):
        return True  # jobspy não reporta híbrido separadamente, não dá pra filtrar com certeza
    if criterios.modelo_trabalho == "Remoto":
        return vaga.modelo_trabalho == "Remoto"
    return True  # "Presencial": sem uma flag confiável de "não remoto", não filtramos


def _determinar_tipo_candidatura(site: Optional[str], url: str) -> str:
    """Decide se a vaga é candidatável via Gupy, site da empresa, ou só manual.

    É uma heurística por domínio, não uma certeza. Vale conferir manualmente
    antes de confiar cegamente no preenchimento automático.
    """
    dominio = urlparse(url or "").netloc.lower()

    if "gupy.io" in dominio:
        return "gupy"

    if site == "google" and dominio and "linkedin" not in dominio and "indeed" not in dominio:
        # O Google Jobs costuma apontar para o link direto da vaga, que às
        # vezes já é a página de candidatura no site da própria empresa.
        return "site_empresa"

    return "manual"


def _texto(valor) -> Optional[str]:
    """Converte um valor vindo do pandas em string limpa, tratando NaN.

    NaN é um float 'verdadeiro' para o Python, então `campo or fallback`
    não funciona como esperado — este helper resolve isso devolvendo None
    para NaN/None/vazio.
    """
    if valor is None:
        return None
    if isinstance(valor, float) and pd.isna(valor):
        return None
    texto = str(valor).strip()
    return texto or None


def _linha_para_vaga(linha: dict, criterios: CriteriosBusca) -> Optional[Vaga]:
    url = _texto(linha.get("job_url_direct")) or _texto(linha.get("job_url"))
    if not url:
        return None

    salario_min = linha.get("min_amount")
    salario_max = linha.get("max_amount")

    if criterios.salario_minimo and pd.notna(salario_max) and salario_max < criterios.salario_minimo:
        return None  # descarta vagas que pagam menos que o piso definido

    salario_texto = None
    if pd.notna(salario_min) or pd.notna(salario_max):
        moeda = _texto(linha.get("currency")) or "R$"
        partes = [str(int(v)) for v in (salario_min, salario_max) if pd.notna(v)]
        if partes:
            salario_texto = f"{moeda} " + " - ".join(partes)

    bruto_remoto = linha.get("is_remote")
    eh_remoto = bool(bruto_remoto) if pd.notna(bruto_remoto) else False
    # Importante: só rotulamos como "Remoto" quando o site realmente
    # confirmou isso. Nunca usamos o critério de busca como fallback aqui,
    # senão toda vaga sem essa informação apareceria marcada como remota
    # mesmo sem ser (foi exatamente o bug que causava vaga presencial
    # aparecendo etiquetada como remota).
    modelo = "Remoto" if eh_remoto else None

    return Vaga(
        titulo=_texto(linha.get("title")) or "(sem título)",
        empresa=_texto(linha.get("company")) or "(empresa não informada)",
        fonte=_texto(linha.get("site")) or "desconhecida",
        url=url,
        descricao=(_texto(linha.get("description")) or "")[:3000],
        modelo_trabalho=modelo,
        salario=salario_texto,
        tipo_candidatura=_determinar_tipo_candidatura(_texto(linha.get("site")), url),
    )


def converter_dataframe(df: pd.DataFrame, criterios: CriteriosBusca) -> list[Vaga]:
    """Separado de `buscar_vagas_reais` para permitir testar sem rede."""
    vagas = []
    for _, linha in df.iterrows():
        vaga = _linha_para_vaga(linha.to_dict(), criterios)
        if vaga is None:
            continue
        if not _vaga_relevante(vaga, criterios):
            continue
        if not _bate_modelo_trabalho(vaga, criterios):
            continue
        vagas.append(vaga)
    return vagas


def buscar_vagas_reais(
    criterios: CriteriosBusca,
    sites: Optional[list[str]] = None,
    resultados_por_site: int = 15,
) -> list[Vaga]:
    sites = sites or ["linkedin", "indeed", "google"]

    kwargs = {
        "site_name": sites,
        "search_term": criterios.cargo,
        "location": criterios.localizacao or "Brasil",
        "is_remote": MODELO_PARA_IS_REMOTE.get(criterios.modelo_trabalho),
        "results_wanted": resultados_por_site,
        "country_indeed": "brazil",
        "linkedin_fetch_description": True,
        "description_format": "markdown",
        "google_search_term": criterios.cargo,
    }
    # Remove qualquer parâmetro que a versão instalada de jobspy não conheça,
    # em vez de deixar o scrape_jobs() estourar TypeError.
    kwargs = {chave: valor for chave, valor in kwargs.items() if chave in _PARAMETROS_ACEITOS}

    df = scrape_jobs(**kwargs)

    if df is None or df.empty:
        return []

    return converter_dataframe(df, criterios)