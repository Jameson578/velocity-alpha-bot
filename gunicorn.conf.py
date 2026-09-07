import logging
import threading

def post_worker_init(worker):
    """
    This special hook runs inside the Gunicorn worker process immediately on boot.
    Instead of importing from another file, we look up the app module directly 
    from the web server container state to ignite the loop safely.
    """
    logging.info("⚙️ Gunicorn Production Process Hook Triggered Successfully.")
    try:
        # Grabs the running application reference dictionary directly from the web server stack
        app_module = worker.wsgi
        if hasattr(app_module, 'application'):
            main_instance = app_module.application
        else:
            main_instance = app_module

        # Trigger the engine core configuration directly from the engine module state
        if hasattr(main_instance, 'ignite_engine_matrix_loop'):
            logging.info("🚀 Launching Quantitative Engine Thread Matrix from Gunicorn Container...")
            main_instance.ignite_engine_matrix_loop()
        else:
            logging.error("❌ Linkage Error: 'ignite_engine_matrix_loop' was not discovered inside your application file.")
    except Exception as e:
        logging.error(f"❌ Critical Exception caught inside worker hook layer: {e}")
