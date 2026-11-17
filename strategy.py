"""Event-driven strategy for a BTC ATM short straddle on Bybit TestNet."""
from __future__ import annotations

from decimal import Decimal

from nautilus_trader.common.enums import LogColor
from nautilus_trader.model.data import IndexPriceUpdate, QuoteTick
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.events.order import (
    OrderAccepted,
    OrderExpired,
    OrderFilled,
    OrderRejected,
)
from nautilus_trader.model.events.position import (
    PositionChanged,
    PositionClosed,
    PositionOpened,
)
from nautilus_trader.model.identifiers import ClientOrderId, InstrumentId, Venue
from nautilus_trader.model.instruments import CryptoOption
from nautilus_trader.trading.strategy import Strategy

from atm_selector import select_atm_straddle
from config import ShortStraddleConfig
from risk_manager import check_exit_condition


class ShortStraddleStrategy(Strategy):
    """BTC ATM short straddle — Level 1 entry + Level 2 automated SL/TP exit."""

    # Rejection reasons that indicate a permanent failure — retrying is pointless.
    _PERMANENT_REJECTION_REASONS = (
        "Insufficient margin balance",
        "Account is banned",
        "Trading is not allowed",
    )

    def __init__(self, config: ShortStraddleConfig) -> None:
        super().__init__(config)

        self._call_id: InstrumentId | None = None
        self._put_id: InstrumentId | None = None

        # CLOIDs distinguish entry vs exit orders for the same instrument
        # when both are in-flight simultaneously during the exit transition.
        self._call_entry_cloid: ClientOrderId | None = None
        self._put_entry_cloid: ClientOrderId | None = None
        self._call_exit_cloid: ClientOrderId | None = None
        self._put_exit_cloid: ClientOrderId | None = None

        self._orders_submitted: bool = False
        self._call_filled: bool = False
        self._put_filled: bool = False
        self._call_filled_qty: Decimal = Decimal("0")
        self._put_filled_qty: Decimal = Decimal("0")

        # Quantity-weighted entry premium: sum(px * qty) / sum(qty)
        self._entry_total_cost: float = 0.0
        self._entry_total_qty: float = 0.0
        self._entry_premium: float = 0.0

        # _exit_triggered guards on_quote_tick only; does not block exit retries.
        self._exit_triggered: bool = False
        self._call_exit_filled: bool = False
        self._put_exit_filled: bool = False

        # Ask prices updated from live ticks (not cache) to avoid stale cross-leg quotes.
        self._latest_call_ask: float | None = None
        self._latest_put_ask: float | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_start(self) -> None:
        self.subscribe_instruments(venue=Venue("BYBIT"))
        self.subscribe_index_prices(
            instrument_id=InstrumentId.from_str("BTCUSDT-LINEAR.BYBIT")
        )
        self.log.info("Strategy started — waiting for BTC index price tick")

    def on_stop(self) -> None:
        if self._call_id is not None:
            self.cancel_all_orders(self._call_id)
        if self._put_id is not None:
            self.cancel_all_orders(self._put_id)
        if not self._exit_triggered and (self._call_filled or self._put_filled):
            self.log.warning("Stopping with open positions — triggering emergency close")
            self._trigger_exit("EMERGENCY_STOP")
        self.log.info("Strategy stopped")

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def on_index_price(self, index_price: IndexPriceUpdate) -> None:
        """Select ATM straddle and submit entry orders on the first price tick."""
        if self._orders_submitted:
            return

        btc_price = float(index_price.value)
        self.log.info(f"BTC index price: {btc_price:.2f}")

        result = select_atm_straddle(self.cache, self.clock, self.log, btc_price)
        if result is None:
            self.log.warning("ATM selection failed — retrying on next tick")
            return

        call, put = result
        self._call_id = call.id
        self._put_id = put.id
        self._orders_submitted = True  # set before submit to prevent race on fast ticks
        self._submit_straddle(call, put)

    def _submit_straddle(self, call: CryptoOption, put: CryptoOption) -> None:
        """Submit SELL IOC market orders for both legs."""
        try:
            call_qty = call.make_qty(Decimal("0.01"))
            put_qty = put.make_qty(Decimal("0.01"))

            call_order = self.order_factory.market(
                instrument_id=call.id,
                order_side=OrderSide.SELL,
                quantity=call_qty,
                time_in_force=TimeInForce.IOC,
            )
            put_order = self.order_factory.market(
                instrument_id=put.id,
                order_side=OrderSide.SELL,
                quantity=put_qty,
                time_in_force=TimeInForce.IOC,
            )

            # CLOIDs stored before submitting — rejection/expiry handlers need them immediately
            self._call_entry_cloid = call_order.client_order_id
            self._put_entry_cloid = put_order.client_order_id

            self.log.info(f"Submitting SELL IOC {call_qty} CALL: {call.id} [cloid={call_order.client_order_id}]")
            self.submit_order(call_order)
            self.log.info(f"Submitting SELL IOC {put_qty} PUT: {put.id} [cloid={put_order.client_order_id}]")
            self.submit_order(put_order)

        except Exception as exc:
            self.log.error(f"Entry order submission failed: {exc!r}")
            self._orders_submitted = False

    # ------------------------------------------------------------------
    # Order event handlers
    # ------------------------------------------------------------------

    def on_order_accepted(self, event: OrderAccepted) -> None:
        self.log.info(
            f"ORDER ACCEPTED: {event.instrument_id} "
            f"cloid={event.client_order_id} venue_order_id={event.venue_order_id}"
        )

    def on_order_filled(self, event: OrderFilled) -> None:
        self.log.info(
            f"ORDER FILLED: {event.instrument_id} side={event.order_side} "
            f"qty={event.last_qty} px={event.last_px} commission={event.commission}",
            color=LogColor.GREEN,
        )
        if event.order_side == OrderSide.SELL:
            self._handle_entry_fill(event)
        elif event.order_side == OrderSide.BUY:
            self._handle_exit_fill(event)

    def on_order_rejected(self, event: OrderRejected) -> None:
        self.log.error(
            f"ORDER REJECTED: {event.instrument_id} "
            f"cloid={event.client_order_id} reason={event.reason}"
        )
        order_type = self._classify_order(event.client_order_id)
        if order_type in ("CALL_ENTRY", "PUT_ENTRY"):
            leg = "CALL" if order_type == "CALL_ENTRY" else "PUT"
            self.log.error(f"Entry {leg} leg REJECTED (IOC)")
            self._handle_leg_failure(leg, reason=event.reason)
        elif order_type in ("CALL_EXIT", "PUT_EXIT"):
            leg = "CALL" if order_type == "CALL_EXIT" else "PUT"
            self.log.error(f"Exit {leg} leg REJECTED — re-attempting close")
            self._retry_exit_leg(event.instrument_id, leg)

    def on_order_expired(self, event: OrderExpired) -> None:
        """IOC entry: check filled_qty to distinguish partial fill from zero fill."""
        self.log.warning(
            f"ORDER EXPIRED: {event.instrument_id} cloid={event.client_order_id}"
        )
        order_type = self._classify_order(event.client_order_id)
        if order_type in ("CALL_ENTRY", "PUT_ENTRY"):
            leg = "CALL" if order_type == "CALL_ENTRY" else "PUT"
            order = self.cache.order(event.client_order_id)
            filled_qty = float(order.filled_qty) if order is not None else 0.0
            if filled_qty > 0:
                self.log.warning(f"Entry {leg} partially filled ({filled_qty}) then expired")
                if self._call_filled and self._put_filled:
                    self.subscribe_quote_ticks(instrument_id=self._call_id)
                    self.subscribe_quote_ticks(instrument_id=self._put_id)
            else:
                self.log.error(f"Entry {leg} expired with zero fill")
                self._handle_leg_failure(leg, reason=f"ENTRY_{leg}_EXPIRED")
        elif order_type in ("CALL_EXIT", "PUT_EXIT"):
            leg = "CALL" if order_type == "CALL_EXIT" else "PUT"
            self.log.warning(f"Exit {leg} expired — re-attempting close")
            self._retry_exit_leg(event.instrument_id, leg)

    # ------------------------------------------------------------------
    # Level 2 — Quote tick monitoring
    # ------------------------------------------------------------------

    def on_quote_tick(self, tick: QuoteTick) -> None:
        """Check combined ask premium against SL/TP thresholds on every tick."""
        if not (self._call_filled and self._put_filled) or self._exit_triggered:
            return

        if tick.instrument_id == self._call_id:
            self._latest_call_ask = float(tick.ask_price)
        elif tick.instrument_id == self._put_id:
            self._latest_put_ask = float(tick.ask_price)

        if self._latest_call_ask is None or self._latest_put_ask is None:
            return

        total_qty = float(self._call_filled_qty) + float(self._put_filled_qty)
        current_ask_premium = (
            self._latest_call_ask * float(self._call_filled_qty)
            + self._latest_put_ask * float(self._put_filled_qty)
        ) / total_qty

        reason = check_exit_condition(
            entry_premium=self._entry_premium,
            current_ask_premium=current_ask_premium,
            stop_loss_pct=self.config.stop_loss_pct,
            take_profit_pct=self.config.take_profit_pct,
        )

        if reason is not None:
            change_pct = ((current_ask_premium / self._entry_premium) - 1) * 100
            self.log.info(
                f"Exit condition: {reason} | "
                f"entry={self._entry_premium:.4f} "
                f"current={current_ask_premium:.4f} "
                f"change={change_pct:+.2f}%"
            )
            self._trigger_exit(reason)

    # ------------------------------------------------------------------
    # Exit
    # ------------------------------------------------------------------

    def _trigger_exit(self, reason: str) -> None:
        """Set exit guard and submit BUY IOC close orders for all filled legs."""
        self._exit_triggered = True
        self.log.info(f"EXIT TRIGGERED: {reason} — closing positions", color=LogColor.YELLOW)
        self._close_leg(self._call_id, self._call_filled, self._call_filled_qty, "CALL", reason)
        self._close_leg(self._put_id, self._put_filled, self._put_filled_qty, "PUT", reason)

    def _retry_exit_leg(self, instrument_id: InstrumentId, leg_name: str) -> None:
        """Re-submit close order for one leg after a rejection or expiry."""
        is_call = leg_name == "CALL"
        self._close_leg(
            instrument_id,
            self._call_filled if is_call else self._put_filled,
            self._call_filled_qty if is_call else self._put_filled_qty,
            leg_name,
            "RETRY_EXIT",
            is_retry=True,
        )

    def _close_leg(
        self,
        instrument_id: InstrumentId | None,
        is_filled: bool,
        filled_qty: Decimal,
        leg_name: str,
        reason: str,
        is_retry: bool = False,
    ) -> None:
        """Submit a BUY IOC order to close one leg at its actual filled quantity."""
        if not is_filled:
            self.log.warning(f"{leg_name} not filled — no position to close ({reason})")
            return
        if instrument_id is None:
            self.log.error(f"Cannot close {leg_name}: instrument_id is None")
            return
        instrument = self.cache.instrument(instrument_id)
        if instrument is None:
            self.log.error(f"Cannot close {leg_name}: {instrument_id} not in cache")
            return
        try:
            qty = instrument.make_qty(filled_qty)
            order = self.order_factory.market(
                instrument_id=instrument_id,
                order_side=OrderSide.BUY,
                quantity=qty,
                time_in_force=TimeInForce.IOC,
            )
            if leg_name == "CALL":
                self._call_exit_cloid = order.client_order_id
            else:
                self._put_exit_cloid = order.client_order_id
            prefix = "RETRY " if is_retry else ""
            self.log.info(
                f"Submitting {prefix}BUY IOC {qty} {leg_name}: {instrument_id} "
                f"[cloid={order.client_order_id}]"
            )
            self.submit_order(order)
        except Exception as exc:
            self.log.error(f"{leg_name} exit submission failed: {exc!r}")

    # ------------------------------------------------------------------
    # Position event handlers
    # ------------------------------------------------------------------

    def on_position_opened(self, event: PositionOpened) -> None:
        self.log.info(
            f"POSITION OPENED: {event.instrument_id} "
            f"side={event.side} qty={event.quantity} avg_px={event.avg_px_open}",
            color=LogColor.BLUE,
        )

    def on_position_changed(self, event: PositionChanged) -> None:
        self.log.info(
            f"POSITION CHANGED: {event.instrument_id} "
            f"side={event.side} qty={event.quantity} unrealized_pnl={event.unrealized_pnl}",
            color=LogColor.BLUE,
        )

    def on_position_closed(self, event: PositionClosed) -> None:
        self.log.info(
            f"POSITION CLOSED: {event.instrument_id} "
            f"realized_pnl={event.realized_pnl} duration={event.duration_ns}ns",
            color=LogColor.GREEN,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _classify_order(self, cloid: ClientOrderId) -> str | None:
        """Map a CLOID to 'CALL_ENTRY', 'PUT_ENTRY', 'CALL_EXIT', 'PUT_EXIT', or None."""
        if cloid == self._call_entry_cloid:
            return "CALL_ENTRY"
        if cloid == self._put_entry_cloid:
            return "PUT_ENTRY"
        if cloid == self._call_exit_cloid:
            return "CALL_EXIT"
        if cloid == self._put_exit_cloid:
            return "PUT_EXIT"
        return None

    def _handle_entry_fill(self, event: OrderFilled) -> None:
        """Accumulate entry premium; subscribe to quote ticks once both legs are filled."""
        px = float(event.last_px)
        qty = float(event.last_qty)
        self._entry_total_cost += px * qty
        self._entry_total_qty += qty

        if event.instrument_id == self._call_id:
            self._call_filled = True
            self._call_filled_qty = Decimal(str(qty))
        elif event.instrument_id == self._put_id:
            self._put_filled = True
            self._put_filled_qty = Decimal(str(qty))

        if self._call_filled and self._put_filled:
            self._entry_premium = (
                self._entry_total_cost / self._entry_total_qty
                if self._entry_total_qty > 0 else 0.0
            )
            self.log.info(
                f"=== STRADDLE LIVE: CALL={self._call_id} PUT={self._put_id} "
                f"entry_premium={self._entry_premium:.4f} "
                f"SL={self.config.stop_loss_pct * 100:.1f}% "
                f"TP={self.config.take_profit_pct * 100:.1f}% ===",
                color=LogColor.GREEN,
            )
            self.subscribe_quote_ticks(instrument_id=self._call_id)
            self.subscribe_quote_ticks(instrument_id=self._put_id)
            self.log.info("Quote tick monitoring started")

    def _handle_exit_fill(self, event: OrderFilled) -> None:
        """Track exit fills; log when all filled legs are closed."""
        if event.instrument_id == self._call_id:
            self._call_exit_filled = True
            self.log.info(f"CALL EXIT FILLED: px={event.last_px}", color=LogColor.BLUE)
        elif event.instrument_id == self._put_id:
            self._put_exit_filled = True
            self.log.info(f"PUT EXIT FILLED: px={event.last_px}", color=LogColor.BLUE)

        legs_to_close = sum([self._call_filled, self._put_filled])
        legs_closed = sum([self._call_exit_filled, self._put_exit_filled])
        if legs_closed == legs_to_close > 0:
            self.log.info("=== STRADDLE CLOSED ===", color=LogColor.GREEN)

    def _handle_leg_failure(self, failed_leg: str, reason: str) -> None:
        """
        Handle a failed IOC entry leg (zero or partial fill).

        If the other leg is already short, trigger an immediate exit to avoid a naked position.
        If neither leg filled, check if the reason is permanent before allowing a retry.
        """
        other_leg = "PUT" if failed_leg == "CALL" else "CALL"
        other_filled = self._put_filled if failed_leg == "CALL" else self._call_filled

        if other_filled:
            self.log.error(
                f"{failed_leg} failed but {other_leg} is short — buying back to avoid naked position",
                color=LogColor.RED,
            )
            self._trigger_exit(reason=f"LEG_IMBALANCE_{reason}")
            return

        is_permanent = any(p.lower() in reason.lower() for p in self._PERMANENT_REJECTION_REASONS)
        if is_permanent:
            self.log.error(
                f"Permanent rejection ({reason}) — fix the issue and restart.",
                color=LogColor.RED,
            )
            return  # leave _orders_submitted=True to stop retrying

        self.log.warning("Both legs failed (transient) — resetting for retry")
        self._orders_submitted = False
        self._call_filled = False
        self._put_filled = False
        self._call_filled_qty = Decimal("0")
        self._put_filled_qty = Decimal("0")
        self._entry_total_cost = 0.0
        self._entry_total_qty = 0.0
        self._entry_premium = 0.0
        self._call_entry_cloid = None
        self._put_entry_cloid = None
