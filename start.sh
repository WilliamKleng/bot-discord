#!/bin/bash
# Prende el bot en segundo plano
python main.py &
# Prende el servidor web en el puerto que asigne el hosting
uvicorn web_server:app --host 0.0.0.0 --port ${PORT:-8000}