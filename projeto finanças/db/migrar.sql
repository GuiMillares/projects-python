-- Alterações em bancos que já existem.
--
-- O schema.sql cria tudo do zero, mas `CREATE TABLE IF NOT EXISTS` não
-- mexe em tabela já criada. Este arquivo é o que atualiza um banco vivo.
--
--   mysql -u root --skip-password < db/migrar.sql
--
-- Pode rodar quantas vezes quiser.

USE local_finance;

-- 2026-08: foto de perfil
-- O MySQL não tem ADD COLUMN IF NOT EXISTS, então a coluna é conferida
-- antes; sem isso a segunda execução falharia com "Duplicate column".
SET @existe := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = 'local_finance'
     AND TABLE_NAME = 'usuarios'
     AND COLUMN_NAME = 'foto'
);

SET @sql := IF(@existe = 0,
  'ALTER TABLE usuarios ADD COLUMN foto MEDIUMTEXT NULL AFTER nome',
  'SELECT "coluna usuarios.foto já existe" AS aviso'
);

PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- 2026-08: investimentos por ticker
--
-- A primeira versão da tabela guardava `nome/tipo/aplicado/atual`, ou seja,
-- o valor atual digitado à mão. Com a cotação vindo da brapi, `atual` deixa
-- de fazer sentido: ele passa a ser quantidade x preço do momento, e um
-- valor gravado só ficaria desatualizado contradizendo a tela.
--
-- A troca só acontece se a tabela ainda estiver no formato antigo E vazia.
-- Recriar tabela com dado dentro apagaria o dado, então o guarda-chuva aqui
-- é duplo de propósito.
SET @tem_ticker := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = 'local_finance'
     AND TABLE_NAME = 'investimentos'
     AND COLUMN_NAME = 'ticker'
);

SET @linhas := (SELECT COUNT(*) FROM investimentos);

SET @sql := IF(@tem_ticker = 0 AND @linhas = 0,
  'DROP TABLE IF EXISTS investimentos',
  'SELECT "investimentos mantida como está" AS aviso'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

CREATE TABLE IF NOT EXISTS investimentos (
  id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  usuario_id  INT UNSIGNED    NOT NULL,
  -- Ticker da B3 em maiúsculas (PETR4, HGLG11, BOVA11). A brapi também
  -- aceita cripto e câmbio, então o campo não é restrito a ações.
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

-- 2026-08: metas gamificadas + subtarefas
--
-- A tabela `metas` original só previa meta financeira (alvo NOT NULL).
-- Agora ela também cobre meta sem valor ("correr 10km"), então `alvo`
-- passa a aceitar NULL e ganha descrição.
SET @tem_descricao := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = 'local_finance' AND TABLE_NAME = 'metas'
     AND COLUMN_NAME = 'descricao'
);
SET @sql := IF(@tem_descricao = 0,
  'ALTER TABLE metas ADD COLUMN descricao TEXT NULL AFTER titulo',
  'SELECT "metas.descricao já existe" AS aviso');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

SET @tem_concluida_em := (
  SELECT COUNT(*) FROM information_schema.COLUMNS
   WHERE TABLE_SCHEMA = 'local_finance' AND TABLE_NAME = 'metas'
     AND COLUMN_NAME = 'concluida_em'
);
SET @sql := IF(@tem_concluida_em = 0,
  'ALTER TABLE metas ADD COLUMN concluida_em DATETIME NULL',
  'SELECT "metas.concluida_em já existe" AS aviso');
PREPARE stmt FROM @sql; EXECUTE stmt; DEALLOCATE PREPARE stmt;

-- MODIFY é naturalmente idempotente: reaplicar o mesmo tipo não faz nada.
ALTER TABLE metas MODIFY COLUMN alvo DECIMAL(14,2) NULL;

-- Subtarefas: os passos concretos de uma meta. Cada uma vale XP.
CREATE TABLE IF NOT EXISTS subtarefas (
  id            BIGINT UNSIGNED   NOT NULL AUTO_INCREMENT,
  meta_id       BIGINT UNSIGNED   NOT NULL,
  titulo        VARCHAR(200)      NOT NULL,
  concluida     TINYINT(1)        NOT NULL DEFAULT 0,
  -- XP por subtarefa em vez de valor fixo: a IA pondera passo difícil
  -- valendo mais que passo trivial.
  xp            SMALLINT UNSIGNED NOT NULL DEFAULT 10,
  ordem         SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  -- Marca a procedência para a tela distinguir o que a IA sugeriu do que
  -- foi escrito à mão.
  gerada_por_ia TINYINT(1)        NOT NULL DEFAULT 0,
  concluida_em  DATETIME          NULL,
  criado_em     DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY ix_subtarefas_meta (meta_id, ordem),
  -- Sem usuario_id aqui de propósito: a dona é a meta, e a checagem de
  -- posse sempre passa por ela (JOIN em metas). Duplicar o usuário abriria
  -- espaço para os dois campos discordarem.
  CONSTRAINT fk_subtarefas_meta FOREIGN KEY (meta_id)
    REFERENCES metas (id) ON DELETE CASCADE,
  CONSTRAINT ck_subtarefas_xp CHECK (xp > 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
