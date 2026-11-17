"""Entrada da API na Vercel.

Na Vercel o Flask não roda com `python app.py`: a plataforma importa este
arquivo e usa o objeto `app`. Só este arquivo é função; os outros módulos
de api/ são importados por ele (ver vercel.json, que declara a entrada
única para a Vercel não transformar cada .py numa função).

Aqui também fica o que só vale fora do PC:

* Fuso. O servidor da Vercel roda em UTC, e o código mistura
  datetime.now() do Python com NOW() do MySQL. Sem acertar os dois, um
  lançamento das 22h cairia no dia seguinte. O TZ vai em formato POSIX
  ("<-03>3" = UTC-3, o horário de Brasília, que não tem mais horário de
  verão), porque esse formato não depende dos arquivos de fuso do sistema.
  A sessão do MySQL recebe o mesmo deslocamento (db.py, FIN_DB_FUSO).
* No PC nada disto roda: lá continua valendo `python app.py`.
"""

import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

os.environ["TZ"] = os.getenv("FIN_FUSO_POSIX", "<-03>3")
time.tzset()
os.environ.setdefault("FIN_DB_FUSO", "-03:00")

# Domínio das passkeys. Fixo de propósito, e não lido do cabeçalho Host:
# a origem esperada é o que impede um site falso de usar a passkey.
os.environ.setdefault("FIN_WEBAUTHN_RP_ID", "meulastro.vercel.app")
os.environ.setdefault("FIN_WEBAUTHN_ORIGENS", "https://meulastro.vercel.app")

from app import app  # noqa: E402,F401
