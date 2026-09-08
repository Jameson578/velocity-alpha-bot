import os
import time
import logging
import threading
import json
import urllib.request
from flask import Flask

app = Flask(__name__)

@app.route('/')
def health_check():
    return "Velocity Native Engine Status: ONLINE", 200

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("VelocityEngine")

# Authenticate Keys
API_KEY = os.environ.get("ALPACA_API_KEY", "YOUR_API_KEY_HERE")
SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "YOUR_SECRET_KEY_HERE")

BASE_URL = "https://alpaca.markets"
DATA_URL = "https://alpaca.markets"

strategy_config = {
    "BTCUSD": {"entry_goal": 78543.73, "stop_loss_pct": 0.01, "allocation": 24000.0},
    "ETHUSD": {"entry_goal": 2487.56, "stop_loss_pct": 0.01, "allocation": 24000.0},
    "SOLUSD": {"entry_goal": 103.26, "stop_loss_pct": 0.01, "allocation": 24000.0}
}

portfolio_positions = {
    "BTCUSD": {"holding": False, "buy_price": 0.0, "qty": 0.0},
    "ETHUSD": {"holding": False, "buy_price": 0.0, "qty": 0.0},
    "SOLUSD": {"holding": False, "buy_price": 0.0, "qty": 0.0}
}

def make_alpaca_request(url, method="GET", payload=None):
    """Refactored request block explicitly verifying server response codes"""
    try:
        req = urllib.request.Request(url, method=method)
        req.add_header("APCA-API-KEY-ID", API_KEY)
        req.add_header("APCA-API-SECRET-KEY", SECRET_KEY)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "Mozilla/5.0")
        
        data = json.dumps(payload).encode('utf-8') if payload else None
        with urllib.request.urlopen(req, data=data, timeout=10) as response:
            # FIX: If Alpaca returns a 204 status, return an empty array instead of parsing nothing
            if response.status == 204:
                return []
                
            res_data = response.read().decode('utf-8')
            if not res_data or res_data.strip() == "":
                return [] if method == "GET" and "positions" in url else {}
            return json.loads(res_data)
    except urllib.error.HTTPError as http_err:
        # Handles 204 edge-cases if thrown directly as an exception object downstream
        if http_err.code == 204:
            return []
        logger.error(f"Alpaca API Server returned HTTP Error {http_err.code}")
        return None
    except Exception as e:
        logger.error(f"Network transport level tracking anomaly: {e}")
        return None

def native_indicators(symbol):
    try:
        url = f"{DATA_URL}?symbols={symbol}&timeframe=1Min&limit=100"
        data = make_alpaca_request(url)
        
        if not data or 'bars' not in data or symbol not in data['bars'] or not data['bars'][symbol]:
            logger.warning(f"⚠️ Price metrics warming up for {symbol}. Synching to active ticker chart...")
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
        for i in range(1, 15):
            change = closes[i] - closes[i-1]
            gains.append(change if change > 0 else 0.0)
            losses.append(-change if change < 0 else 0.0)
            
        avg_gain = sum(gains) / 14
        avg_loss = sum(losses) / 14
        
        for i in range(15, len(closes)):
            change = closes[i] - closes[i-1]
            gain = change if change > 0 else 0.0
            loss = -change if change < 0 else 0.0
            avg_gain = (avg_gain * 13 + gain) / 14
            avg_loss = (avg_loss * 13 + loss) / 14
            
        rs = avg_gain / avg_loss if avg_loss != 0 else 1e-10
        rsi = 100.0 - (100.0 / (1.0 + rs))
        
        return current_price, ema, rsi
    except Exception as e:
        logger.error(f"Failed indicator generation for {symbol}: {e}")
        return None, None, None

def sync_positions():
    url = f"{BASE_URL}/v2/positions"
    positions = make_alpaca_request(url)
    if positions is None: 
        return
        
    active_symbols = [p['symbol'] for p in positions if isinstance(p, dict) and 'symbol' in p]
    for symbol in strategy_config.keys():
        if symbol in active_symbols:
            pos = next(p for p in positions if p.get('symbol') == symbol)
            portfolio_positions[symbol]["holding"] = True
            portfolio_positions[symbol]["qty"] = float(pos['qty'])
            if portfolio_positions[symbol]["buy_price"] == 0.0:
                portfolio_positions[symbol]["buy_price"] = float(pos['avg_entry_price'])
        else:
            portfolio_positions[symbol]["holding"] = False
            portfolio_positions[symbol]["buy_price"] = 0.0
            portfolio_positions[symbol]["qty"] = 0.0

def run_trading_cycle():
    logger.info("⏱️ Scan Event Matrix Initiated...")
    sync_positions()
    
    for symbol, config in strategy_config.items():
        price, ema, rsi = native_indicators(symbol)
        if price is None: 
            continue
        
        position = portfolio_positions[symbol]
        logger.info(f" > [{symbol}] Market: ${price:,.2f} | EMA50: ${ema:,.2f} | RSI14: {rsi:.1f} | Holding: {position['holding']}")
        
        if not position["holding"]:
            if price <= config["entry_goal"] and price > ema and rsi < 65:
                target_qty = config["allocation"] / price
                logger.info(f"🚀 [TREND ENGINE MATCH] Transmitting BUY order for {symbol}: {target_qty:.4f} units")
                url = f"{BASE_URL}/v2/orders"
                payload = {"symbol": symbol, "qty": str(round(target_qty, 4)), "side": "buy", "type": "market", "time_in_force": "gtc"}
                make_alpaca_request(url, method="POST", payload=payload)
                
        elif position["holding"]:
            hard_stop_floor = position["buy_price"] * (1.0 - config["stop_loss_pct"])
            if price <= hard_stop_floor:
                logger.warning(f"🏁 [HARD STOP BREACH] Liquidating open positions for {symbol}")
                url = f"{BASE_URL}/v2/orders"
                payload = {"symbol": symbol, "qty": str(position["qty"]), "side": "sell", "type": "market", "time_in_force": "gtc"}
                make_alpaca_request(url, method="POST", payload=payload)

def background_loop():
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
