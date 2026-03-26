from __future__ import annotations

from META_BOT import MODO_EJECUCION_PAPER, ejecutar_bot


if __name__ == "__main__":
    resultado = ejecutar_bot(modo=MODO_EJECUCION_PAPER)
    print(resultado.get("ib_resultado"))
