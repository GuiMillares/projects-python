"""Modelos de dados usados em todo o projeto."""

import hashlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CriteriosBusca:
    """Critérios definidos pelo usuário na tela de busca."""

    cargo: str
    modelo_trabalho: str = "Qualquer"  # Qualquer, Remoto, Híbrido, Presencial
    salario_minimo: Optional[float] = None
    salario_maximo: Optional[float] = None
    localizacao: Optional[str] = None


@dataclass
class Vaga:
    """Representa uma vaga encontrada em alguma fonte."""

    titulo: str
    empresa: str
    fonte: str  # linkedin, indeed, google, gupy, site_empresa
    url: str
    descricao: str
    modelo_trabalho: Optional[str] = None
    salario: Optional[str] = None
    tipo_candidatura: str = "manual"  # manual, gupy, site_empresa, candidatura_simplificada
    score_compatibilidade: Optional[float] = None
    palavras_em_comum: list = field(default_factory=list)
    palavras_faltando: list = field(default_factory=list)
    id: str = field(init=False)

    def __post_init__(self):
        # ID estável baseado na fonte + URL, para servir de chave de deduplicação
        base = f"{self.fonte}:{self.url}".encode("utf-8")
        self.id = hashlib.sha256(base).hexdigest()[:16]
