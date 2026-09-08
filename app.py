import os
import time
import logging
import pandas as pd
import numpy as np
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, GetOrdersRequest
from alpaca.trading.enums import OrderSide, TimeInForce, QueryOrderStatus
from alpaca.data.live import CryptoDataStream
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame

# 1. Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("VelocityEngine")

# 2. Authenticate Gateway Access
API_KEY = os.environ.get("ALPACA_API_KEY", "YOUR_API_KEY_HERE")
SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "YOUR_SECRET_KEY_HERE")
PAPER = True  

trading_client = TradingClient(api_key=API_KEY, secret_key=SECRET_KEY, paper=PAPER)
data_client = CryptoHistoricalDataClient(api_key=API_KEY, secret_key=SECRET_KEY)

# 3. Target Asset Profiles
strategy_config = {
    "BTCUSD": {"entry_goal": 78543.73, "stop_loss_pct": 0.01, "allocation": 24000.0},
    "ETHUSD": {"entry_goal": 2487.56, "stop_loss_pct": 0.01, "allocation": 24000.0},
    "SOLUSD": {"entry_goal": 103.26, "stop_loss_pct": 0.01, "allocation": 24000.0}
}

# Tracking state storage
portfolio_positions = {
    "BTCUSD": {"holding": False, "buy_price": 0.0, "qty": 0.0},
    "ETHUSD": {"holding": False, "buy_price": 0.0, "qty": 0.0},
    "SOLUSD": {"holding": False, "buy_price": 0.0, "qty": 0.0}
}

def calculate_rsi(prices, period=14):
    if len(prices) <= period:
        return 50.0
    deltas = np.diff(prices)
    seed = deltas[:period]
    up = seed[seed >= 0].sum() / period
    down = -seed[seed < 0].sum() / period
    rs = up / (down if down != 0 else 1e-10)
    
    for i in range(period, len(deltas)):
        delta = deltas[i]
        upval = delta if delta > 0 else 0.0
        downval = -delta if delta < 0 else 0.0
        up = (up * (period - 1) + upval) / period
        down = (down * (period - 1) + downval) / period
        
    rs = up / (down if down != 0 else 1e-10)
    return 100. - 100. / (1. + rs)

def fetch_market_indicators(symbol):
    """Retrieves 100 recent minute bars to compute live indicators"""
    try:
        request_params = CryptoBarsRequest(
            symbol_or_symbols=[symbol],
            timeframe=TimeFrame.Minute,
            limit=100
        )
        bars = data_client.get_crypto_bars(request_params)
        df = bars.df.loc[symbol]
        
        current_price = df["close"].iloc[-1]
        ema_50 = df["close"].ewm(span=50, adjust=False).mean().iloc[-1]
        rsi_14 = calculate_rsi(df["close"].values, period=14)
        
        return current_price, ema_50, rsi_14
    except Exception as e:
        logger.error(f"Error fetching data metrics for {symbol}: {e}")
        return None, None, None

def sync_positions_with_alpaca():
    """Queries live portfolio balances to rebuild tracking states securely"""
    try:
        open_positions = trading_client.get_all_positions()
        active_symbols = [p.symbol for p in open_positions]
        
        for symbol in strategy_config.keys():
            if symbol in active_symbols:
                pos = next(item for item in open_positions if item.symbol == symbol)
                portfolio_positions[symbol]["holding"] = True
                portfolio_positions[symbol]["qty"] = float(pos.qty)
                # Fallback to current price if buy_price was cleared in memory restart
                if portfolio_positions[symbol]["buy_price"] == 0.0:
                    portfolio_positions[symbol]["buy_price"] = float(pos.avg_entry_price)
            else:
                portfolio_positions[symbol]["holding"] = False
                portfolio_positions[symbol]["buy_price"] = 0.0
                portfolio_positions[symbol]["qty"] = 0.0
    except Exception as e:
        logger.error(f"Failed synchronization loop with Alpaca API: {e}")

def run_trading_cycle():
    logger.info("⏱️ Scan Event Matrix Initiated...")
    sync_positions_with_alpaca()
    
    for symbol, config in strategy_config.items():
        price, ema, rsi = fetch_market_indicators(symbol)
        if price is None:
            continue
            
        position = portfolio_positions[symbol]
        logger.info(f" > [{symbol}] Market: ${price:,.2f} | EMA50: ${ema:,.2f} | RSI14: {rsi:.1f} | Holding: {position['holding']}")
        
        # RULE 1: SAFE BUY ENTRY
        if not position["holding"]:
            if price <= config["entry_goal"] and price > ema and rsi < 65:
                logger.info(f"🚀 [TREND ENGINE MATCH] Transmitting BUY order for {symbol}")
                try:
                    req = MarketOrderRequest(
                        symbol=symbol, notional=config["allocation"], side=OrderSide.BUY, time_in_force=TimeInForce.GTC
                    )
                    trading_client.submit_order(order_data=req)
                    position["holding"] = True
                    position["buy_price"] = price
                except Exception as e:
                    logger.error(f"Buy execution failed for {symbol}: {e}")
                    
        # RULE 2: RELATIVE PROTECTIVE HARD STOP FLOOR
        elif position["holding"]:
            hard_stop_floor = position["buy_price"] * (1.0 - config["stop_loss_pct"])
            
            if price <= hard_stop_floor:
                logger.warning(f"🏁 [RISK MANAGEMENT EXECUTED] Hard stop breach on {symbol}. Liquidating portfolio tokens.")
                try:
                    req = MarketOrderRequest(
                        symbol=symbol, qty=position["qty"], side=OrderSide.SELL, time_in_force=TimeInForce.GTC
                    )
                    trading_client.submit_order(order_data=req)
                    position["holding"] = False
                    position["buy_price"] = 0.0
                except Exception as e:
                    logger.error(f"Liquidation execution failed for {symbol}: {e}")

if __name__ == "__main__":
    # Primary application polling matrix loop (checks markets every 15 seconds)
    while True:
        try:
            run_trading_cycle()
        except Exception as e:
            logger.error(f"Main processing failure: {e}")
        time.sleep(15)
