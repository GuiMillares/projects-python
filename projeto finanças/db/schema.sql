-- ============================================================
-- local_finance: esquema do painel financeiro pessoal
-- MySQL 8.4 (Laragon)
--
-- Rodar:
--   mysql -u root --skip-password < db/schema.sql
-- É idempotente: pode rodar de novo sem perder dado.
-- ============================================================

CREATE DATABASE IF NOT EXISTS local_finance
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE local_finance;

-- ── Usuários ────────────────────────────────────────────────
-- App de dono único, mas a tabela existe mesmo assim: é o que
-- ancora as chaves estrangeiras e evita ter "o usuário" implícito
-- espalhado no código.
--
-- `totp_secret` mora AQUI e só aqui. Nenhuma rota da API devolve
-- esse campo. O frontend recebe no máximo o otpauth:// uma vez,
-- no momento do cadastro, e nunca mais.
CREATE TABLE IF NOT EXISTS usuarios (
  id              INT UNSIGNED    NOT NULL AUTO_INCREMENT,
  email           VARCHAR(190)    NOT NULL,
  senha_hash      VARCHAR(255)    NOT NULL,
  nome            VARCHAR(120)    NOT NULL DEFAULT '',
  -- Foto de perfil como data URL. O navegador já recorta em quadrado e
  -- reduz para 256px antes de enviar, então cabe em poucos KB: não vale
  -- a pena um diretório de uploads e uma rota de arquivo estático para
  -- guardar uma imagem por conta.
  foto            MEDIUMTEXT      NULL,
  totp_secret     VARCHAR(64)     NULL,
  totp_confirmado TINYINT(1)      NOT NULL DEFAULT 0,
  -- Janela TOTP já usada, para um código não valer duas vezes
  -- (replay dentro dos mesmos 30 segundos).
  totp_ultimo_step BIGINT         NULL,
  tentativas      SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  bloqueado_ate   DATETIME        NULL,
  criado_em       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  atualizado_em   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                  ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_usuarios_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Sessões ─────────────────────────────────────────────────
-- Guardamos o HASH do token, não o token: vazou o dump do banco,
-- ninguém entra com o que estiver escrito aqui.
--
-- `dois_fatores_ok` = 0 significa "autenticou senha, falta o
-- código". Toda rota de dado exige esse campo em 1.
CREATE TABLE IF NOT EXISTS sessoes (
  id              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  usuario_id      INT UNSIGNED    NOT NULL,
  token_hash      CHAR(64)        NOT NULL,
  dois_fatores_ok TINYINT(1)      NOT NULL DEFAULT 0,
  criado_em       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expira_em       DATETIME        NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_sessoes_token (token_hash),
  KEY ix_sessoes_usuario (usuario_id),
  KEY ix_sessoes_expira (expira_em),
  CONSTRAINT fk_sessoes_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Transações ──────────────────────────────────────────────
-- Mesmas colunas do SQLite original, com os tipos certos:
--   data       DATE     (era TEXT "DD/MM/AAAA")
--   valor      DECIMAL  (era REAL; ponto flutuante não guarda
--                        dinheiro; 0.1+0.2 já erra no centavo)
--   natureza   ENUM     (era TEXT livre, "Receita"/"receita"/…)
--   recorrencia ENUM
CREATE TABLE IF NOT EXISTS transacoes (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  usuario_id  INT UNSIGNED    NOT NULL,
  data        DATE            NOT NULL,
  nome        VARCHAR(160)    NOT NULL,
  valor       DECIMAL(12,2)   NOT NULL,
  natureza    ENUM('receita','despesa')  NOT NULL,
  categoria   VARCHAR(80)     NOT NULL DEFAULT 'Sem categoria',
  -- 1 = o usuário escolheu a categoria; regra de categoria não troca.
  categoria_manual TINYINT(1) NOT NULL DEFAULT 0,
  recorrencia ENUM('unica','mensal')     NOT NULL DEFAULT 'unica',
  -- Fica no histórico mas sai de totais e gráficos (dinheiro de passagem).
  ignorada    TINYINT(1)      NOT NULL DEFAULT 0,
  -- Tela Conferir números, só nas importadas que pareciam movimento
  -- interno e ficaram na soma: 'certo' = contar está certo; 'errado' =
  -- era o mesmo dinheiro de outro lançamento (a tela também a ignora).
  conferencia ENUM('certo','errado') NULL,
  -- Só nas importadas: a previsão do mês não desconta da conta o que vai
  -- para a fatura do cartão.
  meio        ENUM('conta','cartao') NULL,
  observacao  VARCHAR(255)    NULL,
  -- Id da transação na Pluggy quando veio do Open Finance; NULL quando foi
  -- lançada à mão. A chave única é o que deixa reimportar o mesmo período
  -- sem duplicar (o MySQL aceita vários NULL numa UNIQUE).
  origem_id   VARCHAR(64)     NULL,
  -- De qual conexão bancária veio (importadas). Sem FK de propósito: ao
  -- desconectar, os lançamentos ficam, e se a conexão era privada eles
  -- viram privados antes (ver desconectar em app.py).
  conexao_id  INT UNSIGNED    NULL,
  -- Cadeado: privado não aparece para o espaço nem entra no Juntos.
  privada     TINYINT(1)      NOT NULL DEFAULT 0,
  criado_em   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_transacoes_origem (usuario_id, origem_id),
  KEY ix_transacoes_conexao (conexao_id),
  -- O dashboard sempre filtra por usuário + faixa de data: este é o
  -- índice que serve praticamente todas as consultas dele.
  KEY ix_transacoes_usuario_data (usuario_id, data),
  KEY ix_transacoes_categoria (usuario_id, categoria),
  CONSTRAINT fk_transacoes_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE,
  CONSTRAINT ck_transacoes_valor CHECK (valor > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Orçamentos ──────────────────────────────────────────────
-- Teto mensal por categoria. Alimenta os alertas de "gasto acima
-- do previsto" do dashboard.
CREATE TABLE IF NOT EXISTS orcamentos (
  usuario_id INT UNSIGNED  NOT NULL,
  categoria  VARCHAR(80)   NOT NULL,
  teto       DECIMAL(12,2) NOT NULL,
  PRIMARY KEY (usuario_id, categoria),
  CONSTRAINT fk_orcamentos_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE,
  CONSTRAINT ck_orcamentos_teto CHECK (teto >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Investimentos ───────────────────────────────────────────
-- Uma linha por posição. O valor ATUAL não é guardado: ele é
-- quantidade x cotação do momento, buscada na brapi a cada carga
-- da tela (api/cotacoes.py). Gravar um "valor atual" no banco só
-- criaria um número desatualizado contradizendo a tela.
CREATE TABLE IF NOT EXISTS investimentos (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  usuario_id  INT UNSIGNED    NOT NULL,
  -- Ticker da B3 em maiúsculas (PETR4, HGLG11, BOVA11). A brapi também
  -- cobre cripto e câmbio, então o campo não é restrito a ações.
  ticker      VARCHAR(16)     NOT NULL,
  -- DECIMAL e não FLOAT, mesmo motivo de `transacoes.valor`. As 8 casas
  -- são para cripto, onde comprar 0.00351 BTC é normal.
  quantidade  DECIMAL(18,8)   NOT NULL,
  preco_medio DECIMAL(18,8)   NOT NULL,
  data        DATE            NOT NULL,
  -- Cadeado: a posição fica fora da visão dos outros membros do espaço.
  privada     TINYINT(1)      NOT NULL DEFAULT 0,
  criado_em   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_investimentos_usuario (usuario_id, ticker),
  CONSTRAINT fk_investimentos_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE,
  CONSTRAINT ck_investimentos_qtd CHECK (quantidade > 0),
  CONSTRAINT ck_investimentos_preco CHECK (preco_medio > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Metas e subtarefas ──────────────────────────────────────
-- Metas gamificadas: cada subtarefa concluída dá XP, e a meta
-- inteira dá um bônus maior que a soma das subtarefas dela.
-- O XP e o nível NÃO são gravados: são derivados do que está
-- concluído (api/gamificacao.py). Guardar o total abriria espaço
-- para ele divergir das subtarefas que o justificam.
CREATE TABLE IF NOT EXISTS metas (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  usuario_id  INT UNSIGNED    NOT NULL,
  titulo      VARCHAR(160)    NOT NULL,
  descricao   TEXT            NULL,
  -- NULL quando a meta não é financeira ("correr 10km", "ler 12 livros").
  alvo        DECIMAL(14,2)   NULL,
  guardado    DECIMAL(14,2)   NOT NULL DEFAULT 0,
  prazo       DATE            NULL,
  concluida   TINYINT(1)      NOT NULL DEFAULT 0,
  concluida_em DATETIME       NULL,
  -- Multiplicador de dificuldade congelado na conclusão (gamificacao.py).
  -- NULL em meta aberta: aí ele é calculado na hora, pela renda atual.
  multiplicador DECIMAL(3,2)  NULL,
  -- Meta do espaço: todo membro vê e mexe (guardado, passos, concluir).
  -- NULL é meta pessoal. Sem chave estrangeira de propósito: quando o
  -- espaço acaba, api/espacos.py devolve a meta para quem a criou.
  espaco_id   INT UNSIGNED    NULL,
  criado_em   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_metas_usuario (usuario_id),
  KEY ix_metas_espaco (espaco_id),
  CONSTRAINT fk_metas_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS subtarefas (
  id            BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
  meta_id       BIGINT UNSIGNED   NOT NULL,
  titulo        VARCHAR(200)      NOT NULL,
  concluida     TINYINT(1)        NOT NULL DEFAULT 0,
  -- XP por subtarefa em vez de valor fixo: a IA pondera passo difícil
  -- valendo mais que passo trivial.
  xp            SMALLINT UNSIGNED NOT NULL DEFAULT 10,
  ordem         SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  gerada_por_ia TINYINT(1)        NOT NULL DEFAULT 0,
  concluida_em  DATETIME          NULL,
  criado_em     DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_subtarefas_meta (meta_id, ordem),
  -- Sem usuario_id aqui de propósito: a dona é a meta, e a checagem de
  -- posse sempre passa por ela (JOIN em metas).
  CONSTRAINT fk_subtarefas_meta FOREIGN KEY (meta_id)
    REFERENCES metas (id) ON DELETE CASCADE,
  CONSTRAINT ck_subtarefas_xp CHECK (xp > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Conexões do Open Finance ────────────────────────────────
-- Só o id da conexão na Pluggy (o "item"). Saldo e fatura NÃO são
-- gravados: são lidos da Pluggy a cada carga da tela, pelo mesmo motivo
-- do valor atual dos investimentos (api/openfinance.py).
CREATE TABLE IF NOT EXISTS conexoes_bancarias (
  id                 INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  usuario_id         INT UNSIGNED  NOT NULL,
  item_id            CHAR(36)      NOT NULL,
  instituicao        VARCHAR(120)  NOT NULL DEFAULT '',
  -- Até onde a última importação de transações foi. A próxima sugere
  -- começar um pouco antes daqui, e não do começo de tudo.
  importado_ate      DATE          NULL,
  -- Conta inteira fora da visão do espaço (e tudo o que vem dela).
  privada            TINYINT(1)    NOT NULL DEFAULT 0,
  criado_em          DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_conexoes_item (usuario_id, item_id),
  CONSTRAINT fk_conexoes_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Credencial da Pluggy de cada pessoa ─────────────────────
-- O Meu Pluggy gratuito é intransferível: cada pessoa lê os próprios bancos
-- com a própria aplicação na Pluggy. Uma linha por pessoa. O Client Secret
-- fica cifrado (api/cofre.py, chave FIN_CHAVE_CREDENCIAIS no .env, fora
-- deste banco); o Client ID não é segredo.
CREATE TABLE IF NOT EXISTS credenciais_pluggy (
  usuario_id     INT UNSIGNED  NOT NULL,
  client_id      CHAR(36)      NOT NULL,
  client_secret  VARCHAR(512)  NOT NULL,
  atualizado_em  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                               ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (usuario_id),
  CONSTRAINT fk_credenciais_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Regras de categoria ─────────────────────────────────────
-- "Descrição contém X vira categoria Y", aplicada a cada importação e,
-- ao ser criada, às importadas que já existem. `padrao` fica normalizado
-- (minúsculo, sem acento) para casar com o texto que o Python gera.
CREATE TABLE IF NOT EXISTS regras_categoria (
  id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  usuario_id  INT UNSIGNED  NOT NULL,
  padrao      VARCHAR(120)  NOT NULL,
  categoria   VARCHAR(80)   NOT NULL,
  criado_em   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_regras_padrao (usuario_id, padrao),
  CONSTRAINT fk_regras_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Aceites dos termos e da política de privacidade ─────────
-- Uma linha por aceite, sem sobrescrever: é a prova do consentimento
-- (LGPD, art. 8º, §2º). Vale a versão da linha mais recente; quando
-- documentos.VERSAO sobe, a API pede o aceite de novo.
CREATE TABLE IF NOT EXISTS aceites (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  usuario_id  INT UNSIGNED    NOT NULL,
  versao      VARCHAR(20)     NOT NULL,
  aceito_em   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_aceites_usuario (usuario_id, id),
  CONSTRAINT fk_aceites_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Descartes da importação ─────────────────────────────────
-- O que a importação do Open Finance deixou FORA da soma (pagamento de
-- fatura, transferência entre as próprias contas), com o par que a regra
-- achou. Existe para a tela Conferir números: cada descarte é marcado como
-- certo ou errado, e daí sai a taxa de acerto da regra.
-- `veredito` volta a NULL quando a regra muda o motivo ou o par: o que foi
-- conferido era outra decisão. 'errado' devolve o lançamento para a soma,
-- e as importações seguintes respeitam isso.
CREATE TABLE IF NOT EXISTS descartes (
  id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  usuario_id    INT UNSIGNED    NOT NULL,
  origem_id     VARCHAR(64)     NOT NULL,
  data          DATE            NOT NULL,
  nome          VARCHAR(160)    NOT NULL,
  valor         DECIMAL(12,2)   NOT NULL,
  natureza      ENUM('receita','despesa') NOT NULL,
  meio          ENUM('conta','cartao')    NOT NULL,
  -- Nome da conta ou do cartão na Pluggy: é o que diz de onde saiu.
  conta         VARCHAR(120)    NOT NULL DEFAULT '',
  categoria     VARCHAR(80)     NOT NULL DEFAULT 'Sem categoria',
  motivo        ENUM('pagamentoFatura','transferencias') NOT NULL,
  par_origem_id VARCHAR(64)     NULL,
  veredito      ENUM('certo','errado') NULL,
  conferido_em  DATETIME        NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_descartes_origem (usuario_id, origem_id),
  KEY ix_descartes_usuario_data (usuario_id, data),
  CONSTRAINT fk_descartes_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Passkeys (entrar com Face ID / digital) ─────────────────
-- WebAuthn: o aparelho guarda a chave privada, presa ao domínio do app, e
-- só a libera com a biometria ou o desbloqueio dele. Aqui fica a chave
-- PÚBLICA, com a qual o servidor confere cada entrada. A biometria nunca
-- sai do aparelho. Ver api/passkeys.py.
CREATE TABLE IF NOT EXISTS passkeys (
  id             INT UNSIGNED     NOT NULL AUTO_INCREMENT,
  usuario_id     INT UNSIGNED     NOT NULL,
  credencial_id  VARBINARY(255)   NOT NULL,
  chave_publica  VARBINARY(1024)  NOT NULL,
  contador       BIGINT UNSIGNED  NOT NULL DEFAULT 0,
  apelido        VARCHAR(80)      NOT NULL,
  criado_em      DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
  usado_em       DATETIME         NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_passkeys_credencial (credencial_id),
  KEY ix_passkeys_usuario (usuario_id),
  CONSTRAINT fk_passkeys_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Desafio de cada cerimônia WebAuthn, de uso único. Mora no banco e não na
-- memória porque na Vercel cada chamada pode cair numa instância diferente.
CREATE TABLE IF NOT EXISTS desafios_webauthn (
  id          CHAR(32)        NOT NULL,
  desafio     VARBINARY(64)   NOT NULL,
  tipo        VARCHAR(10)     NOT NULL,
  usuario_id  INT UNSIGNED    NULL,
  expira_em   DATETIME        NOT NULL,
  PRIMARY KEY (id),
  KEY ix_desafios_expira (expira_em)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Espaço compartilhado (casal, família) ───────────────────
-- Um espaço junta até 6 pessoas que veem as finanças umas das outras
-- (menos o que cada uma marcar como privado). Nasce quando alguém aceita
-- um convite: o espaço nunca existe vazio. Cada pessoa está em no máximo
-- um espaço (PRIMARY KEY em usuario_id). Ver api/espacos.py.
CREATE TABLE IF NOT EXISTS espacos (
  id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  nome        VARCHAR(80)   NOT NULL DEFAULT '',
  criado_em   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS espaco_membros (
  usuario_id  INT UNSIGNED  NOT NULL,
  espaco_id   INT UNSIGNED  NOT NULL,
  -- 'dono' convida e remove; 'membro' só sai. O primeiro dono é quem
  -- convidou; se ele sair, o membro mais antigo herda.
  papel       VARCHAR(10)   NOT NULL DEFAULT 'membro',
  entrou_em   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (usuario_id),
  KEY ix_membros_espaco (espaco_id),
  CONSTRAINT fk_membros_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE,
  CONSTRAINT fk_membros_espaco FOREIGN KEY (espaco_id)
    REFERENCES espacos (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Convite por link, de uso único, válido por 7 dias. No banco fica só o
-- hash do código, como nas sessões. `usado_por` é quem pegou o convite
-- (ao criar a conta por ele, ou ao abrir com conta já existente);
-- `aceito_em` é quando essa pessoa disse sim ao vínculo.
CREATE TABLE IF NOT EXISTS convites (
  id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  token_hash  CHAR(64)      NOT NULL,
  criado_por  INT UNSIGNED  NOT NULL,
  expira_em   DATETIME      NOT NULL,
  usado_por   INT UNSIGNED  NULL,
  usado_em    DATETIME      NULL,
  aceito_em   DATETIME      NULL,
  criado_em   DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_convites_token (token_hash),
  KEY ix_convites_criador (criado_por),
  KEY ix_convites_usado_por (usado_por),
  CONSTRAINT fk_convites_criador FOREIGN KEY (criado_por)
    REFERENCES usuarios (id) ON DELETE CASCADE,
  CONSTRAINT fk_convites_usado_por FOREIGN KEY (usado_por)
    REFERENCES usuarios (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Orçamento do espaço: tetos da casa, comparados com o gasto somado na
-- visão Juntos. Os tetos de cada um seguem em `orcamentos`. Qualquer
-- membro edita; o espaço acabou, os tetos dele vão junto.
CREATE TABLE IF NOT EXISTS orcamentos_espaco (
  espaco_id  INT UNSIGNED  NOT NULL,
  categoria  VARCHAR(80)   NOT NULL,
  teto       DECIMAL(12,2) NOT NULL,
  PRIMARY KEY (espaco_id, categoria),
  CONSTRAINT fk_orc_espaco FOREIGN KEY (espaco_id)
    REFERENCES espacos (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ── Notificações push (api/notificacoes.py) ─────────────────
-- Cada aparelho que ativou as notificações. O endpoint é a "caixa postal"
-- do aparelho no serviço de push do sistema (Apple, Google, Mozilla); as
-- chaves cifram a mensagem de ponta a ponta. Fica o hash do endpoint como
-- chave única porque ele passa de 255 caracteres.
CREATE TABLE IF NOT EXISTS push_inscricoes (
  id             INT UNSIGNED  NOT NULL AUTO_INCREMENT,
  usuario_id     INT UNSIGNED  NOT NULL,
  endpoint_hash  CHAR(64)      NOT NULL,
  endpoint       VARCHAR(1000) NOT NULL,
  p256dh         VARCHAR(200)  NOT NULL,
  auth           VARCHAR(100)  NOT NULL,
  aparelho       VARCHAR(80)   NOT NULL DEFAULT '',
  criado_em      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_push_endpoint (endpoint_hash),
  KEY ix_push_usuario (usuario_id),
  CONSTRAINT fk_push_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- O que a pessoa quer receber. Sem linha = tudo ligado.
CREATE TABLE IF NOT EXISTS notif_preferencias (
  usuario_id  INT UNSIGNED  NOT NULL,
  entradas    TINYINT(1)    NOT NULL DEFAULT 1,
  saidas      TINYINT(1)    NOT NULL DEFAULT 1,
  faturas     TINYINT(1)    NOT NULL DEFAULT 1,
  PRIMARY KEY (usuario_id),
  CONSTRAINT fk_notif_pref_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Webhook da Pluggy de cada pessoa (criado com a credencial DELA). `rota`
-- vai na URL e diz de quem é o aviso; o segredo vai num cabeçalho e aqui
-- fica só o hash. A Pluggy não assina os avisos: é o segredo que prova a
-- origem.
CREATE TABLE IF NOT EXISTS webhooks_pluggy (
  usuario_id    INT UNSIGNED  NOT NULL,
  rota          CHAR(32)      NOT NULL,
  segredo_hash  CHAR(64)      NOT NULL,
  webhook_id    VARCHAR(64)   NULL,
  client_id     CHAR(36)      NOT NULL,
  criado_em     DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (usuario_id),
  UNIQUE KEY uq_webhooks_rota (rota),
  CONSTRAINT fk_webhooks_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Aviso que só pode sair uma vez (ex.: "fatura vence amanhã" daquele
-- cartão naquele vencimento), mesmo com a rotina diária rodando de novo.
CREATE TABLE IF NOT EXISTS notificacoes_enviadas (
  usuario_id  INT UNSIGNED  NOT NULL,
  chave       VARCHAR(160)  NOT NULL,
  enviada_em  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (usuario_id, chave),
  CONSTRAINT fk_notif_env_usuario FOREIGN KEY (usuario_id)
    REFERENCES usuarios (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
