import os
import sys
import time
import threading
import logging
import pandas as pd
import numpy as np
from datetime import datetime, UTC

# Configure standard root logging to force output straight onto your dashboard log panel view
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

# 🌐 LIGHTWEIGHT WEB SERVER DEFINED NATIVELY AT THE TOP FOR PORT MAPPING PASSES
try:
    from flask import Flask
    app = Flask(__name__)
    @app.route('/')
    def health_check():
        return "Velocity Alpha Monolith Engine: ONLINE", 200
except ImportError:
    logging.error("❌ Critical Error: 'Flask' library not detected.")
    sys.exit(1)

# 🔐 DIRECT PRODUCTION PARAMETERS MAP (AUTHENTICATED LOGISTICS)
ALPACA_API_KEY = "PKGV2SNFX6ABDXTQQ25ZFQHGLN"
ALPACA_SECRET_KEY = "Bo2QTdwmDcXvZ8v3Vkttf8H1GwKFKxmXzTJ4B3nJDLrT"
ACCOUNT_TYPE = "paper"

try:
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
except ImportError:
    logging.error("❌ Critical Error: 'alpaca-py' library dependencies not detected.")
    sys.exit(1)

# 1. CORE OPERATIONAL CONTROL CENTER (MATCHING EXPERIMENTAL BLOCK METRICS)
PORTFOLIO_SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD"]
INITIAL_CASH = 500.00
MARGIN_LEVERAGE = 1.5
ATR_PROFIT_MULT = 2.5
ATR_STOP_MULT = 2.5
POLLING_INTERVAL_SECONDS = 15  # Wakes up inside process parameters context frame

# local telemetry context states dictionaries tracking blocks
thread_states = {symbol: {
    "buy_price": 0.0,
    "entry_cost": 0.0,
    "highest_high_in_trade": 0.0
} for symbol in PORTFOLIO_SYMBOLS}

# 3. LIVE MARKET DATA FETCH AND EXECUTION CLIENT GATEWAYS
data_client = CryptoHistoricalDataClient(api_key=ALPACA_API_KEY, secret_key=ALPACA_SECRET_KEY)
trading_client = TradingClient(api_key=ALPACA_API_KEY, secret_key=ALPACA_SECRET_KEY, paper=True)

def fetch_live_market_candles(symbol):
    end_time = datetime.now(UTC)
    start_time = end_time - pd.Timedelta(hours=100)
    clean_target_ticker = symbol.replace("/", "")
    try:
        request_params = CryptoBarsRequest(
            symbol_or_symbols=clean_target_ticker,
            timeframe=TimeFrame(amount=15, unit=TimeFrameUnit.Minute),
            start=start_time,
            end=end_time
        )
        bars = data_client.get_crypto_bars(request_params)
        df_raw = bars.df
        if df_raw is None or df_raw.empty:
            return None
        df = df_raw.reset_index(level=0, drop=True)
        df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
        return df[['Open', 'High', 'Low', 'Close', 'Volume']]
    except Exception as e:
        logging.error(f"❌ Internal API Data Fetch Failure on {symbol} (Target: {clean_target_ticker}): {e}")
        return None

def calculate_trend_signals(df_input):
    if df_input is None or df_input.empty or len(df_input) < 2:
        return None
    df = df_input.copy()
    df['Volume'] = df['Volume'].replace(0, 1e-8)
    df['Date_Day'] = df.index.date
    df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3.0
    df['TP_Vol'] = df['Typical_Price'] * df['Volume']
    df['Cum_TP_Vol'] = df.groupby('Date_Day')['TP_Vol'].cumsum()
    df['Cum_Vol'] = df.groupby('Date_Day')['Volume'].cumsum()
    df['VWAP'] = df['Cum_TP_Vol'] / df['Cum_Vol']
    df['High_Low'] = df['High'] - df['Low']
    df['High_Close_Prev'] = abs(df['High'] - df['Close'].shift(1))
    df['Low_Close_Prev'] = abs(df['Low'] - df['Close'].shift(1))
    df['TR'] = df[['High_Low', 'High_Close_Prev', 'Low_Close_Prev']].max(axis=1)
    df['ATR'] = df['TR'].rolling(window=20, min_periods=1).mean()
    df['Asset_Norm_Vol'] = df['ATR'] / df['Close']
    df['Fast_Trend_EMA'] = df['Close'].ewm(span=20, adjust=False).mean()
    df['Limit_Buy_Target'] = df['VWAP'] + (0.3 * df['ATR'])
    return df.ffill().bfill()

# 4. CORE ENGINE LIVE EXECUTION STATE MACHINE (THE CENTRAL WORKER LOOP)
def trading_loop():
    time.sleep(5)
    logging.info(f"⚡ Velocity Engine Live AUTHENTICATED-ALPACA Gateway Engaged...")
    while True:
        try:
            # Sync capital matrix directly with your active paper account dashboard parameters
            account_info = trading_client.get_account()
            current_cash = float(account_info.cash)
            portfolio_value = float(account_info.portfolio_value)
            
            # Pull currently open position vectors from the active broker node
            active_positions = trading_client.get_all_positions()
            holding_symbols = [p.symbol for p in active_positions]
            
            live_timestamp_str = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')
            logging.info(f"⏱️ Scan Event Matrix Initiated: {live_timestamp_str}")
            
            for symbol in PORTFOLIO_SYMBOLS:
                s = thread_states[symbol]
                clean_ticker = symbol.replace("/", "")
                is_holding = clean_ticker in holding_symbols
                market_data = fetch_live_market_candles(symbol)
                df_vectors = calculate_trend_signals(market_data)
                
                if df_vectors is None or len(df_vectors) < 2:
                    continue
                    
                current_close = df_vectors['Close'].iloc[-1]
                current_high = df_vectors['High'].iloc[-1]
                current_low = df_vectors['Low'].iloc[-1]
                current_atr = df_vectors['ATR'].iloc[-1]
                current_ema = df_vectors['Fast_Trend_EMA'].iloc[-1]
                current_norm_vol = df_vectors['Asset_Norm_Vol'].iloc[-1]
                limit_buy_target = df_vectors['Limit_Buy_Target'].iloc[-2]
                
                logging.info(f" > [{symbol}] Market: ${current_close:,.2f} | Entry Goal: ${limit_buy_target:,.2f} | Holding: {is_holding}")
                
                # --- STRUCTURED LIVE BROKER EXIT GATEWAYS ---
                if is_holding:
                    position_details = next(p for p in active_positions if p.symbol == clean_ticker)
                    position_qty = abs(float(position_details.qty))
                    if current_high > s["highest_high_in_trade"] or s["buy_price"] == 0:
                        s["highest_high_in_trade"] = current_high
                        s["buy_price"] = float(position_details.avg_entry_price)
                        
                    target_profit_price = s["buy_price"] + (ATR_PROFIT_MULT * current_atr)
                    is_profit_extended = s["highest_high_in_trade"] > (s["buy_price"] + (2.0 * current_atr))
                    is_trailing_active = s["highest_high_in_trade"] > (s["buy_price"] + (3.5 * current_atr))
                    
                    if is_trailing_active:
                        target_stop_price = s["highest_high_in_trade"] - (1.5 * current_atr)
                        reason_code = "TRAILING LOCK"
                    elif is_profit_extended:
                        target_stop_price = s["buy_price"]
                        reason_code = "BE SHIELD"
                    else:
                        target_stop_price = s["buy_price"] - (ATR_STOP_MULT * current_atr)
                        reason_code = "HARD STOP"
                        
                    # 🚀 TESTING OVERRIDE GATEWAY: Forces profit liquidation check to clear asset slots instantly
                    if current_high >= target_profit_price or current_low <= target_stop_price or True:
                        order_data = MarketOrderRequest(
                            symbol=clean_ticker,
                            qty=position_qty,
                            side=OrderSide.SELL,
                            time_in_force=TimeInForce.GTC
                        )
                        trading_client.submit_order(order_data)
                        logging.info(f"🏁 [NATIVE LIQUIDATION EXECUTED] -> Reason: {reason_code} for {symbol}")
                        s["buy_price"] = 0.0
                        s["highest_high_in_trade"] = 0.0
                        
                # --- STRUCTURED LIVE BROKER ENTRY GATEWAYS ---
                else:
                    # 🚀 PROACTIVE FORCE IGNITION: Bypasses filters initially to send real orders immediately
                    if current_high >= limit_buy_target or True:
                        rolling_kelly = 0.55 - ((1.0 - 0.55) / (ATR_PROFIT_MULT / ATR_STOP_MULT))
                        calculated_entry = current_cash * max(0.25, min(0.75, rolling_kelly * 0.5 * (1.3 if current_norm_vol > 0.0040 else 0.9)))
                        if calculated_entry < 15.0 or current_cash < 20.0:
                            continue
                            
                        order_data = MarketOrderRequest(
                            symbol=clean_ticker,
                            notional=round(calculated_entry, 2),
                            side=OrderSide.BUY,
                            time_in_force=TimeInForce.GTC
                        )
                        trading_client.submit_order(order_data)
                        logging.info(f"🚀 [NATIVE MARKET BUY ORDER TRANSMITTED] -> Allocated ${calculated_entry:,.2f} into {symbol}")
                        s["buy_price"] = current_close
                        s["highest_high_in_trade"] = current_close

            # Throttle loop iterations safely according to config parameters
            time.sleep(POLLING_INTERVAL_SECONDS)

        except Exception as loop_error:
            # ✅ Added safety handler block to fix the structural syntax mistake
