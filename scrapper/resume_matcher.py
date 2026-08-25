"""Extrai o texto do currículo e calcula compatibilidade com a descrição da vaga.

v1 usa similaridade TF-IDF (rápido, sem depender de API externa nem chave).
Dá pra evoluir depois para usar um LLM e ter uma justificativa mais rica
("bate porque você tem 3 anos de Django e a vaga pede isso"), mas essa
versão já é suficiente para filtrar vagas obviamente incompatíveis.
"""

import io
import re
from typing import Union

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

PALAVRA_RE = re.compile(r"\b[a-zA-ZÀ-ÿ]{4,}\b")


def extrair_texto_curriculo(arquivo: Union[str, io.BytesIO], nome_arquivo: str = "") -> str:
    """Aceita um caminho de arquivo (str) ou um arquivo em memória (ex: upload do Streamlit)."""

    extensao = nome_arquivo.lower() if nome_arquivo else str(arquivo).lower()

    if extensao.endswith(".pdf"):
        import pypdf

        leitor = pypdf.PdfReader(arquivo)
        return "\n".join(pagina.extract_text() or "" for pagina in leitor.pages)

    if extensao.endswith(".docx"):
        import docx

        documento = docx.Document(arquivo)
        return "\n".join(paragrafo.text for paragrafo in documento.paragraphs)

    # fallback: texto puro
    if isinstance(arquivo, str):
        with open(arquivo, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    return arquivo.read().decode("utf-8", errors="ignore")


def calcular_compatibilidade(texto_curriculo: str, descricao_vaga: str) -> dict:
    """Retorna um score de 0 a 100 e as palavras-chave em comum/faltando."""

    if not texto_curriculo.strip() or not descricao_vaga.strip():
        return {"score": 0.0, "palavras_em_comum": [], "palavras_faltando": []}

    vetorizador = TfidfVectorizer(max_features=500)
    matriz = vetorizador.fit_transform([texto_curriculo, descricao_vaga])
    similaridade = cosine_similarity(matriz[0:1], matriz[1:2])[0][0]
    score = round(float(similaridade) * 100, 1)

    palavras_vaga = set(PALAVRA_RE.findall(descricao_vaga.lower()))
    palavras_curriculo = set(PALAVRA_RE.findall(texto_curriculo.lower()))

    em_comum = sorted(palavras_vaga & palavras_curriculo)[:15]
    faltando = sorted(palavras_vaga - palavras_curriculo)[:15]

    return {
        "score": score,
        "palavras_em_comum": em_comum,
        "palavras_faltando": faltando,
    }
