import logging

def post_worker_init(worker):
    """
    This special Gunicorn lifecycle hook runs INSIDE the active live 
    worker process context immediately after it boots up.
    """
    logging.info(" Gunicorn Worker Boot Hook Detected! Intercepting process context...")
    
    try:
        # Extract the application module object directly from Gunicorn's runtime space
        # This completely bypasses the need to guess the exact script file name!
        app_instance = worker.wsgi
        
        # Pull the module context out of the WSGI wrapper array
        if hasattr(app_instance, 'application'):
            module_context = app_instance.application
        else:
            module_context = app_instance

        # Dynamically locate and fire the matrix initialization engine hook
        if hasattr(module_context, 'ignite_trading_matrix_on_worker'):
            logging.info("🚀 Triggering detached Quantitative Matrix thread from Gunicorn Hook...")
            module_context.ignite_trading_matrix_on_worker()
        else:
            # Fallback scan lookup across common naming arrays if structure is highly nested
            logging.error("❌ Crucial function 'ignite_trading_matrix_on_worker' missing from code file!")
            
    except Exception as e:
        logging.error(f"❌ Error spawning trading thread from Gunicorn post-fork hook: {e}")
