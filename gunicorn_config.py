import multiprocessing
import os

# Helper function to get environment variables with defaults
def get_env_variable(var_name, default):
    return os.getenv(var_name, default)

# Server Socket
bind = get_env_variable('GUNICORN_BIND', '0.0.0.0:8000')

# Worker Processes
#workers = int(get_env_variable('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))
workers = int(get_env_variable('GUNICORN_WORKERS', 1))
threads = int(get_env_variable('GUNICORN_THREADS', 2))

# Server Mechanics
preload_app = bool(int(get_env_variable('GUNICORN_PRELOAD_APP', '0')))
timeout = int(get_env_variable('GUNICORN_TIMEOUT', 120))

# Debugging
loglevel = get_env_variable('GUNICORN_LOGLEVEL', 'info')

# Logging
accesslog = get_env_variable('GUNICORN_ACCESSLOG', '-')
errorlog = get_env_variable('GUNICORN_ERRORLOG', '-')

# Process Naming
proc_name = get_env_variable('GUNICORN_PROC_NAME', 'myapp')

# Server Hooks
def on_starting(server):
    print("Gunicorn server is starting")

def when_ready(server):
    print("Gunicorn server is ready")

def worker_int(worker):
    print("Worker received SIGINT or SIGQUIT signal")

def worker_abort(worker):
    print("Worker received SIGABRT signal")

# Assigning the hooks
on_starting = on_starting
when_ready = when_ready
worker_int = worker_int
worker_abort = worker_abort
