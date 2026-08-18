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
  recorrencia ENUM('unica','mensal')     NOT NULL DEFAULT 'unica',
  observacao  VARCHAR(255)    NULL,
  criado_em   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
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
  criado_em   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_metas_usuario (usuario_id),
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
