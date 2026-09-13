import time
import requests
import datetime

# --- CONFIGURATION ---
# Replace with your actual Alpaca Keys
ALPACA_API_KEY = "YOUR_API_KEY_HERE"
ALPACA_SECRET_KEY = "YOUR_SECRET_KEY_HERE"

# List of assets tracked by your Scan Event Matrix
SYMBOLS = ["BTCUSD", "ETHUSD", "SOLUSD"]
# How often to check for new bar data (seconds)
LOOP_INTERVAL = 15 

def get_crypto_bars(symbol):
    """
    Safely fetches the latest crypto bars from Alpaca.
    Protects against weekend 'char 0' parsing bugs and empty server payloads.
    """
    # Alpaca multi-asset crypto bars endpoint
    url = "https://alpaca.markets"
    
    headers = {
        "Apca-Api-Key-Id": ALPACA_API_KEY,
        "Apca-Api-Secret-Key": ALPACA_SECRET_KEY,
        "Accept": "application/json"
    }
    
    # Query parameters for live market telemetry
    params = {
        "symbols": symbol,
        "timeframe": "1Min",
        "limit": 1
    }
    
    try:
        # 10 second timeout stops Render container from hanging infinitely on weak connections
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        # Guard Phase 1: Check HTTP Status
        if response.status_code == 200:
            # Safe JSON extraction block
            data = response.json()
            if data and "bars" in data and data["bars"]:
                return data["bars"]
            else:
                print(f"[WARNING] Telemetry empty but valid format for {symbol}")
                return None
                
        elif response.status_code == 429:
            print(f"[WARNING] ⚠️ Rate Limit hit (429)! Cooling down for 30s...")
            time.sleep(30)
            return None
            
        else:
            print(f"[WARNING] Server rejected request. Status Code: {response.status_code}")
            return None
            
    except requests.exceptions.Timeout:
        print(f"[WARNING] ⏱️ Connection timed out fetching {symbol}. Server is sluggish.")
        return None
        
    except Exception as e:
        # CRITICAL PROTECTION: Catches 'Expecting value: line 1 column 1 (char 0)'
        print(f"[ERROR HANDLED] Skipped invalid or empty market telemetry for {symbol}. Error: {e}")
        return None

def execute_trading_logic(symbol, bar_data):
    """
    Placeholder for your bot's core trading strategies.
    Replace this internal code block with your active math indicators.
    """
    print(f"📈 [STRATEGY] Processing data stream for {symbol}...")
    # Your indicator logic / order generation goes here
    pass

# --- MAIN RUNTIME LOOP ---
if __name__ == "__main__":
    print("🚀 Velocity Alpha Bot Activated. Starting 24/7 Monitoring...")
    
    while True:
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{current_time}] Scan Event Matrix Initiated...")
        
        for symbol in SYMBOLS:
            # Query data provider safely
            market_telemetry = get_crypto_bars(symbol)
            
            if market_telemetry:
                # Execute trading strategies if telemetry contains valid live data
                execute_trading_logic(symbol, market_telemetry)
            else:
                # Handle weekend failures gracefully without letting the main thread crash
                print(f"⚠️ [MONITOR] Skipping execution cycle for {symbol} due to missing data.")
                
        # Sleep until the next polling window opens
        time.sleep(LOOP_INTERVAL)
