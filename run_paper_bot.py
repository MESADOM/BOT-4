import logging
import signal
import sys
import time

from dotenv import load_dotenv

from META_BOT import VERSION, ejecutar_bot
from ib_connection import IBConnectionManager


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("run_paper_bot")

RUNNING = True


def _handle_stop(signum, _frame):
    global RUNNING
    logger.info("Señal %s recibida. Cerrando bot limpiamente...", signum)
    RUNNING = False


def main() -> int:
    signal.signal(signal.SIGINT, _handle_stop)
    signal.signal(signal.SIGTERM, _handle_stop)

    ib_manager = IBConnectionManager()
    if not ib_manager.connect_ib():
        logger.error("No se pudo establecer conexión inicial con IB Gateway")
        return 1

    logger.info("Bot PAPER iniciado. Versión=%s", VERSION)

    try:
        while RUNNING:
            if not ib_manager.ensure_connection():
                logger.error("No hay conexión activa. Reintentando en ciclo...")
                time.sleep(2)
                continue

            # No altera estrategia: delega en META_BOT.ejecutar_bot()
            ejecutar_bot(ib_manager=ib_manager)
            time.sleep(1)
    finally:
        ib_manager.disconnect()

    logger.info("Bot finalizado correctamente")
    return 0


if __name__ == "__main__":
    sys.exit(main())
