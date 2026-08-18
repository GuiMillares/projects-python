# Painel financeiro pessoal

Front-end React (futuro app Tauri) + API Python sobre o MySQL do Laragon.

```
projeto finanças/
  db/schema.sql      esquema do banco local_finance
  db/migrar.sql      alterações em banco que já existe
  api/               API Flask: auth, 2FA e dados
  ui/                telas React
  financas.py        CLI antiga (SQLite), origem dos dados a importar
```

## Subir

**1. MySQL do Laragon**, pelo painel do Laragon ou:

```bash
C:/laragon/bin/mysql/mysql-8.4.3-winx64/bin/mysqld.exe \
  --defaults-file=C:/laragon/bin/mysql/mysql-8.4.3-winx64/my.ini
```

**2. Banco** (já criado; os dois scripts são idempotentes).

Rode **a partir da raiz `projeto finanças/`**, não de dentro de `ui/` ou
`api/`, senão o caminho não existe:

```bash
cd "projeto finanças"
mysql -u root --skip-password < db/schema.sql
mysql -u root --skip-password < db/migrar.sql
```

`migrar.sql` é o que atualiza um banco que já existe: o `schema.sql` usa
`CREATE TABLE IF NOT EXISTS` e não mexe em tabela já criada. Sem ele, falta
a coluna `usuarios.foto` e a tela de perfil quebra.

**3. API**

Ative o venv **antes**. As dependências estão em `python/.venv`, e o `python`
do PATH pode não ser ele: existe um `python/venv` antigo e vazio ao lado, e
cair nele dá `ModuleNotFoundError: No module named 'flask'`.

```bash
cd api
source ../../.venv/Scripts/activate     # Git Bash
# ..\..\.venv\Scripts\activate.bat      # cmd
# ..\..\.venv\Scripts\Activate.ps1      # PowerShell

pip install -r requirements.txt         # só na primeira vez
python criar_usuario.py                 # cria seu login, só na primeira vez
python app.py                           # http://127.0.0.1:8756
```

Sem ativar nada também funciona: `../../.venv/Scripts/python.exe app.py`.

Só suba **uma** instância. O Windows deixa dois processos escutarem a mesma
porta, e aí as respostas passam a vir ora de um, ora do outro; se a API
parecer estar rodando código velho, é isso.

**4. Telas**

```bash
cd ui
npm install
npm run dev                  # http://localhost:1420
```

No primeiro acesso a tela pede o cadastro do 2FA e mostra o QR code. Leia com
Google Authenticator, Authy ou 1Password: sem isso não se entra.

**5. Importar o histórico do SQLite** (opcional)

```bash
cd api
python importar_sqlite.py "../financas.db" seu@email.com
```

## Como a segurança funciona

O desenho é o mesmo do painel administrativo do Synchro, com o Firebase
trocado por processo local:

| Synchro | aqui |
| --- | --- |
| Firebase Auth | senha com `hashlib.scrypt` em `api/seguranca.py` |
| Cloud Functions do 2FA | rotas `/api/auth/2fa/*` |
| Documento do Firestore | tabela `usuarios` |

**A regra que não muda: o segredo TOTP nunca existe no frontend.** Ele é
gerado no servidor, mora só em `usuarios.totp_secret` e nenhuma rota o
devolve. O cliente vê uma única vez o `otpauth://` do cadastro (para virar
QR code) e, daí em diante, só manda 6 dígitos e recebe sim ou não.

Se algum dia aparecer `otplib` ou `speakeasy` no `ui/package.json`, é sinal
de que essa regra foi quebrada.

Outros pontos, todos com teste ponta a ponta passando:

- Login devolve uma sessão **parcial**. Ela abre apenas as rotas de 2FA:
  nenhum dado financeiro sai antes do código ser validado.
- Código de 6 dígitos vale **uma vez só** (a janela usada é queimada em
  `totp_ultimo_step`), e não os 30 segundos inteiros.
- Desativar o 2FA exige um código válido, senão bastariam dois cliques
  numa sessão deixada aberta.
- Trocar a senha derruba as outras sessões.
- E-mail inexistente e senha errada dão a **mesma** resposta, para a tela
  não virar um oráculo de quais e-mails têm conta.
- 5 tentativas erradas trancam a conta por 15 minutos.
- No banco fica o **hash** do token de sessão, não o token.
- A foto de perfil é validada pelo prefixo do data URL: sem isso daria para
  gravar `data:text/html,<script>` e o `<img src>` viraria injeção.
- A API escuta só em `127.0.0.1` e aceita um conjunto fechado de origens.

## Design

Paleta **Oliva & Terracota**: base neutra quente (marrom-tinta no escuro,
pergaminho no claro) com acento **oliva**, um verde puxado para o amarelo,
cor de azeitona e latão envelhecido. Nada de ciano, azul ou teal (território
do Synchro) e nada de roxo/indigo de template.

Entradas em oliva, saídas em terracota, alertas em ocre; vermelho-tijolo
fica reservado ao que exige ação agora. Os quatro ficam em matizes bem
separados para o olho distinguir na fileira de KPIs sem ler o rótulo.

Toda cor vive em `ui/src/styles/tokens.css`. Nenhum componente tem cor
fixa: é isso que faz o tema claro/escuro funcionar sem duplicar nada. Trocar
`data-theme` no `<html>` repinta a aplicação inteira. O tema se troca pelo
botão da topbar, que está sempre à mão, e a escolha fica salva no aparelho;
sem preferência salva, o app segue o tema do sistema.

A cor de cada categoria vem da **posição** dela na lista ordenada de
categorias (`ui/src/services/cores.js`), não de um hash do nome. Hash
colidia: com 5 categorias e 6 cores, três caíam na mesma terracota e a rosca
ficava com fatias idênticas.

Gráficos (linha, barra, rosca) são componentes SVG próprios em
`ui/src/components/Charts.jsx`, sem biblioteca de gráfico. Eles medem o
container e desenham no tamanho real, então texto e círculos não distorcem
em tela larga.

Ícones: `lucide-react`. Nenhum emoji na interface.

**Responsivo:** no desktop a navegação é a sidebar; abaixo de 900px ela vira
bottom navigation (Geral, Entradas, Saídas, Investir, Metas), com
`safe-area-inset` para o iPhone. Configurações fica no menu do avatar nos
dois tamanhos. Verificado sem rolagem lateral até 320px de largura.

## Estado das telas

| Tela | Situação |
| --- | --- |
| Login + 2FA (cadastro e verificação) | pronta |
| Visão geral (KPIs, gráficos, pontos de atenção) | pronta |
| Entradas (lista, cadastro, exclusão) | pronta |
| Saídas (lista, cadastro, exclusão) | pronta |
| Investimentos (carteira com cotação da B3) | pronta |
| Metas gamificadas (XP, nível, subtarefas por IA) | pronta |
| Configurações (perfil, foto, senha, 2FA, orçamentos) | pronta |

Não há mais tela placeholder: `EmBreve.jsx` foi removido.

Entradas e Saídas são **o mesmo componente** (`ui/src/pages/Lancamentos.jsx`)
com `natureza` trocada. Mesma rota da API, mesmos campos, mesmos totais: manter
duas cópias só faria uma receber ajuste e a outra ficar para trás.

## Cotação da B3 (brapi.dev)

A tela de Investimentos guarda ticker, quantidade e preço médio; o valor
atual **não** é gravado, porque ele é quantidade x cotação do momento. Um
número salvo no banco só ficaria desatualizado contradizendo a tela.

O cliente está em `api/cotacoes.py`, só com biblioteca padrão.

**Token (opcional, mas recomendado).** A brapi aceita **um** ticker por
request sem token e recusa a lista com `401 MISSING_TOKEN`. O código cobre
os dois casos:

| | comportamento |
| --- | --- |
| sem token | um request por ticker, no máximo `FIN_BRAPI_MAX_SEM_TOKEN` (6) |
| com token | um request só, com a carteira inteira |

Para configurar, gere o token gratuito em brapi.dev e exporte antes de subir
a API (não precisa mexer em código):

```bash
export FIN_BRAPI_TOKEN=seu_token_aqui   # Git Bash
# $env:FIN_BRAPI_TOKEN = "seu_token"    # PowerShell
python app.py
```

Cotações ficam em cache por 60s (`FIN_BRAPI_CACHE`), senão cada F5 vira uma
rodada de requests e o limite gratuito acaba rápido.

**Se a brapi cair, a tela não quebra.** `cotacoes.buscar` nunca levanta
exceção: devolve o que conseguiu mais um aviso em texto. As posições
aparecem completas (ticker, quantidade, preço médio, investido), só sem os
números de mercado, e o aviso diz o motivo. Verificado com a API apontada
para um host inexistente: HTTP 200, itens completos, `cotacao: null`.

## Próximo passo: Tauri

O front não usa nada de navegador que o webview não tenha. Para empacotar,
`tauri.conf.json` aponta `build.devUrl` para `http://localhost:1420` e a API
sobe como sidecar. `ui/src/services/api.js` é o único arquivo que sabe o
endereço do servidor: se um dia a comunicação virar `invoke()` do Tauri em
vez de HTTP, é só ali que se mexe.


## Metas gamificadas

Cada meta se divide em subtarefas. Subtarefa concluída dá XP; concluir a
meta inteira dá um bônus **maior que a soma das subtarefas dela** (fator
1.5, mínimo 50), então nunca compensa parar com tudo feito menos o fim.

O XP e o nível **não são gravados**: derivam do que está marcado como
concluído (`api/gamificacao.py`). Guardar o total abriria espaço para ele
divergir das subtarefas que o justificam, e o cálculo é barato o bastante
para rodar a cada carga. Desmarcar uma subtarefa devolve o XP dela.

A curva de nível é quadrática: nível 2 aos 100 XP, 3 aos 300, 4 aos 600.
O avatar do personagem troca de patente conforme o nível (Semente, Brasa,
Estrela, Gema, Coroa), só um ícone e uma cor.

### Subtarefas geradas por IA

A quebra automática da meta em passos acontece em **`api/ia.py`**, o único
arquivo do projeto que fala com um modelo de linguagem. Ele usa o SDK
oficial do Google (`google-genai`) com saída estruturada por schema, o que
dispensa regex e retry de parse.

**Configuração:** uma variável de ambiente com a chave.

```bash
export GEMINI_API_KEY=AIza...                    # Git Bash
$env:GEMINI_API_KEY = "AIza..."                  # PowerShell (sessão atual)
[Environment]::SetEnvironmentVariable("GEMINI_API_KEY", "AIza...", "User")
```

Gere em aistudio.google.com/apikey. O tier gratuito não pede cartão de
crédito. O SDK também aceita `GOOGLE_API_KEY`, que tem precedência se as
duas existirem; prefira `GEMINI_API_KEY`, porque o nome genérico pode
colidir com outra ferramenta Google na mesma máquina.

**Nenhuma credencial aparece no código**: o cliente é construído sem
argumentos e o SDK resolve a chave do ambiente. `config.py` guarda só
ajustes (modelo, timeout, teto de subtarefas), nunca segredo. Vale a mesma
pegadinha do Windows da seção de armadilhas: variável com escopo "User" só
é vista por processo aberto depois de configurada.

O modelo é trocável sem mexer em código, do mais barato ao mais capaz:

```bash
FIN_IA_MODELO=gemini-3.5-flash-lite   # mais rápido e econômico
FIN_IA_MODELO=gemini-3.5-flash        # padrão
FIN_IA_MODELO=gemini-3.7-flash        # melhor julgamento
```

A geração recebe os passos que a meta já tem: o modelo complementa o
caminho em vez de recomeçar, e um filtro no servidor barra qualquer
repetição literal (case, acento e pontuação não contam como diferença).
O nível de raciocínio é configurável por FIN_IA_THINKING (padrão MEDIUM).

### Escada de níveis

300 aparências únicas, seguindo o desenho dos sistemas de rank maduros:
15 patamares com nome de material (Semente até Lenda, modelo Duolingo e
Overwatch), 4 divisões em algarismo romano dentro de cada patamar (IV até
I, modelo League of Legends) e 5 pips estilo insígnia militar dentro de
cada divisão. Nível 1 e 2 diferem nos pips; 5 e 6 trocam de divisão; 20 e
21 trocam de patamar inteiro. A lógica vive em ui/src/services/niveis.js
e o servidor trava o nível em 300.

### Exclusões e histórico

Todo botão de excluir (meta, passo, lançamento, posição da carteira) abre
um modal de confirmação que diz o que vai junto: passos, XP, valores. O
foco inicial fica no Cancelar, então Enter por reflexo não apaga nada.

Metas concluídas saem da lista principal e vão para a aba "Concluídas",
com contador; reabrir traz de volta.

**Sem a chave, nada quebra.** Mesmo contrato de `cotacoes.py`: a função
nunca levanta exceção. A meta é criada do mesmo jeito, a caixa "sugerir os
passos" aparece desabilitada explicando o que falta, e você escreve os
passos à mão.
