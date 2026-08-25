# Buscador e candidato automático de vagas

## O que já está pronto (v1)

- `models.py` — estrutura de dados (`Vaga`, `CriteriosBusca`). Cada vaga
  recebe um `id` estável (hash de fonte + URL), que é a chave usada para
  não te candidatar duas vezes na mesma vaga.
- `resume_matcher.py` — lê o currículo (PDF ou DOCX) e calcula um score
  de 0 a 100 de compatibilidade com a descrição da vaga, além de mostrar
  quais palavras-chave da vaga aparecem (ou não) no currículo.
- `storage.py` — histórico de candidaturas guardado numa planilha do
  Google Sheets (não usa banco de dados local).
- `app.py` — painel em Streamlit com o formulário de critérios de busca
  e a lista de vagas com botão de candidatar/ignorar. Por enquanto exibe
  vagas fictícias (`buscar_vagas_mock`) no lugar dos scrapers reais.

## O que falta (próxima etapa)

- Scrapers reais de LinkedIn, Indeed e Google Jobs.
- Preenchimento automático via Playwright em vagas da Gupy e de sites
  de empresa (dados pessoais, pretensão salarial, upload de currículo).
- Ligar `storage.py` no `app.py` (hoje está comentado no código).
- Opcionalmente: busca do perfil do recrutador/empresa + geração de
  e-mail de apresentação.

## Como rodar a v1 (só a tela, com vagas fictícias)

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Setup do Google Sheets (necessário antes de ligar o storage.py)

1. No [Google Cloud Console](https://console.cloud.google.com/), crie um
   projeto e ative a **Google Sheets API** e a **Google Drive API**.
2. Crie uma **Service Account**, gere uma chave em formato JSON e salve
   o arquivo em um local seguro (ex: `credenciais_google.json`). **Não**
   suba esse arquivo para nenhum repositório.
3. Crie uma planilha nova no Google Sheets e compartilhe-a com o e-mail
   da service account (algo como `nome@projeto.iam.gserviceaccount.com`),
   dando permissão de **Editor**.
4. Copie o ID da planilha (o trecho da URL entre `/d/` e `/edit`).
5. No código, instancie assim:

```python
from storage import HistoricoCandidaturas

historico = HistoricoCandidaturas(
    caminho_credenciais="credenciais_google.json",
    id_planilha="ID_DA_SUA_PLANILHA",
)

if not historico.ja_candidatou(vaga.id):
    # preencher/enviar a candidatura
    historico.registrar_candidatura(vaga)
```
