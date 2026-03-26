from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional

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
    def __init__(
        self,
        host: str,
        port: int,
        client_id: int,
        symbol: str,
        exchange: str,
        currency: str,
        state_path: Path,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.client_id = int(client_id)
        self.symbol = symbol
        self.exchange = exchange
        self.currency = currency
        self.state_path = Path(state_path)

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

    def _build_contract(self):
        return Stock(self.symbol, self.exchange, self.currency)

    def _position_for_symbol(self, ib: IB) -> int:
        pos = 0
        for p in ib.positions():
            contract = getattr(p, "contract", None)
            if contract is None:
                continue
            if getattr(contract, "symbol", "") == self.symbol:
                pos += int(p.position)
        return pos

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

        ib = IB()
        try:
            ib.connect(self.host, self.port, clientId=self.client_id, timeout=8)

            if self._already_open_order_ref(ib, signal.signal_id):
                return asdict(
                    IBSignalResult(
                        estado="duplicada",
                        detalle="Hay una orden activa con el mismo orderRef",
                        signal_id=signal.signal_id,
                    )
                )

            current_position = self._position_for_symbol(ib)
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

            order = MarketOrder(signal.accion, qty)
            order.orderRef = signal.signal_id
            trade = ib.placeOrder(contract, order)
            ib.sleep(1.0)

            order_id = getattr(trade.order, "orderId", None)
            self._record_processed_signal(signal.signal_id, order_id)
            return asdict(
                IBSignalResult(
                    estado="enviada",
                    detalle=f"Orden {signal.accion} {qty} enviada a IB Gateway",
                    signal_id=signal.signal_id,
                    order_id=order_id,
                )
            )
        finally:
            if ib.isConnected():
                ib.disconnect()
