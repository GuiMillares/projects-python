"""Termos de uso e política de privacidade.

Os textos moram na API, e não no front, porque é a API que precisa saber
qual versão está valendo para cobrar o aceite (ver exige_sessao em
app.py). Mudou algo que muda o sentido? Suba VERSAO: todo mundo aceita de
novo antes de continuar usando. Correção de digitação não precisa.

Não é parecer jurídico. É o que o app de fato faz com os dados, escrito
em português claro. Se o app passar a fazer outra coisa (outro serviço
recebendo dado, cobrança, backup com outro prazo), o texto muda junto.
"""

import config

VERSAO = "2026-10-28"
VERSAO_POR_EXTENSO = "28 de outubro de 2026"


def _secao(titulo, *paragrafos, itens=None):
    return {"titulo": titulo, "paragrafos": list(paragrafos), "itens": itens or []}


TERMOS = {
    "titulo": "Termos de uso",
    "secoes": [
        _secao(
            "1. O que é este app",
            "É um app de finanças pessoais feito e mantido por uma pessoa só, usado por "
            "convite entre família e amigos. Ele reúne num lugar seus lançamentos, contas, "
            "cartões, investimentos e metas.",
        ),
        _secao(
            "2. Quem pode usar",
            "Pessoas maiores de 18 anos que receberam um convite. Cada conta é de uma pessoa "
            "só: não empreste sua senha nem o seu app autenticador.",
        ),
        _secao(
            "3. Sua conta",
            "Você cuida da sua senha e do app autenticador usado na verificação em duas "
            "etapas. Se desconfiar que alguém entrou na sua conta, troque a senha em "
            "Configurações e avise quem mantém o app.",
        ),
        _secao(
            "4. Conexão com os bancos",
            "A leitura das contas e dos cartões passa pela Pluggy, instituição autorizada a "
            "operar no Open Finance. Você dá o consentimento no app do seu banco e pode "
            "revogá-lo lá ou no Meu Pluggy quando quiser. A conexão só lê dados: o app não "
            "movimenta dinheiro, não faz pagamento e não pede a senha do banco.",
        ),
        _secao(
            "5. Os números e as sugestões",
            "Totais, previsões, orçamentos sugeridos e passos de metas são informativos. A "
            "regra que tira da soma o dinheiro que só muda de conta pode errar, e a tela "
            "Conferir números existe para você conferir. Os passos sugeridos pela IA são "
            "sugestões. Nada aqui é recomendação de investimento nem consultoria financeira "
            "ou contábil.",
        ),
        _secao(
            "6. Disponibilidade",
            "É um projeto pessoal, sem garantia de funcionamento contínuo. O app pode ficar "
            "fora do ar, mudar ou ser encerrado. Se for encerrado, você recebe aviso com "
            "antecedência razoável para exportar seus dados.",
        ),
        _secao(
            "7. Preço",
            "O uso é gratuito. Se um dia houver cobrança, ela só começa depois de um aviso e "
            "de um novo aceite.",
        ),
        _secao(
            "8. Seus dados",
            "O que acontece com seus dados está na Política de privacidade. Em Configurações "
            "você exporta tudo o que o app guarda sobre você e apaga sua conta quando quiser.",
        ),
        _secao(
            "9. Mudanças nestes termos",
            "Se estes termos ou a política mudarem de sentido, o app pede um novo aceite "
            "antes de você continuar usando.",
        ),
        _secao(
            "10. Lei aplicável",
            "Valem as leis do Brasil, em especial a Lei Geral de Proteção de Dados Pessoais "
            "(Lei 13.709/2018).",
        ),
    ],
}


def _privacidade():
    quem = config.CONTROLADOR_NOME or "a pessoa que mantém esta instalação do app e te convidou"
    contato = (
        f"Para falar sobre seus dados, escreva para {config.CONTROLADOR_CONTATO}."
        if config.CONTROLADOR_CONTATO
        else "Para falar sobre seus dados, procure quem te convidou para o app."
    )
    return {
        "titulo": "Política de privacidade",
        "secoes": [
            _secao(
                "1. Quem cuida dos seus dados",
                f"O controlador dos dados, isto é, quem decide como eles são tratados, é "
                f"{quem}. {contato}",
            ),
            _secao(
                "2. O que o app guarda",
                itens=[
                    "Conta: e-mail, nome, foto (se você enviar), a senha guardada só como "
                    "resumo criptográfico (nunca a senha em si) e o segredo do autenticador "
                    "da verificação em duas etapas.",
                    "Dados financeiros que você lança ou importa: lançamentos (data, "
                    "descrição, valor e categoria), orçamentos, regras de categoria, "
                    "investimentos (código do ativo, quantidade e preço) e metas com seus "
                    "passos.",
                    "Open Finance: o identificador de cada conexão na Pluggy e as transações "
                    "importadas. Saldos e faturas são lidos na hora e não ficam guardados. "
                    "Os lançamentos que a importação deixou fora da soma ficam guardados "
                    "para a conferência dos números.",
                    "Registros de segurança: as sessões abertas (só o resumo do código de "
                    "acesso), as tentativas de login erradas e a versão destes documentos "
                    "que você aceitou, com data e hora.",
                ],
            ),
            _secao(
                "3. Para que",
                "Só para mostrar suas finanças a você e fazer o app funcionar: somar, prever, "
                "sugerir orçamentos e passos de metas. Não há publicidade, venda de dados nem "
                "perfil de consumo para terceiros.",
                "Quem mantém o servidor tem acesso técnico ao banco de dados e se compromete "
                "a não olhar seus dados, a não ser para resolver um problema que você pediu.",
            ),
            _secao(
                "4. Base legal",
                "O tratamento se apoia no seu consentimento (art. 7º, I, da LGPD), dado ao "
                "aceitar esta política. Você pode retirá-lo quando quiser apagando sua conta.",
            ),
            _secao(
                "5. Com quem os dados são compartilhados",
                itens=[
                    "Pluggy: lê os dados das suas contas e cartões no Open Finance, com o "
                    "consentimento que você dá no banco, e segue as regras do Banco Central.",
                    "Google (Gemini): só quando você pede sugestão de passos para uma meta. "
                    "Vão o título, a descrição, o valor alvo, o prazo e os passos que a meta "
                    "já tem. Não vão nome, e-mail, renda nem lançamentos. No plano gratuito "
                    "do Gemini, o Google pode usar o conteúdo enviado para melhorar os "
                    "produtos dele, e o processamento pode acontecer fora do Brasil (art. 33 "
                    "da LGPD). Não escreva na meta nada que você não mandaria ao Google.",
                    "brapi.dev: recebe só os códigos dos ativos da sua carteira (por exemplo, "
                    "PETR4) para buscar a cotação. Nenhum dado seu vai junto.",
                    "Servidor: os dados ficam no banco de dados do servidor onde o app roda, "
                    "contratado por quem mantém o app.",
                ],
            ),
            _secao(
                "6. Por quanto tempo",
                "Enquanto sua conta existir. Ao apagar a conta, tudo o que está na seção 2 sai "
                "do banco na hora. Se houver cópia de segurança do banco, os dados apagados "
                "somem dela quando a cópia for substituída, em até 30 dias.",
                "Apagar a conta no app não revoga o consentimento do Open Finance: faça isso "
                "no Meu Pluggy ou no app do seu banco.",
            ),
            _secao(
                "7. Segurança",
                "Nenhum sistema é infalível. Se acontecer um incidente de segurança que possa "
                "trazer risco ou dano relevante, você recebe aviso, e a ANPD também quando a "
                "lei exigir (art. 48 da LGPD).",
                itens=[
                    "Senha guardada só como resumo criptográfico e verificação em duas etapas "
                    "no login.",
                    "O código de cada sessão também é guardado só como resumo.",
                    "Cada pessoa só acessa os próprios dados, e a API confere isso em toda "
                    "requisição.",
                    "Chaves e senhas de serviços ficam fora do código do app.",
                ],
            ),
            _secao(
                "8. Seus direitos",
                "Para qualquer outro pedido sobre seus dados, use o contato da seção 1. A "
                "resposta vem em até 15 dias.",
                itens=[
                    "Acessar e levar seus dados: em Configurações, Exportar meus dados baixa "
                    "tudo num arquivo JSON.",
                    "Corrigir: o perfil se edita em Configurações, e lançamentos, "
                    "investimentos e metas errados podem ser excluídos e lançados de novo.",
                    "Apagar e retirar o consentimento: Apagar minha conta, em Configurações, "
                    "apaga tudo de uma vez.",
                    "Saber com quem os dados são compartilhados: está na seção 5.",
                ],
            ),
            _secao(
                "9. Mudanças nesta política",
                "Se esta política mudar de sentido, o app pede um novo aceite antes de você "
                "continuar usando.",
            ),
        ],
    }


def documentos():
    return {
        "versao": VERSAO,
        "versaoPorExtenso": VERSAO_POR_EXTENSO,
        "termos": TERMOS,
        "privacidade": _privacidade(),
    }
