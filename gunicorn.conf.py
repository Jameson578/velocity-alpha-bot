import logging
import threading

def post_worker_init(worker):
    """
    Standard Gunicorn lifecycle hook container.
    Safely delegates process flow to the central app script structure.
    """
    logging.info("⚙️ Gunicorn worker container wrapper online. Boot sequence clear.")
    
    try:
        # Import the trading loop from your app file at worker execution runtime
        from app import trading_loop
        
        # Spin up the background execution thread inside the isolated worker environment
        trading_thread = threading.Thread(target=trading_loop, daemon=True)
        trading_thread.start()
        logging.info("🚀 Background Trading Engine Thread Successfully Launched inside Gunicorn Worker Container!")
    except Exception as e:
        logging.error(f"❌ Critical Error: Failed to initiate background execution thread inside worker container: {e}")
