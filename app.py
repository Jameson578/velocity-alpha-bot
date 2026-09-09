import os
import time
import logging
import threading
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from flask import Flask

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Velocity Alpha Monolith Engine: ONLINE", 200

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("VelocityEngine")

# Authenticate Keys
API_KEY = os.environ.get("ALPACA_API_KEY", "YOUR_API_KEY_HERE")
SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "YOUR_SECRET_KEY_HERE")

BASE_URL = "https://alpaca.markets"
DATA_URL = "https://alpaca.markets"

# Strategy Parameters
strategy_config = {
    "BTCUSD": {"entry_goal": 78543.73, "stop_loss_pct": 0.01, "take_profit_pct": 0.03, "allocation": 24000.0, "step": 4},
    "ETHUSD": {"entry_goal": 2487.56, "stop_loss_pct": 0.01, "take_profit_pct": 0.03, "allocation": 24000.0, "step": 4},
    "SOLUSD": {"entry_goal": 103.26, "stop_loss_pct": 0.01, "take_profit_pct": 0.03, "allocation": 24000.0, "step": 2}
}

# Tracking states equipped with highest_high memories & cool-down clocks
portfolio_positions = {
    "BTCUSD": {"holding": False, "buy_price": 0.0, "qty": 0.0, "highest_high": 0.0, "cool_down_until": None},
    "ETHUSD": {"holding": False, "buy_price": 0.0, "qty": 0.0, "highest_high": 0.0, "cool_down_until": None},
    "SOLUSD": {"holding": False, "buy_price": 0.0, "qty": 0.0, "highest_high": 0.0, "cool_down_until": None}
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
    except Exception as e:
        return None

# UPGRADE 4: Automated Order and Stale Position Purge on Boot Up
def cancel_all_open_orders():
    """Cancels floating or unexecuted orders at startup to clear the ledger"""
    logger.info("🧹 Sweeping ledger... Checking for open orders to cancel.")
    url = f"{BASE_URL}/v2/orders"
    open_orders = make_alpaca_request(url)
    
    if open_orders and isinstance(open_orders, list) and len(open_orders) > 0:
        logger.warning(f"⚠️ Found {len(open_orders)} open orders. Sending cancel commands.")
        make_alpaca_request(url, method="DELETE")
        time.sleep(2) # Allow exchange system to process cancellations
    else:
        logger.info("✅ Ledger clear. No floating orders found.")

def native_indicators(symbol):
    try:
        now_dt = datetime.now(timezone.utc)
        start_str = (now_dt - timedelta(hours=4)).strftime('%Y-%m-%dT%H:%M:%SZ')
        end_str = now_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
        
        url = f"{DATA_URL}?symbols={symbol}&timeframe=1Min&start={start_str}&end={end_str}"
        data = make_alpaca_request(url)
        
        if not data or 'bars' not in data or symbol not in data['bars'] or not data['bars'][symbol]:
            return None, None, None
            
        bars = data['bars'][symbol]
        closes = [float(b['c']) for b in bars]
        if len(closes) < 50:
            return closes[-1], closes[-1], 50.0
            
        current_price = closes[-1]
        
        # EMA 50
        ema = closes[0]
        k = 2 / (50 + 1)
        for price in closes[1:]:
            ema = (price * k) + (ema * (1 - k))
            
        # RSI 14
        gains, losses = [], []
        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            gains.append(change if change > 0 else 0.0)
            losses.append(-change if change < 0 else 0.0)
            
        avg_gain = sum(gains[:14]) / 14
        avg_loss = sum(losses[:14]) / 14
        for i in range(14, len(gains)):
            avg_gain = (avg_gain * 13 + gains[i]) / 14
            avg_loss = (avg_loss * 13 + losses[i]) / 14
            
        rs = avg_gain / avg_loss if avg_loss != 0 else 1e-10
        rsi = 100.0 - (100.0 / (1.0 + rs))
        
        return current_price, ema, rsi
    except Exception as e:
        return None, None, None

def sync_positions():
    url = f"{BASE_URL}/v2/positions"
    positions = make_alpaca_request(url)
    if positions is None: 
        return
        
    active_symbols = []
    if isinstance(positions, list):
        active_symbols = [p['symbol'] for p in positions if isinstance(p, dict) and 'symbol' in p]
        
    for symbol in strategy_config.keys():
        if symbol in active_symbols:
            pos = next(p for p in positions if p.get('symbol') == symbol)
            portfolio_positions[symbol]["holding"] = True
            portfolio_positions[symbol]["qty"] = float(pos['qty'])
            if portfolio_positions[symbol]["buy_price"] == 0.0:
                portfolio_positions[symbol]["buy_price"] = float(pos['avg_entry_price'])
                portfolio_positions[symbol]["highest_high"] = max(portfolio_positions[symbol]["highest_high"], float(pos['current_price']))
        else:
            portfolio_positions[symbol]["holding"] = False
            portfolio_positions[symbol]["buy_price"] = 0.0
            portfolio_positions[symbol]["qty"] = 0.0
            portfolio_positions[symbol]["highest_high"] = 0.0

def run_trading_cycle():
    logger.info("⏱️ Scan Event Matrix Initiated...")
    sync_positions()
    now = datetime.now(timezone.utc)
    
    for symbol, config in strategy_config.items():
        price, ema, rsi = native_indicators(symbol)
        if price is None: 
            continue
        
        position = portfolio_positions[symbol]
        
        # UPGRADE 1: Cool-Down Guard Check
        in_cool_down = False
        if position["cool_down_until"] and now < position["cool_down_until"]:
            in_cool_down = True
            remaining = (position["cool_down_until"] - now).total_seconds() / 60
            logger.info(f" > [{symbol}] Market: ${price:,.2f} | ❄️ COOL-DOWN ACTIVE ({remaining:.1f} mins remaining) | Holding: {position['holding']}")
        else:
            logger.info(f" > [{symbol}] Market: ${price:,.2f} | EMA50: ${ema:,.2f} | RSI14: {rsi:.1f} | Holding: {position['holding']}")
        
        # RULE 1: SAFE BUY ENTRY
        if not position["holding"] and not in_cool_down:
            if price <= config["entry_goal"] and price > ema and rsi < 65:
                # UPGRADE 2: Lot Sizing & Fractional Precision Engine
                raw_qty = config["allocation"] / price
                target_qty = round(raw_qty, config["step"])
                
                logger.info(f"🚀 [TREND ENGINE MATCH] Transmitting BUY order for {symbol}: {target_qty} units")
                url = f"{BASE_URL}/v2/orders"
                payload = {"symbol": symbol, "qty": str(target_qty), "side": "buy", "type": "market", "time_in_force": "gtc"}
                make_alpaca_request(url, method="POST", payload=payload)
                
                position["holding"] = True
                position["buy_price"] = price
                position["highest_high"] = price
                
        # RULE 2: DUAL EXIT AND TRAILING STOP-LOSS GATEWAY
        elif position["holding"]:
            # UPGRADE 3: Update trailing stop high watermark memory
            if price > position["highest_high"]:
                position["highest_high"] = price
                
            # Trailing stop floor tracks beneath your highest peak price, NOT your entry price
            trailing_stop_floor = position["highest_high"] * (1.0 - config["stop_loss_pct"])
            profit_target_ceiling = position["buy_price"] * (1.0 + config["take_profit_pct"])
            
            # Upside Exit Check
            if price >= profit_target_ceiling:
                logger.info(f"💰 [TAKE PROFIT MATCH] Target hit for {symbol}! Liquidating at a 3% profit.")
                url = f"{BASE_URL}/v2/orders"
                payload = {"symbol": symbol, "qty": str(position["qty"]), "side": "sell", "type": "market", "time_in_force": "gtc"}
                make_alpaca_request(url, method="POST", payload=payload)
                # Activate 2-hour safety cool-down
                position["cool_down_until"] = now + timedelta(hours=2)
            
            # Downside Exit Check (Now incorporates dynamic Trailing Stops)
            elif price <= trailing_stop_floor:
                reason = "TRAILING STOP LOCK" if position["highest_high"] > position["buy_price"] else "HARD STOP LOSS"
                logger.warning(f"🏁 [{reason} BREACH] Protective boundary triggered on {symbol}. Liquidating portfolio.")
                url = f"{BASE_URL}/v2/orders"
                payload = {"symbol": symbol, "qty": str(position["qty"]), "side": "sell", "type": "market", "time_in_force": "gtc"}
                make_alpaca_request(url, method="POST", payload=payload)
                # Activate 2-hour safety cool-down
                position["cool_down_until"] = now + timedelta(hours=2)

def background_loop():
    # Run the open order purge cleanly once right when the server initializes
    cancel_all_open_orders()
    while True:
        try: 
            run_trading_cycle()
        except Exception as e: 
            logger.error(f"Critical execution error: {e}")
        time.sleep(15)

trading_thread = threading.Thread(target=background_loop, daemon=True)
trading_thread.start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
