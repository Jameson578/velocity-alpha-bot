import os 
import sys 
import time 
import threading 
import logging 
import pandas as pd 
import numpy as np 
from datetime import datetime, UTC 

# Configure standard root logging to force output straight onto your Render log stream
logging.basicConfig( 
    level=logging.INFO, 
    format='%(asctime)s [%(levelname)s] %(message)s', 
    handlers=[logging.StreamHandler(sys.stdout)] 
) 

# 🌐 LIGHTWEIGHT WEB SERVER FOR RENDER.COM DEPLOYMENT
try: 
    from flask import Flask 
    app = Flask(__name__) 
    
    @app.route('/') 
    def health_check(): 
        return "Velocity Alpha Engine: ONLINE", 200 
except ImportError: 
    logging.error("❌ Critical Error: 'Flask' library not detected.") 
    sys.exit(1) 

# Global credentials placeholders updated inside the boot hook
ALPACA_API_KEY = None 
ALPACA_SECRET_KEY = None 
ACCOUNT_TYPE = "paper" 

try: 
    from alpaca.data.historical import CryptoHistoricalDataClient 
    from alpaca.data.requests import CryptoBarsRequest 
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit 
except ImportError: 
    logging.error("❌ Critical Error: 'alpaca-py' library not detected.") 
    sys.exit(1) 

# 1. CORE OPERATIONAL CONTROL CENTER (MULTI-ASSET MATRIX - OPTIMIZED PARAMS)
PORTFOLIO_SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD"] 
INITIAL_CASH = 500.00 
MARGIN_LEVERAGE = 1.5 
ATR_PROFIT_MULT = 2.5 
ATR_STOP_MULT = 2.5 
FEE_RATE = 0.0010 
POLLING_INTERVAL_SECONDS = 15 

# 2. LOCAL SIMULATED PORTFOLIO MANAGEMENT STATE (SHARED MATRIX POOL)
sim_cash = INITIAL_CASH 
trade_counter = 0 
total_fees_paid = 0.0 

# Tracking dictionaries matching script 2 structure
thread_states = {symbol: { 
    "is_holding": False, 
    "position_qty": 0.0, 
    "buy_price": 0.0, 
    "entry_cost": 0.0, 
    "highest_high_in_trade": 0.0 
} for symbol in PORTFOLIO_SYMBOLS} 

# Initialize client placeholder
data_client = None 

# 3. LIVE MARKET DATA FETCH ENGINE
def fetch_live_market_candles(symbol): 
    """Pulls genuine live 15-minute OHLCV bars for a specific pair via the authenticated Alpaca SDK.""" 
    if not data_client:
        logging.error(f"❌ [DATA ERROR] Client connection missing while attempting fetch for {symbol}")
        return None
        
    end_time = datetime.now(UTC) 
    start_time = end_time - pd.Timedelta(hours=100) 
    
    request_params = CryptoBarsRequest( 
        symbol_or_symbols=symbol, 
        timeframe=TimeFrame(15, TimeFrameUnit.Minute), 
        start=start_time, 
        end=end_time 
    ) 
    try: 
        bars = data_client.get_crypto_bars(request_params) 
        df_raw = bars.df 
        if df_raw is None or df_raw.empty: 
            raise ValueError(f"Alpaca node returned an empty snapshot matrix for {symbol}.") 
        df = df_raw.reset_index(level=0, drop=True) 
        df.rename(columns={ 
            'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume' 
        }, inplace=True) 
        return df[['Open', 'High', 'Low', 'Close', 'Volume']] 
    except Exception as e: 
        logging.warning(f"⚠️ Data Feed Interruption on {symbol}: {e}. Retrying matrix loop...") 
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

# 4. CORE ENGINE LIVE EXECUTION STATE MACHINE
def trading_loop(): 
    global sim_cash, trade_counter, total_fees_paid 
    
    logging.info(f"⚡ Velocity Engine Live AUTHENTICATED-ALPACA Gateway Engaged...") 
    logging.info(f"💰 Starting Capital: ${sim_cash:,.2f} USD | Dynamic Multi-Asset Focus: {PORTFOLIO_SYMBOLS}") 
    
    while True: 
        if not ALPACA_API_KEY or "YOUR_" in str(ALPACA_API_KEY): 
            logging.error("🛑 HALT DETECTED: ALPACA_API_KEY is structurally invalid or unpopulated!") 
            time.sleep(10) 
            continue 
        
        live_timestamp_str = datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC') 
        logging.info(f"⏱️ Scan Event Matrix Initiated: {live_timestamp_str}") 
        
        # Loop sequentially over all portfolio tickers matching script 2 loop structure
        for symbol in PORTFOLIO_SYMBOLS: 
            s = thread_states[symbol] 
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
            
            # Recalculate specific asset PnL for active positions
            open_pnl = (s["position_qty"] * (current_close - s["buy_price"])) if s["is_holding"] else 0.0 
            logging.info(f" > [{symbol}] Market: ${current_close:,.2f} | Entry Goal: ${limit_buy_target:,.2f} | Asset PnL: ${open_pnl:+,.2f}") 
            
            # --- STRUCTURED EXIT LOGIC ---
            if s["is_holding"]: 
                if current_high > s["highest_high_in_trade"]: 
                    s["highest_high_in_trade"] = current_high 
                    
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
                
                if current_high >= target_profit_price or current_low <= target_stop_price: 
                    exit_price = target_profit_price if current_high >= target_profit_price else target_stop_price 
                    exit_reason = f"[{symbol}] VELOCITY PROFIT TARGET" if current_high >= target_profit_price else f"[{symbol}] {reason_code}" 
                    
                    net_pnl = (s["entry_cost"] * ((exit_price - s["buy_price"]) / s["buy_price"]) * MARGIN_LEVERAGE) - ((s["entry_cost"] * MARGIN_LEVERAGE) * FEE_RATE) 
                    total_fees_paid += ((s["entry_cost"] * MARGIN_LEVERAGE) * FEE_RATE) 
                    sim_cash += s["entry_cost"] + net_pnl 
                    trade_counter += 1 
                    
                    logging.info(f"🏁 [VIRTUAL LIQUIDATION] -> Event: {exit_reason}") 
                    logging.info(f"🎉 Trade #{trade_counter} Settled! Net PnL: ${net_pnl:+.2f} | Shared Wallet Cash: ${sim_cash:,.2f}") 
                    
                    s["is_holding"] = False 
                    s["position_qty"] = 0.0 
                    s["highest_high_in_trade"] = 0.0 
                    
            # --- STRUCTURED ENTRY LOGIC ---
            else: 
                if current_high >= limit_buy_target and (current_atr / current_close) >= 0.0010 and current_close > current_ema: 
                    rolling_kelly = 0.55 - ((1.0 - 0.55) / (ATR_PROFIT_MULT / ATR_STOP_MULT)) 
                    calculated_entry = sim_cash * max(0.25, min(0.75, rolling_kelly * 0.5 * (1.3 if current_norm_vol > 0.0040 else 0.9))) 
                    
                    if calculated_entry < 10.0 and sim_cash >= 10.0: 
                        calculated_entry = 10.0 
                    elif calculated_entry < 10.0 and sim_cash < 10.0: 
                        continue 
                        
                    s["entry_cost"] = calculated_entry 
                    entry_fee = (s["entry_cost"] * MARGIN_LEVERAGE) * FEE_RATE 
                    sim_cash -= (s["entry_cost"] + entry_fee) 
                    total_fees_paid += entry_fee 
                    
                    s["buy_price"] = limit_buy_target 
                    s["position_qty"] = (s["entry_cost"] * MARGIN_LEVERAGE) / s["buy_price"] 
                    s["highest_high_in_trade"] = current_close 
                    s["is_holding"] = True 
                    
                    logging.info("🚀 [VIRTUAL MARKET ENTRY ORDER EXECUTED]") 
                    logging.info(f" Allocation: Buying {s['position_qty']:.4f} units of {symbol} at ${s['buy_price']:,.2f} using {MARGIN_LEVERAGE}x Leverage") 
                    
        # Calculate pool equity across shared context state
        active_positions_value = 0.0 
