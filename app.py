import os
import time
import logging
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# 1. Setup Structured Application Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("VelocityEngine")

# 2. Alpaca Gateway Authentication
# Safely assign your environment credentials inside your Render control dashboard
API_KEY = os.environ.get("ALPACA_API_KEY", "YOUR_API_KEY_HERE")
SECRET_KEY = os.environ.get("ALPACA_SECRET_KEY", "YOUR_SECRET_KEY_HERE")
PAPER = True  

trading_client = TradingClient(api_key=API_KEY, secret_key=SECRET_KEY, paper=PAPER)

# 3. Strategy Parameters Configuration
strategy_config = {
    "BTC/USD": {"entry_goal": 78543.73, "stop_loss_pct": 0.01, "allocation": 24000.0},
    "ETH/USD": {"entry_goal": 2487.56, "stop_loss_pct": 0.01, "allocation": 24000.0},
    "SOL/USD": {"entry_goal": 103.26, "stop_loss_pct": 0.01, "allocation": 24000.0}
}

# 4. In-Memory Tracking States (Saves what you paid so you don't instantly churn)
portfolio_positions = {
    "BTC/USD": {"holding": False, "buy_price": 0.0, "qty": 0.0},
    "ETH/USD": {"holding": False, "buy_price": 0.0, "qty": 0.0},
    "SOL/USD": {"holding": False, "buy_price": 0.0, "qty": 0.0}
}

def execute_alpaca_order(symbol, side, allocation_or_qty):
    \"\"\"Transmits safe market orders downstream to Alpaca APIs\"\"\"
    try:
        # Standardize tickers (Alpaca reads 'BTCUSD' instead of 'BTC/USD')
        alpaca_ticker = symbol.replace("/", "")
        
        if side == OrderSide.BUY:
            req = MarketOrderRequest(
                symbol=alpaca_ticker,
                notional=allocation_or_qty, # Allocates exact cash amount
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC
            )
            trading_client.submit_order(order_data=req)
            logger.info(f"🚀 [ALPACA ORDER SENT] Market BUY submitted for {symbol}: ${allocation_or_qty:,.2f}")
            
        elif side == OrderSide.SELL:
            req = MarketOrderRequest(
                symbol=alpaca_ticker,
                qty=allocation_or_qty, # Liquidates your specific token count
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC
            )
            trading_client.submit_order(order_data=req)
            logger.info(f"🏁 [ALPACA ORDER SENT] Liquidation MARKET SELL submitted for {symbol}: {allocation_or_qty}")
    except Exception as e:
        logger.error(f"Execution failed for {symbol}: {e}")

def scan_event_matrix(symbol, current_market_price):
    config = strategy_config[symbol]
    position = portfolio_positions[symbol]
    
    logger.info(f" > [{symbol}] Market: ${current_market_price:,.2f} | Entry Goal: ${config['entry_goal']:,.2f} | Holding: {position['holding']}")

    # RULE 1: SAFE BUY CONDITION
    if not position["holding"]:
        if current_market_price <= config["entry_goal"]:
            logger.info(f"🚀 [NATIVE MARKET BUY ORDER TRANSMITTED] -> Allocated ${config['allocation']:,.2f} into {symbol}")
            
            execute_alpaca_order(symbol, OrderSide.BUY, config["allocation"])
            
            # Update position states to remember what you spent
            position["holding"] = True
            position["buy_price"] = current_market_price
            position["qty"] = config["allocation"] / current_market_price 

    # RULE 2: FIXED SELL CONDITION (Prevents immediate stop-loss loops)
    elif position["holding"]:
        # Calculate trailing floor using your actual entry fill price
        hard_stop_floor = position["buy_price"] * (1.0 - config["stop_loss_pct"])
        
        if current_market_price <= hard_stop_floor:
            logger.warning(f"🏁 [NATIVE LIQUIDATION EXECUTED] -> Reason: HARD STOP for {symbol} (Paid: ${position['buy_price']:,.2f}, Floor: ${hard_stop_floor:,.2f})")
            
            execute_alpaca_order(symbol, OrderSide.SELL, position["qty"])
            
            # Clear state fields safely post liquidation
            position["holding"] = False
            position["buy_price"] = 0.0
            position["qty"] = 0.0
