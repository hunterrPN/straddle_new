# BTC ATM Short Straddle

A systematic options trading strategy built on [NautilusTrader](https://nautilustrader.io) connected to Bybit TestNet. Sells an at-the-money Call and Put on BTC options at the same strike and expiry, then monitors and closes the position automatically based on configurable risk thresholds.

---

## Strategy Overview

A **short straddle** collects premium by selling both sides of the market. The trader profits if BTC stays near the strike price — the combined premium decays as expiry approaches. The position loses money if BTC moves sharply in either direction, since the cost to buy back the options increases.

| Level | What it does |
|---|---|
| **Level 1** | Connect → load instruments → find ATM strike → sell Call + Put |
| **Level 2** | Monitor combined ask premium → auto-close on stop-loss or take-profit |

### Risk parameters (Level 2)

| Parameter | Default | Trigger |
|---|---|---|
| Stop-loss | 1% | Combined ask ≥ entry × 1.01 |
| Take-profit | 2% | Combined ask ≤ entry × 0.98 |

---

## Project Structure

```
straddle/
├── main.py           # Entry point — loads .env, builds node, runs
├── config.py         # ShortStraddleConfig + build_node_config()
├── atm_selector.py   # ATM strike selection (pure function, no strategy state)
├── strategy.py       # ShortStraddleStrategy — all event-driven logic
├── node.py           # TradingNode assembly
└── risk_manager.py   # check_exit_condition() — pure Python, no framework deps
```

---

## Execution Flow

```
1.  main() loads .env → reads API_KEY, API_SECRET

2.  build_node() assembles TradingNode:
    ├── BybitDataClientConfig  (TESTNET, OPTION + LINEAR, load_all BTC)
    └── BybitExecClientConfig  (TESTNET, OPTION, load_all BTC)

3.  node.build() connects clients:
    ├── InstrumentProvider loads all BTC options via HTTP (~824 contracts)
    ├── WebSocket connects to Bybit option + linear streams
    └── ExecEngine starts reconciliation

4.  strategy.on_start():
    ├── subscribe_instruments(BYBIT)
    └── subscribe_index_prices(BTCUSDT-LINEAR.BYBIT)

5.  on_index_price() fires (first tick only):
    ├── select_atm_straddle() scans cache:
    │   ├── Filter CryptoOption instruments, discard expired
    │   ├── Pick nearest expiry
    │   └── Find strike closest to BTC index price
    └── _submit_straddle():
        ├── SELL IOC 0.01 BTC CALL
        └── SELL IOC 0.01 BTC PUT

6.  Order lifecycle (per leg):
    SUBMITTED → ACCEPTED → FILLED
                         ↘ REJECTED / EXPIRED  → _handle_leg_failure()

7.  on_order_filled() (both legs):
    ├── Accumulate quantity-weighted entry premium
    ├── subscribe_quote_ticks(call), subscribe_quote_ticks(put)
    └── Log "STRADDLE LIVE"

8.  on_quote_tick() fires continuously:
    ├── Update latest ask for arriving leg
    ├── Compute combined ask premium (quantity-weighted)
    └── check_exit_condition() → STOP_LOSS | TAKE_PROFIT | None

9.  _trigger_exit():
    ├── BUY IOC call_qty CALL
    └── BUY IOC put_qty PUT

10. on_order_filled() (exit):
    └── Log "STRADDLE CLOSED" when all filled legs are bought back

11. Ctrl-C → on_stop():
    ├── cancel_all_orders() on both legs
    └── Emergency close if positions are still open
```

---

## Strategy Flow Diagram

```
on_start ─► wait for index price ─► on_index_price (ONE time)
                                         │ select ATM call + put
                                         ▼
                                   submit 2 SELL IOC orders
                                         │
              ┌──────────────────────────┼──────────────────────────┐
         both FILLED              one REJECTED/EXPIRED         both failed
              │                          │                          │
   compute entry premium        other leg filled?             reset, retry
   subscribe to quotes          → buy it back                 next tick
              │                   (avoid naked short)
              ▼
   on_quote_tick (many/sec) ─► combined ask vs entry premium
              │  SL or TP hit
              ▼
   _trigger_exit ─► BUY IOC both legs ─► fills ─► "STRADDLE CLOSED"
```

---

## Order Design Decisions

### Entry and exit: IOC (Immediate or Cancel)

Both entry and exit orders use IOC. IOC fills what is available immediately and cancels any remainder — the correct TIF for Bybit options market orders.

**Why not FOK for entry?** FOK (Fill or Kill) would be theoretically cleaner for a straddle — a partial fill on one leg creates a naked short, which is a completely different risk profile. However, Bybit TestNet does not reliably support FOK for options: FOK orders hang without any WebSocket acknowledgement, causing the reconciliation engine to timeout with synthetic `UNKNOWN` rejections (see [Known Issues](#known-issues)). IOC is used in practice, with partial-fill detection in `on_order_expired` as the safety net.

The FOK vs IOC tradeoff is a deliberate design decision documented here for the walkthrough:
- FOK entry = cleaner semantics, unreliable on Bybit TestNet options
- IOC entry = reliable execution, requires explicit partial-fill handling in code

### Entry premium calculation

```
entry_premium = Σ(fill_price × fill_qty) / Σ(fill_qty)
```

Quantity-weighted across all fill events for both legs. Handles the case where Bybit splits a single order into multiple fill events. The combined ask premium at exit is computed on the same weighted basis.

### Stale quote prevention

`on_quote_tick` updates `_latest_call_ask` / `_latest_put_ask` directly from the **arriving tick**, not from `self.cache.quote_tick()`. This prevents the combined premium from being computed with a stale price from the other leg — particularly important in thin option markets where one leg may go minutes without a quote.

### Leg failure handling

If one entry leg is rejected or expires with zero fill:
- Other leg already filled → naked short exists → `_trigger_exit` buys it back immediately
- Neither leg filled → all state reset, retry on next index price tick

Permanent rejection reasons (e.g. `Insufficient margin balance`) stop the retry loop to avoid flooding the venue with doomed orders.

---

## Setup

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) package manager
- Bybit TestNet account with:
  - **Unified Trading Account** (options require UTA — standard accounts cannot trade options)
  - API key with **Read-Write + Derivatives** permissions, no IP restriction
  - At least **1,000 USDT** transferred to the Unified Trading Account (not Funding)

### Install

```bash
uv sync
```

### Configure

Create a `.env` file in the project root:

```env
API_KEY=your_testnet_api_key
API_SECRET=your_testnet_api_secret
```

> **Note:** Keys must be from [testnet.bybit.com](https://testnet.bybit.com), not mainnet. The strategy connects to `BybitEnvironment.TESTNET`.

### Add test funds

1. Log in to [testnet.bybit.com](https://testnet.bybit.com)
2. Assets → **Request Test Coins** → claim USDT
3. Assets → **Transfer** → move USDT from Funding to **Unified Trading**

Without funds in Unified Trading, orders are rejected with `Insufficient margin balance`.

### Run

```bash
uv run python main.py
```

Press `Ctrl+C` to stop. Open orders are cancelled on exit.

---

## Configuration

Risk parameters can be changed without modifying strategy code:

```python
# node.py
ShortStraddleStrategy(config=ShortStraddleConfig(
    stop_loss_pct=0.015,   # 1.5%
    take_profit_pct=0.03,  # 3%
))
```

---

## Known Issues

### NautilusTrader Bybit adapter — `smpGroup` parsing bug (issue #4655)

**What happens:** After submitting option orders, NautilusTrader receives no WebSocket acknowledgement from Bybit TestNet (no `OrderAccepted`, `OrderFilled`, or `OrderExpired` event). The reconciliation engine falls back to polling REST every ~6 seconds. The REST response contains a field `smpGroup` as a string `"0"` instead of an integer, which the adapter's Rust/pyo3 parser cannot handle:

```
Bybit returned string smpGroup when querying order ... (known upstream issue #4655). Returning None.
```

After 5 failed REST retries (~42 seconds), the engine synthesises an `UNKNOWN` rejection for the order.

**Root cause:** Two separate failures compound each other:
1. Bybit TestNet's private WebSocket does not reliably deliver order update events for options (the order is submitted but the fill/rejection callback never arrives)
2. The REST fallback parser crashes on `smpGroup` — a known bug tracked at [nautechsystems/nautilus_trader#4655](https://github.com/nautechsystems/nautilus_trader/issues/4655)

**Status:** Confirmed present in nautilus-trader 1.231.0 (latest at time of writing). The adapter team is aware. The `use_http_batch_api=True` config flag was tested as a workaround — it routes order submission through REST instead of the trade WebSocket — but the same `smpGroup` parsing failure occurs on the response.

**Impact on this implementation:** Orders do reach Bybit (visible in the TestNet UI), but NautilusTrader never receives the fill or rejection confirmation. The strategy's execution logic (ATM selection, order submission, risk management, leg failure handling) is correct and complete — the blocker is entirely within the adapter layer.

**Fix:** Will resolve when issue #4655 is patched in a future nautilus-trader release, or when Bybit TestNet's option order stream stabilises.
---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `nautilus-trader` | ≥1.231.0 | Trading engine + Bybit adapter |
| `python-dotenv` | ≥1.2.4 | Credential loading from `.env` |
