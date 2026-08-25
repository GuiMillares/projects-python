"""Histórico de candidaturas guardado em uma planilha Google Sheets.

Por que Google Sheets: é armazenamento em nuvem (não um banco de dados
local), gratuito, e dá pra abrir e conferir manualmente pelo celular
ou navegador a qualquer momento.

Setup necessário (uma vez só):
1. Criar um projeto no Google Cloud Console e ativar a API do Google Sheets
   e do Google Drive.
2. Criar uma "Service Account", gerar uma chave JSON e salvar o arquivo
   (ex: credenciais_google.json) em local seguro, fora do controle de versão.
3. Criar uma planilha no Google Sheets e compartilhá-la com o e-mail da
   service account (algo como nome@projeto.iam.gserviceaccount.com),
   dando permissão de Editor.
4. Copiar o ID da planilha (a parte da URL entre /d/ e /edit).
"""

from datetime import datetime
from typing import Optional

import gspread
from google.oauth2.service_account import Credentials

from models import Vaga

ESCOPOS = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

CABECALHO = [
    "id_vaga",
    "titulo",
    "empresa",
    "fonte",
    "url",
    "tipo_candidatura",
    "score_compatibilidade",
    "data_candidatura",
]


class HistoricoCandidaturas:
    """Controla quais vagas já foram aplicadas, usando uma planilha como fonte da verdade."""

    def __init__(self, caminho_credenciais: str, id_planilha: str, aba: str = "candidaturas"):
        credenciais = Credentials.from_service_account_file(caminho_credenciais, scopes=ESCOPOS)
        cliente = gspread.authorize(credenciais)
        self.planilha = cliente.open_by_key(id_planilha)
        try:
            self.aba = self.planilha.worksheet(aba)
        except gspread.WorksheetNotFound:
            self.aba = self.planilha.add_worksheet(title=aba, rows=2000, cols=len(CABECALHO))
            self.aba.append_row(CABECALHO)

        self._cache_ids: Optional[set] = None

    def _carregar_ids(self) -> set:
        if self._cache_ids is None:
            valores = self.aba.col_values(1)  # coluna id_vaga, pulando o cabeçalho
            self._cache_ids = set(valores[1:])
        return self._cache_ids

    def ja_candidatou(self, id_vaga: str) -> bool:
        return id_vaga in self._carregar_ids()

    def registrar_candidatura(self, vaga: Vaga):
        if self.ja_candidatou(vaga.id):
            return  # evita duplicar linha se, por algum motivo, for chamado duas vezes

        self.aba.append_row([
            vaga.id,
            vaga.titulo,
            vaga.empresa,
            vaga.fonte,
            vaga.url,
            vaga.tipo_candidatura,
            vaga.score_compatibilidade or "",
            datetime.now().strftime("%Y-%m-%d %H:%M"),
        ])
        self._carregar_ids().add(vaga.id)
