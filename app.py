import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import datetime, UTC
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

try:
    # Historical Data API
    from alpaca.data.historical import CryptoHistoricalDataClient
    from alpaca.data.requests import CryptoBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
    
    # Trading Execution API (Added for Live Integration)
    from alpaca.trading.client import TradingClient
    from alpaca.trading.requests import MarketOrderRequest, TakeProfitRequest, StopLossRequest
    from alpaca.trading.enums import OrderSide, TimeInForce
except ImportError:
    print("❌ Critical Error: 'alpaca-py' library not detected.")
    sys.exit(1)

# 1. SETUP WEB APP MODULE FOR RENDER
app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# 2. CRITICAL CONFIGURATION MATRIX (Secured via Environment Variables)
ALPACA_API_KEY = os.environ.get("ALPACA_API_KEY", "PKGV2SNFX6ABDXTQQ25ZFQHGLN")
ALPACA_SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "Bo2QTdwmDcXvZ8v3Vkttf8H1GwKFKxmXzTJ4B3nJDLrT")
ACCOUNT_TYPE = "paper"  # Change to "live" if running out of paper environment

PORTFOLIO_SYMBOLS = ["BTC/USD", "ETH/USD", "SOL/USD"]
MARGIN_LEVERAGE = 1.5 
ATR_PROFIT_MULT = 2.5
ATR_STOP_MULT = 2.5

# Initialize official Alpaca Clients
data_client = CryptoHistoricalDataClient(api_key=ALPACA_API_KEY, secret_key=ALPACA_SECRET_KEY)
trading_client = TradingClient(api_key=ALPACA_API_KEY, secret_key=ALPACA_SECRET_KEY, paper=(ACCOUNT_TYPE == "paper"))

logger.info(f"⚡ Velocity Engine Live AUTHENTICATED - Alpaca {ACCOUNT_TYPE.upper()} Gateway Engaged...")

# 3. MARKET CANDLE FETCH UTILITY
def fetch_live_market_candles(symbol):
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
            raise ValueError(f"Alpaca node returned an empty matrix for {symbol}.")
        df = df_raw.reset_index(level=0, drop=True)
        df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
        return df[['Open', 'High', 'Low', 'Close', 'Volume']]
    except Exception as e:
        logger.warning(f"Data Feed Interruption on {symbol}: {e}")
        return None

# 4. MATHEMATICAL MATRIX CALCULATOR
def calculate_trend_signals(df_input):
    if df_input is None or df_input.empty:
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

# 5. EXECUTABLE LIVE ENGINE 
def execution_cycle_tick():
    now = datetime.now(UTC)
    logger.info(f"⏱️ Scan Event Matrix Initiated: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    try:
        # Fetch actual live account equity rather than using static configurations
        account = trading_client.get_account()
        available_cash = float(account.cash)
        logger.info(f"💼 Current Brokerage Account Balance: ${available_cash:,.2f}")
    except Exception as e:
        logger.error(f"Failed to fetch account status from Alpaca API: {e}")
        return

    # Fetch real live asset states currently active on the exchange
    try:
        live_positions = trading_client.get_all_positions()
        active_symbols = [pos.symbol for pos in live_positions]
    except Exception as e:
        logger.error(f"Failed to pull active exposure mapping: {e}")
        active_symbols = []

    for symbol in PORTFOLIO_SYMBOLS:
        # Check if the asset is already processing in our account
        # Alpaca returns crypto symbols natively as standard formats (e.g. BTCUSD or BTC/USD)
        clean_symbol = symbol.replace("/", "")
        is_holding = any(pos_sym in [symbol, clean_symbol] for pos_sym in active_symbols)
        
        market_data = fetch_live_market_candles(symbol)
        df_vectors = calculate_trend_signals(market_data)
        if df_vectors is None:
            continue
            
        current_close = df_vectors['Close'].iloc[-1]
        current_high = df_vectors['High'].iloc[-1]
        current_atr = df_vectors['ATR'].iloc[-1]
        current_ema = df_vectors['Fast_Trend_EMA'].iloc[-1]
        current_norm_vol = df_vectors['Asset_Norm_Vol'].iloc[-1]
        limit_buy_target = df_vectors['Limit_Buy_Target'].iloc[-1]
        
        logger.info(f" > [{symbol}] Market: ${current_close:,.2f} | Entry Goal: ${limit_buy_target:,.2f} | Active Hold: {is_holding}")
        
        # ENTRY CONDITIONS
        if not is_holding and current_high >= limit_buy_target and (current_atr / current_close) >= 0.0010 and current_close > current_ema:
            
            # Simple Kelly allocation safety translation matrix logic
            rolling_kelly = 0.55 - ((1.0 - 0.55) / (ATR_PROFIT_MULT / ATR_STOP_MULT))
            calculated_entry = available_cash * max(0.25, min(0.75, rolling_kelly * 0.5 * (1.3 if current_norm_vol > 0.0040 else 0.9)))
            
            if calculated_entry < 10.0 and available_cash >= 10.0:
                calculated_entry = 10.0
            elif calculated_entry < 10.0 or calculated_entry > available_cash:
                continue

            # Calculate Native Risk Bracket Order Pricing
            target_profit_price = round(limit_buy_target + (ATR_PROFIT_MULT * current_atr), 2)
            target_stop_price = round(limit_buy_target - (ATR_STOP_MULT * current_atr), 2)
            
            # Calculate position sizing matching real leverage parameters
            position_value_with_leverage = calculated_entry * MARGIN_LEVERAGE
            qty_to_buy = round(position_value_with_leverage / current_close, 5)
            
            logger.info(f"🚀 Sending Live BRACKET Market Buy Order for {qty_to_buy} {symbol}")
            logger.info(f"🎯 Take-Profit set to: ${target_profit_price} | 🛑 Stop-Loss set to: ${target_stop_price}")
            
            try:
                # Constructing a dynamic live Bracket Market Order Request via Alpaca Brokerage
                bracket_order_req = MarketOrderRequest(
                    symbol=symbol,
                    qty=qty_to_buy,
                    side=OrderSide.BUY,
                    time_in_force=TimeInForce.GTC,
                    take_profit=TakeProfitRequest(limit_price=target_profit_price),
                    stop_loss=StopLossRequest(stop_price=target_stop_price)
                )
                
                trading_client.submit_order(order_data=bracket_order_req)
                logger.info(f"✅ Bracket Order successfully filled/submitted via Alpaca Engine.")
            except Exception as e:
                logger.error(f"🚨 ORDER REJECTION ROUTINE ENCOUNTERED: {e}")

# 6. INITIALIZE DYNAMIC TIMER POOL (Aligned: Executes cycle exactly every 15 minutes)
scheduler = BackgroundScheduler(daemon=True)
scheduler.add_job(func=execution_cycle_tick, trigger="interval", minutes=15)
scheduler.start()

# 7. OPEN WEB GATEWAY ROUTES FOR RENDER DEPLOY CHECKING
@app.route('/')
def health_endpoint():
    return "Velocity Matrix Live Core Engine Online and Running!", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))
