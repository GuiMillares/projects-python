# Plano de resposta a incidente

O que fazer, em ordem, se dado de alguém pode ter vazado, sido alterado ou se
perdido. Cabe numa página para ser lido com pressa.

**Conta como incidente** qualquer suspeita de que alguém sem permissão viu,
copiou, alterou ou apagou dado pessoal. Por exemplo:

- acesso estranho à VPS ou ao MySQL;
- o `.env` exposto num commit, num print ou num servidor invadido. Ele tem as
  chaves da Pluggy e do Gemini;
- um backup ou a frase da cifra exposto;
- uma pessoa vendo dado de outra, por bug de isolamento;
- a conta de alguém acessada por terceiro;
- banco apagado ou corrompido.

## 1. Conter (na primeira hora)

- Anote a hora em que você soube. Os prazos da ANPD contam a partir dela.
- Se o vazamento pode estar acontecendo agora, **tire o app do ar**: pare a
  API e o servidor web.
- **Derrube todas as sessões:** `mysql local_finance -e "DELETE FROM sessoes"`.
- **Troque o que pode ter vazado:**
  - o Client Secret da Pluggy (no dashboard);
  - a chave do Gemini (no AI Studio);
  - o token da brapi;
  - a senha do MySQL;
  - as chaves SSH da VPS;
  - a frase do backup. Depois de trocá-la, faça um backup novo.
- **Guarde as evidências antes de mexer:** copie para fora do servidor o
  `/var/log/auth.log`, os logs do servidor web e o `journalctl` da API. Não
  apague nada ainda.

## 2. Avaliar (até 24 horas)

Responda no registro (seção 5):

- O que aconteceu, quando começou e quando foi percebido?
- Que dados foram afetados: conta (e-mail, nome), lançamentos e
  investimentos, identificadores das conexões da Pluggy, segredos?
- De quem? O app é pequeno: liste as pessoas pelo nome.
- Há risco ou dano relevante? Dado financeiro e de conta abre espaço para
  golpe, fraude e constrangimento. **Na dúvida, trate como relevante.**

## 3. Comunicar (em até 3 dias úteis, se houver risco ou dano relevante)

O prazo conta de quando você soube que havia dado pessoal afetado (LGPD, art.
48, e Resolução CD/ANPD nº 15/2024).

- **Titulares afetados:** mande uma mensagem direta a cada um, usando o
  modelo abaixo.
- **ANPD:** use o formulário de comunicação de incidente no site da ANPD
  (gov.br/anpd) e conte o que já se sabe. Complementos podem ir em até 20 dias
  úteis.
- **Pluggy:** se as credenciais da Pluggy vazaram, avise a Pluggy. Se os dados
  das conexões foram expostos, oriente as pessoas a revogar o consentimento no
  Meu Pluggy ou no app do banco.

> **Assunto:** Incidente de segurança no app de finanças
>
> Oi, [nome]. Em [data], descobri que [o que aconteceu, em uma frase].
> Podem ter sido expostos: [quais dados]. Já fiz o seguinte: [trocar chaves,
> encerrar sessões, tirar o app do ar]. Recomendo que você [troque a senha do
> app / revogue o Open Finance no Meu Pluggy / desconfie de quem pedir seus
> dados em nome do app]. Se tiver dúvida, fale comigo em [contato]. Aviso de
> novo quando souber mais.

## 4. Corrigir e voltar

1. Corrija a causa antes de subir o app de novo: atualize o pacote, feche a
   porta ou corrija o bug.
2. Se houve perda ou adulteração de dados, restaure um backup anterior ao
   incidente, seguindo `ops/BACKUP.md`.
3. Rode os testes, suba o app e confira com um usuário de teste.
4. Avise as pessoas que o app voltou e o que mudou.

## 5. Registrar (sempre, mesmo sem comunicar)

Todo incidente vira um registro guardado por pelo menos 5 anos, **fora deste
repositório**, que é público. Uma pasta privada no Drive serve. O registro
precisa ter:

- data e hora em que você soube;
- o que aconteceu;
- dados e pessoas afetados;
- avaliação de risco e por que comunicou ou não;
- medidas tomadas;
- comunicações feitas: a quem e quando.

## Contatos

| Quem | Como |
| --- | --- |
| Controlador | `FIN_CONTROLADOR_NOME` e `FIN_CONTROLADOR_CONTATO`, no `.env` |
| ANPD | formulário de comunicação de incidente em gov.br/anpd |
| Pluggy | dashboard.pluggy.ai e o formulário de contato em pluggy.ai |
| Provedor da VPS | painel do provedor |
