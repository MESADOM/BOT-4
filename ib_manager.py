from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus
from urllib.request import urlopen

try:
    from ib_insync import IB, MarketOrder, Stock
except ImportError:  # pragma: no cover - dependencia opcional en entorno local
    IB = None
    MarketOrder = None
    Stock = None


@dataclass
class IBSignalResult:
    estado: str
    detalle: str
    signal_id: Optional[str] = None
    order_id: Optional[int] = None


class IBOrderManager:
    """
    Capa única de conectividad + ejecución IB.

    Estrategia/Motor: META_BOT.py
    Ejecución real: este manager
    Proceso continuo: run_paper_bot.py
    """

    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        symbol: str,
        exchange: str,
        currency: str,
        state_path: Path,
        connect_timeout: float = 8.0,
        max_reintentos: int = 3,
        retry_delay_segundos: float = 2.0,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.client_id = int(client_id)
        self.symbol = symbol
        self.exchange = exchange
        self.currency = currency
        self.state_path = Path(state_path)

        self.connect_timeout = float(connect_timeout)
        self.max_reintentos = max(1, int(max_reintentos))
        self.retry_delay_segundos = max(0.0, float(retry_delay_segundos))

        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._ib: Optional[IB] = None
        self._was_connected = False

    # -----------------------------
    # Conectividad
    # -----------------------------
    def connect_ib(self) -> bool:
        if IB is None:
            self.logger.error("ib_insync no está instalado. No se puede conectar a IB Gateway.")
            return False

        if self._ib is None:
            self._ib = IB()

        if self._ib.isConnected():
            return True

        for intento in range(1, self.max_reintentos + 1):
            try:
                self.logger.info(
                    "Conectando a IB Gateway host=%s port=%s clientId=%s intento=%s/%s",
                    self.host,
                    self.port,
                    self.client_id,
                    intento,
                    self.max_reintentos,
                )
                self._ib.connect(
                    self.host,
                    self.port,
                    clientId=self.client_id,
                    timeout=self.connect_timeout,
                )
                if self._ib.isConnected():
                    self.logger.info("Conexión IB establecida correctamente.")
                    if not self._was_connected:
                        self._notify_ib_reconnected()
                    self._was_connected = True
                    return True
            except Exception as exc:
                self.logger.warning("Falló conexión IB (intento %s): %s", intento, exc)

            if intento < self.max_reintentos:
                time.sleep(self.retry_delay_segundos)

        self.logger.error("No se pudo conectar a IB tras %s intentos.", self.max_reintentos)
        if self._was_connected:
            self._notify_ib_disconnected("No se pudo reconectar tras reintentos")
        self._was_connected = False
        return False

    def ensure_connection(self) -> bool:
        if self._ib is not None and self._ib.isConnected():
            return True
        return self.connect_ib()

    def close(self) -> None:
        if self._ib is not None and self._ib.isConnected():
            self.logger.info("Cerrando conexión IB.")
            self._ib.disconnect()
        if self._was_connected:
            self._notify_ib_disconnected("Conexión cerrada por apagado del bot")
        self._was_connected = False

    # -----------------------------
    # Estado / dedupe
    # -----------------------------
    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {"last_signal_id": "", "last_order_id": None}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"last_signal_id": "", "last_order_id": None}

    def _save_state(self, data: Dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _signal_already_processed(self, signal_id: str) -> bool:
        state = self._load_state()
        return str(state.get("last_signal_id", "")) == signal_id

    def _record_processed_signal(self, signal_id: str, order_id: Optional[int]) -> None:
        self._save_state({"last_signal_id": signal_id, "last_order_id": order_id})

    # -----------------------------
    # Helpers IB + reglas de posición
    # -----------------------------
    def _build_contract(self):
        return Stock(self.symbol, self.exchange, self.currency)

    @staticmethod
    def _normalizar_fecha_barra(raw_date: Any) -> datetime:
        if isinstance(raw_date, datetime):
            dt = raw_date
        elif hasattr(raw_date, "year") and hasattr(raw_date, "month") and hasattr(raw_date, "day"):
            dt = datetime(int(raw_date.year), int(raw_date.month), int(raw_date.day))
        else:
            text = str(raw_date).strip()
            dt = datetime.strptime(text[:8], "%Y%m%d")

        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)

    def obtener_barras_historicas(
        self,
        symbol: str,
        duration_str: str = "420 D",
        bar_size_setting: str = "1 day",
        what_to_show: str = "TRADES",
        use_rth: bool = True,
        exchange: Optional[str] = None,
        currency: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if IB is None or Stock is None:
            raise RuntimeError("Falta instalar ib_insync para descargar datos desde IB Gateway")

        if not self.ensure_connection() or self._ib is None:
            raise RuntimeError("No hay conexión con IB Gateway para descargar datos")

        contrato = Stock(symbol, exchange or self.exchange, currency or self.currency)
        self._ib.qualifyContracts(contrato)
        barras = self._ib.reqHistoricalData(
            contrato,
            endDateTime="",
            durationStr=duration_str,
            barSizeSetting=bar_size_setting,
            whatToShow=what_to_show,
            useRTH=use_rth,
            formatDate=1,
        )

        resultado: List[Dict[str, Any]] = []
        for barra in barras:
            resultado.append(
                {
                    "date": self._normalizar_fecha_barra(getattr(barra, "date", None)),
                    "open": float(getattr(barra, "open", 0.0) or 0.0),
                    "high": float(getattr(barra, "high", 0.0) or 0.0),
                    "low": float(getattr(barra, "low", 0.0) or 0.0),
                    "close": float(getattr(barra, "close", 0.0) or 0.0),
                }
            )
        return resultado

    def _position_for_symbol(self, ib: IB) -> Tuple[int, Optional[float]]:
        pos = 0
        avg_cost: Optional[float] = None
        for p in ib.positions():
            contract = getattr(p, "contract", None)
            if contract is None:
                continue
            if getattr(contract, "symbol", "") == self.symbol:
                pos += int(p.position)
                avg_raw = getattr(p, "avgCost", None)
                if avg_raw is not None:
                    try:
                        avg_cost = float(avg_raw)
                    except (TypeError, ValueError):
                        avg_cost = None
        return pos, avg_cost

    def _already_open_order_ref(self, ib: IB, signal_id: str) -> bool:
        for trade in ib.trades():
            order = getattr(trade, "order", None)
            if order is None:
                continue
            if getattr(order, "orderRef", "") == signal_id:
                status = getattr(getattr(trade, "orderStatus", None), "status", "")
                if status not in {"Cancelled", "Inactive", "Filled"}:
                    return True
        return False

    def _quantity_from_signal(self, signal: Any, current_position: int) -> int:
        qty = int(signal.unidades)
        if signal.tipo == "EXIT_LONG":
            return max(0, min(qty, max(0, current_position)))
        if signal.tipo == "EXIT_SHORT":
            return max(0, min(qty, abs(min(0, current_position))))
        return max(0, qty)

    def _position_gate(self, signal: Any, current_position: int) -> Optional[str]:
        if signal.tipo == "ENTRY_LONG" and current_position > 0:
            return "Ya existe posición long abierta"
        if signal.tipo == "ENTRY_SHORT" and current_position < 0:
            return "Ya existe posición short abierta"
        if signal.tipo == "EXIT_LONG" and current_position <= 0:
            return "No hay posición long para cerrar"
        if signal.tipo == "EXIT_SHORT" and current_position >= 0:
            return "No hay posición short para cerrar"
        return None

    # -----------------------------
    # Telegram
    # -----------------------------
    def _enviar_alerta_telegram(self, mensaje: str) -> None:
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return
        text = quote_plus(mensaje)
        url = (
            f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            f"?chat_id={self.telegram_chat_id}&text={text}"
        )
        with urlopen(url, timeout=6) as response:
            _ = response.read()

    def _tipo_evento(self, signal: Any) -> str:
        if str(signal.tipo).startswith("ENTRY_"):
            return "APERTURA"
        if str(signal.tipo).startswith("EXIT_"):
            return "CIERRE"
        return "OPERACION"

    def _lado_desde_signal(self, signal: Any) -> str:
        if str(signal.tipo).endswith("LONG"):
            return "LONG"
        if str(signal.tipo).endswith("SHORT"):
            return "SHORT"
        return "N/A"

    def _obtener_precio_fill(self, trade: Any) -> Optional[float]:
        fills = getattr(trade, "fills", []) or []
        total_qty = 0.0
        total_cost = 0.0
        for fill in fills:
            execution = getattr(fill, "execution", None)
            if execution is None:
                continue
            try:
                shares = float(getattr(execution, "shares", 0.0) or 0.0)
                price = float(getattr(execution, "price", 0.0) or 0.0)
            except (TypeError, ValueError):
                continue
            if shares > 0 and price > 0:
                total_qty += shares
                total_cost += shares * price
        if total_qty <= 0:
            return None
        return total_cost / total_qty

    def _calcular_pnl_cierre(
        self,
        signal: Any,
        qty: int,
        precio_fill: Optional[float],
        avg_cost: Optional[float],
    ) -> Optional[float]:
        if precio_fill is None or avg_cost is None:
            return None
        if signal.tipo == "EXIT_LONG":
            return (precio_fill - avg_cost) * qty
        if signal.tipo == "EXIT_SHORT":
            return (avg_cost - precio_fill) * qty
        return None

    def _notificar_operacion(self, signal: Any, qty: int, estado_orden_ib: str, precio: Optional[float], pnl_cierre: Optional[float]) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lado = self._lado_desde_signal(signal)
        if str(signal.tipo).startswith("ENTRY_"):
            mensaje = (
                "🤖 BOT PAPER - APERTURA\n"
                f"Activo: {self.symbol}\n"
                f"Lado: {lado}\n"
                f"Cantidad: {qty}\n"
                f"Estado IB: {estado_orden_ib}"
            )
            if precio is not None:
                mensaje += f"\nPrecio: {precio:.4f}"
            mensaje += (
                f"\nHora: {timestamp}\n"
                f"Señal: {signal.signal_id}"
            )
        else:
            mensaje = (
                "🤖 BOT PAPER - CIERRE\n"
                f"Activo: {self.symbol}\n"
                f"Lado: {lado}\n"
                f"Cantidad: {qty}\n"
                f"Estado IB: {estado_orden_ib}"
            )
            if precio is not None:
                mensaje += f"\nPrecio: {precio:.4f}"
            if pnl_cierre is not None:
                mensaje += f"\nPnL: {pnl_cierre:.2f} USD"
            mensaje += (
                f"\nHora: {timestamp}\n"
                f"Motivo: {getattr(signal, 'motivo', 'N/D')}"
            )
        try:
            self._enviar_alerta_telegram(mensaje)
        except Exception as exc:
            self.logger.warning("No se pudo enviar alerta Telegram: %s", exc)

    def _notificar_orden_fallida(
        self,
        signal: Any,
        qty: int,
        estado_ib: str,
        motivo: str,
    ) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        lado = self._lado_desde_signal(signal)
        mensaje = (
            "⚠️ BOT PAPER - ORDEN FALLIDA\n"
            f"Activo: {self.symbol}\n"
            f"Lado: {lado}\n"
            f"Cantidad: {qty}\n"
            f"Estado IB: {estado_ib}\n"
            f"Motivo: {motivo}\n"
            f"Hora: {timestamp}"
        )
        try:
            self._enviar_alerta_telegram(mensaje)
        except Exception as exc:
            self.logger.warning("No se pudo enviar alerta Telegram: %s", exc)

    def _notify_ib_disconnected(self, detalle: str) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        mensaje = (
            "⚠️ BOT PAPER - IB DESCONECTADO\n"
            f"Hora: {timestamp}\n"
            f"Detalle: {detalle}"
        )
        try:
            self._enviar_alerta_telegram(mensaje)
        except Exception as exc:
            self.logger.warning("No se pudo enviar alerta Telegram: %s", exc)

    def _notify_ib_reconnected(self) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        mensaje = (
            "✅ BOT PAPER - IB RECONECTADO\n"
            f"Hora: {timestamp}\n"
            f"Host: {self.host}\n"
            f"Puerto: {self.port}\n"
            f"ClientId: {self.client_id}"
        )
        try:
            self._enviar_alerta_telegram(mensaje)
        except Exception as exc:
            self.logger.warning("No se pudo enviar alerta Telegram: %s", exc)

    def notify_bot_started(self) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        mensaje = (
            "🚀 BOT PAPER - INICIADO\n"
            f"Hora: {timestamp}\n"
            f"Host: {self.host}\n"
            f"Puerto: {self.port}\n"
            f"ClientId: {self.client_id}"
        )
        try:
            self._enviar_alerta_telegram(mensaje)
        except Exception as exc:
            self.logger.warning("No se pudo enviar alerta Telegram: %s", exc)

    def notify_bot_stopped(self, motivo: str) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        mensaje = (
            "🛑 BOT PAPER - DETENIDO\n"
            f"Hora: {timestamp}\n"
            f"Motivo: {motivo}"
        )
        try:
            self._enviar_alerta_telegram(mensaje)
        except Exception as exc:
            self.logger.warning("No se pudo enviar alerta Telegram: %s", exc)

    # -----------------------------
    # Ejecución
    # -----------------------------
    def procesar_senal(self, signal: Optional[Any]) -> Dict[str, Any]:
        if signal is None:
            return asdict(IBSignalResult(estado="sin_senal", detalle="No hay señal operativa en esta ejecución"))

        if IB is None or Stock is None or MarketOrder is None:
            return asdict(
                IBSignalResult(
                    estado="error_dependencia",
                    detalle="Falta instalar ib_insync para conectar con IB Gateway",
                    signal_id=signal.signal_id,
                )
            )

        if self._signal_already_processed(signal.signal_id):
            return asdict(
                IBSignalResult(
                    estado="duplicada",
                    detalle="Señal ya procesada previamente (reconexión/dedupe)",
                    signal_id=signal.signal_id,
                )
            )

        if not self.ensure_connection() or self._ib is None:
            return asdict(
                IBSignalResult(
                    estado="error_conexion",
                    detalle="No hay conexión con IB Gateway tras reintentos",
                    signal_id=signal.signal_id,
                )
            )

        ib = self._ib
        try:
            if self._already_open_order_ref(ib, signal.signal_id):
                return asdict(
                    IBSignalResult(
                        estado="duplicada",
                        detalle="Hay una orden activa con el mismo orderRef",
                        signal_id=signal.signal_id,
                    )
                )

            current_position, avg_cost = self._position_for_symbol(ib)
            blocked = self._position_gate(signal, current_position)
            if blocked:
                return asdict(IBSignalResult(estado="bloqueada", detalle=blocked, signal_id=signal.signal_id))

            qty = self._quantity_from_signal(signal, current_position)
            if qty <= 0:
                return asdict(
                    IBSignalResult(
                        estado="bloqueada",
                        detalle="Cantidad a ejecutar es 0 después del control de posición",
                        signal_id=signal.signal_id,
                    )
                )

            contract = self._build_contract()
            ib.qualifyContracts(contract)

            self.logger.info("Enviando orden a IB: %s %s %s", signal.accion, qty, self.symbol)
            order = MarketOrder(signal.accion, qty)
            order.orderRef = signal.signal_id
            trade = ib.placeOrder(contract, order)
            ib.sleep(1.5)

            order_id = getattr(trade.order, "orderId", None)
            estado_orden_ib = str(getattr(getattr(trade, "orderStatus", None), "status", "") or "DESCONOCIDO")
            estado_envio = "confirmada" if estado_orden_ib == "Filled" else "enviada"
            precio_fill = self._obtener_precio_fill(trade)
            pnl_cierre = self._calcular_pnl_cierre(
                signal=signal,
                qty=qty,
                precio_fill=precio_fill,
                avg_cost=avg_cost,
            )

            if estado_orden_ib in {"Rejected", "Cancelled", "ApiCancelled", "Inactive"}:
                self._record_processed_signal(signal.signal_id, order_id)
                self._notificar_orden_fallida(
                    signal=signal,
                    qty=qty,
                    estado_ib=estado_orden_ib,
                    motivo="Orden rechazada o cancelada por IB",
                )
                return asdict(
                    IBSignalResult(
                        estado="fallida",
                        detalle=f"Orden con estado {estado_orden_ib}",
                        signal_id=signal.signal_id,
                        order_id=order_id,
                    )
                )

            self._record_processed_signal(signal.signal_id, order_id)
            self._notificar_operacion(
                signal=signal,
                qty=qty,
                estado_orden_ib=estado_orden_ib,
                precio=precio_fill,
                pnl_cierre=pnl_cierre,
            )

            self.logger.info("Resultado orden signal_id=%s estado=%s ib_status=%s", signal.signal_id, estado_envio, estado_orden_ib)
            return asdict(
                IBSignalResult(
                    estado=estado_envio,
                    detalle=f"Orden {signal.accion} {qty} {estado_envio} en IB Gateway",
                    signal_id=signal.signal_id,
                    order_id=order_id,
                )
            )
        except Exception as exc:
            self.logger.exception("Error ejecutando señal en IB: %s", exc)
            self._record_processed_signal(signal.signal_id, None)
            self._notificar_orden_fallida(
                signal=signal,
                qty=int(getattr(signal, "unidades", 0) or 0),
                estado_ib="ERROR",
                motivo=str(exc),
            )
            return asdict(
                IBSignalResult(
                    estado="error_ejecucion",
                    detalle=f"Error ejecutando señal: {exc}",
                    signal_id=signal.signal_id,
                )
            )
