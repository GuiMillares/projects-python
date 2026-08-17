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
