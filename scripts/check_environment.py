"""Comprobación rápida para antes de la clase."""
from __future__ import annotations

import os
import socket
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


csv_path = Path("data/ecommerce_orders_dataset.csv")
db_path = Path("data/ecommerce_orders.db")
print("OPENROUTER_API_KEY:", "OK" if os.getenv("OPENROUTER_API_KEY") else "FALTA")
print("Modelo:", os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"))
print("CSV real:", "OK" if csv_path.exists() else "FALTA")
print("SQLite importada:", "OK" if db_path.exists() else "FALTA (ejecuta: python data/import_dataset_to_sqlite.py)")
print("MCP datos 8000:", "ACTIVO" if port_open(8000) else "INACTIVO")
print("MCP agente 8001:", "ACTIVO" if port_open(8001) else "INACTIVO")
