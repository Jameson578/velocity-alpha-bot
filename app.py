import os
import time
import logging
import threading
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from flask import Flask

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Velocity Dynamic Multi-Asset Matrix Engine: ONLINE", 200

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("VelocityEngine")

# Authenticate Keys
API_KEY = os.environ.get("ALPACA_API_KEY", "YOUR_API_KEY_HERE")
SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "YOUR_SECRET_KEY_HERE")

# Configured for Alpaca Paper Trading Sandbox Environment
BASE_URL = "https://alpaca.markets"
DATA_URL = "https://alpaca.markets"

# Strategy Parameters - Mirrored exactly from your Colab operational control center
INITIAL_CASH = 500.00
MARGIN_LEVERAGE = 1.5
ATR_PROFIT_MULT = 2.5
ATR_STOP_MULT = 2.5

# Portfolio Asset Allocation Targets
strategy_config = {
    "BTCUSD": {"entry_goal": 76895.85, "allocation_pct": 0.30, "step": 4},
    "ETHUSD": {"entry_goal": 2497.96, "allocation_pct": 0.30, "step": 4},
    "SOLUSD": {"entry_goal": 100.39, "allocation_pct": 0.30, "step": 2}
}

# Live Shared Matrix tracking structures
portfolio_positions = {
    "BTCUSD": {"holding": False, "buy_price": 0.0, "qty": 0.0, "highest_high": 0.0},
    "ETHUSD": {"holding": False, "buy_price": 0.0, "qty": 0.0, "highest_high": 0.0},
    "SOLUSD": {"holding": False, "buy_price": 0.0, "qty": 0.0, "highest_high": 0.0}
}

def make_alpaca_request(url, method="GET", payload=None):
    try:
        req = urllib.request.Request(url, method=method)
        req.add_header("APCA-API-KEY-ID", API_KEY)
        req.add_header("APCA-API-SECRET-KEY", SECRET_KEY)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "Mozilla/5.0")
        
        data = json.dumps(payload).encode('utf-8') if payload else None
        with urllib.request.urlopen(req, data=data, timeout=10) as response:
            if response.status == 204:
                return []
            res_data = response.read().decode('utf-8')
            if not res_data or res_data.strip() == "":
                return [] if "positions" in url or "orders" in url else {}
            return json.loads(res_data)
    except urllib.error.HTTPError as e:
        logger.error(f"❌ Alpaca API returned HTTP Status {e.code}")
        return None
    except Exception as e:
        logger.error(f"Network request failure: {e}")
        return None

def sync_account_matrix():
    """Syncs positions with Alpaca ledger to get true current state metrics"""
    account_url = f"{BASE_URL}/v2/account"
    account_data = make_alpaca_request(account_url)
    cash_wallet = INITIAL_CASH
    if account_data and "cash" in account_data:
        cash_wallet = float(account_data["cash"])

    positions_url = f"{BASE_URL}/v2/positions"
    positions = make_alpaca_request(positions_url)
    
    active_symbols = []
    if isinstance(positions, list):
        active_symbols = [p['symbol'] for p in positions if isinstance(p, dict) and 'symbol' in p]
        
    for symbol in strategy_config.keys():
        if symbol in active_symbols:
            pos = next(p for p in positions if p.get('symbol') == symbol)
            portfolio_positions[symbol]["holding"] = True
            portfolio_positions[symbol]["qty"] = float(pos['qty'])
            portfolio_positions[symbol]["buy_price"] = float(pos['avg_entry_price'])
            portfolio_positions[symbol]["highest_high"] = max(portfolio_positions[symbol]["highest_high"], float(pos['current_price']))
        else:
            portfolio_positions[symbol]["holding"] = False
            portfolio_positions[symbol]["buy_price"] = 0.0
            portfolio_positions[symbol]["qty"] = 0.0
            portfolio_positions[symbol]["highest_high"] = 0.0
            
    return cash_wallet

def native_indicators(symbol):
    try:
        now_dt = datetime.now(timezone.utc)
        start_str = (now_dt - timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%SZ')
        end_str = now_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        url = f"{DATA_URL}?symbols={symbol}&timeframe=15Min&start={start_str}&end={end_str}"
        data = make_alpaca_request(url)
        
        if not data or 'bars' not in data or symbol not in data['bars'] or not data['bars'][symbol]:
            return None, None, None, None, None
            
        bars = data['bars'][symbol]
        closes = [float(b['c']) for b in bars]
        highs = [float(b['h']) for b in bars]
        lows = [float(b['l']) for b in bars]
        
        if len(closes) < 20:
            return closes[-1], highs[-1], lows[-1], closes[-1], 1.0
            
        current_close = closes[-1]
        current_high = highs[-1]
        current_low = lows[-1]
        
        # Fast EMA 20
        ema = closes[0]
        k = 2 / (20 + 1)
        for price in closes[1:]:
            ema = (price * k) + (ema * (1 - k))
            
        # True Range (TR) & Average True Range (ATR)
        tr_elements = []
        for i in range(1, len(closes)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i-1])
            lc = abs(lows[i] - closes[i-1])
            tr_elements.append(max(hl, hc, lc))
        atr = sum(tr_elements[-20:]) / 20 if len(tr_elements) >= 20 else sum(tr_elements) / len(tr_elements)
        
        return current_close, current_high, current_low, ema, atr
    except Exception as e:
        logger.error(f"Error compiling indicators for {symbol}: {e}")
        return None, None, None, None, None

def run_trading_cycle():
    live_timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    logger.info(f"⏱   Scan Event Matrix Initiated: {live_timestamp}")
    
    sim_cash = sync_account_matrix()
    total_open_pnl = 0.0
    
    # Pre-calculate portfolio metrics loop
    for symbol in strategy_config.keys():
        pos = portfolio_positions[symbol]
        if pos["holding"]:
            price, _, _, _, _ = native_indicators(symbol)
            if price:
                total_open_pnl += (pos["qty"] * (price - pos["buy_price"]))
                
    net_pool_equity = sim_cash + total_open_pnl

    for symbol, config in strategy_config.items():
        current_price, current_high, current_low, current_ema, current_atr = native_indicators(symbol)
        if current_price is None:
            continue
            
        pos = portfolio_positions[symbol]
        open_pnl = (pos["qty"] * (current_price - pos["buy_price"])) if pos["holding"] else 0.0
        
        logger.info(f" > [{symbol}] Market: ${current_price:,.2f} | Entry Goal: ${config['entry_goal']:,.2f} | Asset PnL: ${open_pnl:+.2f}")
        
        # BUY ENTRY ROUTING
        if not pos["holding"]:
            if current_price <= config["entry_goal"] and current_price > current_ema:
                # Allocation calculations matching Colab risk matrix logic
                target_allocation = net_pool_equity * config["allocation_pct"]
                raw_qty = (target_allocation * MARGIN_LEVERAGE) / current_price
                target_qty = round(raw_qty, config["step"])
                
                if target_qty > 0:
                    logger.info(f"🚀  [VIRTUAL MARKET ENTRY ORDER EXECUTED] -> Buying {target_qty} units of {symbol}")
                    url = f"{BASE_URL}/v2/orders"
                    payload = {"symbol": symbol, "qty": str(target_qty), "side": "buy", "type": "market", "time_in_force": "gtc"}
                    make_alpaca_request(url, method="POST", payload=payload)
                    
        # RISK MANAGEMENT EXIT ROUTING
        elif pos["holding"]:
            if current_high > pos["highest_high"]:
                pos["highest_high"] = current_high
                
            # Dynamic Stop Matrices matching Colab code parameters
            target_profit_price = pos["buy_price"] + (ATR_PROFIT_MULT * current_atr)
            is_profit_extended = pos["highest_high"] > (pos["buy_price"] + (2.0 * current_atr))
            is_trailing_active = pos["highest_high"] > (pos["buy_price"] + (3.5 * current_atr))
            
            if is_trailing_active:
                target_stop_price = pos["highest_high"] - (1.5 * current_atr)
                reason_code = "TRAILING LOCK"
            elif is_profit_extended:
                target_stop_price = pos["buy_price"]
                reason_code = "BE SHIELD"
            else:
                target_stop_price = pos["buy_price"] - (ATR_STOP_MULT * current_atr)
                reason_code = "HARD STOP"
                
            # Exit Criteria Check
            if current_high >= target_profit_price:
                logger.info(f"🏁  [VIRTUAL LIQUIDATION] -> Event: [{symbol}] VELOCITY PROFIT TARGET")
                url = f"{BASE_URL}/v2/orders"
                payload = {"symbol": symbol, "qty": str(pos["qty"]), "side": "sell", "type": "market", "time_in_force": "gtc"}
                make_alpaca_request(url, method="POST", payload=payload)
            elif current_low <= target_stop_price:
                logger.warning(f"🏁  [VIRTUAL LIQUIDATION] -> Event: [{symbol}] Protective {reason_code} Floor Breached")
                url = f"{BASE_URL}/v2/orders"
                payload = {"symbol": symbol, "qty": str(pos["qty"]), "side": "sell", "type": "market", "time_in_force": "gtc"}
                make_alpaca_request(url, method="POST", payload=payload)

    logger.info(f"📊  Matrix Wallet Cash: ${sim_cash:,.2f} | Net Pool Equity: ${net_pool_equity:,.2f}")

def background_loop():
    # Allow system cluster initialization sync setup buffer time
    time.sleep(5)
    while True:
        try:
            run_trading_cycle()
        except Exception as e:
            logger.error(f"Critical execution error: {e}")
        time.sleep(15)

