"""TradingNode assembly — wires Bybit clients, strategy, and returns a ready-to-run node."""
from __future__ import annotations

from nautilus_trader.adapters.bybit import (
    BybitLiveDataClientFactory,
    BybitLiveExecClientFactory,
)
from nautilus_trader.adapters.bybit.execution import BybitExecutionClient
from nautilus_trader.common.enums import LogColor
from nautilus_trader.core import nautilus_pyo3
from nautilus_trader.core.datetime import ensure_pydatetime_utc
from nautilus_trader.execution.messages import GenerateOrderStatusReports
from nautilus_trader.execution.reports import OrderStatusReport
from nautilus_trader.live.node import TradingNode

from config import ShortStraddleConfig, build_node_config
from strategy import ShortStraddleStrategy


# Monkey-patch to handle Bybit TestNet returning smpGroup as a string instead of i32.
# See README Known Issues and upstream issue #4655.
async def _patched_generate_order_status_reports(
    self: BybitExecutionClient,
    command: GenerateOrderStatusReports,
) -> list[OrderStatusReport]:
    self._log.debug(
        f"Requesting OrderStatusReports "
        f"{repr(command.instrument_id) if command.instrument_id else ''}...",
    )
    pyo3_reports: list[nautilus_pyo3.OrderStatusReport] = []
    reports: list[OrderStatusReport] = []

    try:
        pyo3_instrument_id = None
        if command.instrument_id:
            pyo3_instrument_id = nautilus_pyo3.InstrumentId.from_str(command.instrument_id.value)

        for product_type in self._product_types:
            try:
                response = await self._http_client.request_order_status_reports(
                    account_id=self.pyo3_account_id,
                    product_type=product_type,
                    instrument_id=pyo3_instrument_id,
                    open_only=command.open_only,
                    start=ensure_pydatetime_utc(command.start),
                    end=ensure_pydatetime_utc(command.end),
                )
                pyo3_reports.extend(response)
            except ValueError as e:
                if "invalid type: string" in str(e) and "expected i32" in str(e):
                    self._log.warning(
                        f"Bybit order history for {product_type} returned string smpGroup "
                        f"(known upstream issue #4655). Skipping order history reconciliation.",
                        LogColor.YELLOW,
                    )
                else:
                    raise

        for pyo3_report in pyo3_reports:
            report = OrderStatusReport.from_pyo3(pyo3_report)
            self._cache_reconciliation_order_position_id(report)
            self._log.debug(f"Received {report}", LogColor.MAGENTA)
            reports.append(report)

    except ValueError as e:
        if "request canceled" in str(e).lower():
            self._log.debug("OrderStatusReports request cancelled during shutdown")
        elif "symbol` must be initialized" in str(e):
            self._log.warning(
                "Order history contains instruments not in cache — expected for uncached symbols.",
                LogColor.YELLOW,
            )
        elif "invalid type: string" in str(e) and "expected i32" in str(e):
            self._log.warning(
                "Bybit order history smpGroup schema mismatch (issue #4655) — skipping.",
                LogColor.YELLOW,
            )
        else:
            self._log.exception("Failed to generate OrderStatusReports", e)
    except Exception as e:
        self._log.exception("Failed to generate OrderStatusReports", e)

    self._log_report_receipt(len(reports), "OrderStatusReport", command.log_receipt_level)
    return reports


BybitExecutionClient.generate_order_status_reports = _patched_generate_order_status_reports


def build_node(api_key: str, api_secret: str) -> TradingNode:
    """Assemble, build, and return the TradingNode."""
    node = TradingNode(config=build_node_config(api_key, api_secret))
    node.add_data_client_factory("BYBIT", BybitLiveDataClientFactory)
    node.add_exec_client_factory("BYBIT", BybitLiveExecClientFactory)
    node.trader.add_strategy(ShortStraddleStrategy(config=ShortStraddleConfig()))
    node.build()
    return node
