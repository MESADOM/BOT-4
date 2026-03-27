from __future__ import annotations

import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from threading import Event
from typing import Any, Dict

from META_BOT import (
    BASE_DIR,
    IB_CURRENCY,
    IB_EXCHANGE,
    IB_HOST_POR_DEFECTO,
    IB_PORT_PAPER,
    IB_SYMBOL,
    MODO_EJECUCION_PAPER,
    RUTA_ESTADO_SENALES_IB,
    _cargar_env_local,
    ejecutar_bot,
)
from ib_manager import IBOrderManager


@dataclass
class ProcessConfig:
    host: str
    port: int
    client_id: int
    loop_seconds: int
    max_reintentos: int
    timeout: float


def _build_config() -> ProcessConfig:
    _cargar_env_local(BASE_DIR / ".env")
    return ProcessConfig(
        host=os.getenv("IB_HOST", IB_HOST_POR_DEFECTO),
        port=int(os.getenv("IB_PORT", str(IB_PORT_PAPER))),
        client_id=int(os.getenv("IB_CLIENT_ID", "1")),
        loop_seconds=max(5, int(os.getenv("PAPER_LOOP_SECONDS", "60"))),
        max_reintentos=max(1, int(os.getenv("IB_MAX_RETRIES", "3"))),
        timeout=float(os.getenv("IB_TIMEOUT", "8")),
    )


def _configure_logging() -> logging.Logger:
    level_name = os.getenv("PAPER_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger("paper_runner")


def _install_signal_handlers(stop_event: Event, logger: logging.Logger) -> None:
    stop_event.stop_reason = "cierre manual o señal del sistema"  # type: ignore[attr-defined]

    def _handle_shutdown(signum: int, _frame: Any) -> None:
        logger.warning("Señal de apagado recibida: %s", signum)
        stop_event.stop_reason = f"señal del sistema ({signum})"  # type: ignore[attr-defined]
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_shutdown)


def _sleep_interruptible(seconds: int, stop_event: Event) -> None:
    for _ in range(seconds):
        if stop_event.is_set():
            return
        time.sleep(1)


def main() -> int:
    logger = _configure_logging()
    stop_event = Event()
    _install_signal_handlers(stop_event, logger)

    cfg = _build_config()
    logger.info(
        "Inicio paper runner | host=%s port=%s clientId=%s loop=%ss",
        cfg.host,
        cfg.port,
        cfg.client_id,
        cfg.loop_seconds,
    )

    manager = IBOrderManager(
        host=cfg.host,
        port=cfg.port,
        client_id=cfg.client_id,
        symbol=IB_SYMBOL,
        exchange=IB_EXCHANGE,
        currency=IB_CURRENCY,
        state_path=RUTA_ESTADO_SENALES_IB,
        max_reintentos=cfg.max_reintentos,
        connect_timeout=cfg.timeout,
        logger=logging.getLogger("ib_manager"),
    )
    manager.notify_bot_started()

    try:
        while not stop_event.is_set():
            try:
                if not manager.ensure_connection():
                    logger.warning("IB no conectado; se reintentará en el próximo ciclo.")
                resultado: Dict[str, Any] = ejecutar_bot(modo=MODO_EJECUCION_PAPER, ib_manager=manager)
                ib_resultado = resultado.get("ib_resultado")
                logger.info("Ciclo completado | ib_resultado=%s", ib_resultado)
            except Exception as exc:
                logger.exception("Error en ciclo paper: %s", exc)

            _sleep_interruptible(cfg.loop_seconds, stop_event)

    finally:
        logger.info("Apagado limpio del paper runner.")
        motivo = getattr(stop_event, "stop_reason", "cierre manual o señal del sistema")
        manager.notify_bot_stopped(motivo=motivo)
        manager.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
