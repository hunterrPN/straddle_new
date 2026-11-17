"""Strategy config and TradingNode config builder."""
from __future__ import annotations

from nautilus_trader.adapters.bybit import BybitDataClientConfig, BybitExecClientConfig
from nautilus_trader.config import (
    InstrumentProviderConfig,
    LiveExecEngineConfig,
    LoggingConfig,
    StrategyConfig,
    TradingNodeConfig,
)
from nautilus_trader.core.nautilus_pyo3 import BybitEnvironment, BybitProductType


class ShortStraddleConfig(StrategyConfig, frozen=True):
    """Risk parameters for the short straddle strategy."""
    stop_loss_pct: float = 0.01    # 1%
    take_profit_pct: float = 0.02  # 2%


def build_node_config(api_key: str, api_secret: str) -> TradingNodeConfig:
    """Build TradingNodeConfig for Bybit TestNet with BTC options."""
    instrument_cfg = InstrumentProviderConfig(
        load_all=True,
        filters={"base_coin": "BTC"},
    )
    data_client_cfg = BybitDataClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        # LINEAR is needed for the BTCUSDT index price WebSocket channel.
        product_types=(BybitProductType.OPTION, BybitProductType.LINEAR),
        environment=BybitEnvironment.TESTNET,
        instrument_provider=instrument_cfg,
    )
    exec_client_cfg = BybitExecClientConfig(
        api_key=api_key,
        api_secret=api_secret,
        product_types=(BybitProductType.OPTION,),
        environment=BybitEnvironment.TESTNET,
        instrument_provider=instrument_cfg,
        use_http_batch_api=True,  # workaround for smpGroup WS bug — see README Known Issues
        recv_window_ms=10_000,    # increased from 5000 to tolerate minor clock skew
    )
    return TradingNodeConfig(
        trader_id="TRADER-001",
        logging=LoggingConfig(log_level="INFO"),
        data_clients={"BYBIT": data_client_cfg},
        exec_clients={"BYBIT": exec_client_cfg},
        exec_engine=LiveExecEngineConfig(
            reconciliation=False,  # disabled — REST fallback crashes on smpGroup (issue #4655)
        ),
    )
