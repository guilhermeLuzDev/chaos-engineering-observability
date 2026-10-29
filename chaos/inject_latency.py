#!/usr/bin/env python3
"""
Script para injetar 3.000ms de latência (caos) no serviço de pagamentos via Toxiproxy.
Usa apenas a biblioteca padrão do Python (urllib), sem necessidade de pip install.
"""
import json
import urllib.request
import urllib.error
import sys

TOXIPROXY_URL = "http://localhost:8474/proxies/payment_proxy/toxics"

payload = {
    "name": "payment_latency",
    "type": "latency",
    "stream": "downstream",
    "toxicity": 1.0,
    "attributes": {
        "latency": 3000,   # 3 segundos de atraso
        "jitter": 200      # variação de +/- 200ms
    }
}

def inject():
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        TOXIPROXY_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print("==================================================================")
            print("🚨 CAOS INJETADO COM SUCESSO!")
            print("💥 Latência de 3000ms (+/- 200ms) adicionada ao serviço de Pagamentos.")
            print("👀 Observe no Grafana (http://localhost:3000):")
            print("   1. A latência aumentará inicialmente até o timeout de 1.0s.")
            print("   2. Após 3 falhas consecutivas, o Circuit Breaker mudará para OPEN (Vermelho).")
            print("   3. As respostas passarão a retornar via Fallback imediato (~10ms).")
            print("==================================================================")
    except urllib.error.HTTPError as e:
        if e.code == 409:
            print("⚠️ A latência já está injetada no momento! Para resetar, rode: python chaos/reset_chaos.py")
        else:
            print(f"Erro ao injetar toxicidade: {e.code} - {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"Erro de conexão com o Toxiproxy: {e}")
        print("Certifique-se de que os containers estão rodando com 'docker compose up'.")

if __name__ == "__main__":
    inject()
