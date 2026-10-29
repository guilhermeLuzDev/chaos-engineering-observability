import os
import time
import httpx
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("load-generator")

ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://order-service:8000/orders")
RATE_DELAY = float(os.getenv("RATE_DELAY", "0.2"))  # ~5 requisições por segundo

def run_load():
    logger.info(f"🚀 Iniciando gerador de carga contínua para {ORDER_SERVICE_URL}...")
    # Aguarda o order-service subir
    time.sleep(3)
    
    with httpx.Client(timeout=5.0) as client:
        while True:
            try:
                resp = client.post(ORDER_SERVICE_URL, json={"amount": 49.90})
                data = resp.json()
                status = data.get("status")
                cb = data.get("circuit_breaker")
                dur = data.get("duration_ms")
                logger.info(f"➡️ Pedido enviado: status={status} | CB={cb} | latência={dur}ms")
            except Exception as e:
                logger.warning(f"Erro ao enviar pedido: {e}")
            
            time.sleep(RATE_DELAY)

if __name__ == "__main__":
    run_load()
