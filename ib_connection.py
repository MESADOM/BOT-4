import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional, Set, Tuple

from ib_insync import IB, Trade


logger = logging.getLogger(__name__)


@dataclass
class IBConfig:
    host: str = os.getenv("IB_HOST", "127.0.0.1")
    port: int = int(os.getenv("IB_PORT", "4002"))
    client_id: int = int(os.getenv("IB_CLIENT_ID", "1"))
    connect_timeout: float = float(os.getenv("IB_CONNECT_TIMEOUT", "8"))
    max_retries: int = int(os.getenv("IB_MAX_RETRIES", "10"))
    retry_delay: float = float(os.getenv("IB_RETRY_DELAY", "3"))


class IBConnectionManager:
    """Capa de conectividad robusta para IB Gateway (Paper/Real)."""

    def __init__(self, config: Optional[IBConfig] = None) -> None:
        self.config = config or IBConfig()
        self.ib = IB()
        self._next_valid_id_ready = threading.Event()
        self._sent_orders: Set[Tuple[str, str, str]] = set()

        self.ib.connectedEvent += self._on_connected
        self.ib.disconnectedEvent += self._on_disconnected

    def _on_connected(self) -> None:
        logger.info(
            "Conexión IBKR OK -> host=%s port=%s clientId=%s",
            self.config.host,
            self.config.port,
            self.config.client_id,
        )

    def _on_disconnected(self) -> None:
        logger.warning("Desconexión detectada de IBKR")
        self._next_valid_id_ready.clear()

    def _wait_for_next_valid_id(self, timeout: float) -> bool:
        started = time.time()
        while time.time() - started < timeout:
            self.ib.sleep(0.2)
            if self.ib.client and self.ib.client.isReady():
                self._next_valid_id_ready.set()
                return True
        return False

    def connect_ib(self) -> bool:
        """Conecta con reintentos, timeout y logs claros."""
        for attempt in range(1, self.config.max_retries + 1):
            try:
                if self.ib.isConnected():
                    if self._wait_for_next_valid_id(self.config.connect_timeout):
                        return True

                logger.info(
                    "Conectando a IB Gateway (intento %s/%s)...",
                    attempt,
                    self.config.max_retries,
                )
                self.ib.connect(
                    self.config.host,
                    self.config.port,
                    clientId=self.config.client_id,
                    timeout=self.config.connect_timeout,
                )

                if self._wait_for_next_valid_id(self.config.connect_timeout):
                    return True

                logger.error("Conectado pero sin estado ready/nextValidId dentro de timeout")
                self.ib.disconnect()
            except Exception as exc:
                logger.error("Error de conexión con IBKR: %s", exc)

            time.sleep(self.config.retry_delay)

        return False

    def ensure_connection(self) -> bool:
        """Verifica conexión activa y reconecta si se cae."""
        if self.ib.isConnected() and self._wait_for_next_valid_id(1.5):
            return True

        logger.warning("Conexión no activa/lista. Intentando reconectar...")
        return self.connect_ib()

    def place_order_once(self, contract, order, dedupe_key: Optional[Tuple[str, str, str]] = None) -> Optional[Trade]:
        """Evita duplicar órdenes tras reconexiones usando clave de deduplicación."""
        if not self.ensure_connection():
            logger.error("No se puede enviar orden: sin conexión IBKR")
            return None

        key = dedupe_key or (
            getattr(contract, "symbol", "UNK"),
            getattr(order, "action", "UNK"),
            str(getattr(order, "totalQuantity", "UNK")),
        )

        if key in self._sent_orders:
            logger.warning("Orden duplicada bloqueada: %s", key)
            return None

        try:
            trade = self.ib.placeOrder(contract, order)
            self._sent_orders.add(key)
            logger.info("Orden enviada: %s", key)
            return trade
        except Exception as exc:
            logger.error("Fallo/rechazo al enviar orden %s: %s", key, exc)
            return None

    def disconnect(self) -> None:
        if self.ib.isConnected():
            self.ib.disconnect()
            logger.info("Conexión con IBKR cerrada limpiamente")
