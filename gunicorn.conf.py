import logging

def post_worker_init(worker):
    """
    This special hook runs INSIDE the live worker process 
    immediately after Gunicorn boots up on Render.
    """
    logging.info(" Gunicorn Worker Boot Hook Detected! Intercepting process context...")
    try:
        # Import your startup function directly from your main app script
        from app import ignite_trading_matrix_on_worker
        
        logging.info("🚀 Triggering detached Quantitative Matrix thread from Gunicorn Hook...")
        ignite_trading_matrix_on_worker()
    except Exception as e:
        logging.error(f"❌ Error spawning trading thread from Gunicorn post-fork hook: {e}")
