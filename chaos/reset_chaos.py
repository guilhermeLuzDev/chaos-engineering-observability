#!/usr/bin/env python3
"""
Script para remover o caos (restaurar a rede normal) e observar a autocura do sistema.
"""
import urllib.request
import urllib.error

TOXIPROXY_DELETE_URL = "http://localhost:8474/proxies/payment_proxy/toxics/payment_latency"

def reset():
    req = urllib.request.Request(
        TOXIPROXY_DELETE_URL,
        method="DELETE"
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print("==================================================================")
            print(" CAOS REMOVIDO! Conexão com o serviço de pagamentos restaurada.")
            print("   Observe a Autocura no Grafana (http://localhost:3000):")
            print("   1. O Circuit Breaker entrará no estado HALF-OPEN (Amarelo) para testar a rede.")
            print("   2. Ao confirmar que a resposta é rápida (<50ms), ele voltará para CLOSED (Verde).")
            print("   3. As ordens voltam a ser confirmadas normalmente com status 200 OK.")
            print("==================================================================")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print("ℹ️ Nenhum caos estava ativo no momento (a rede já estava limpa).")
        else:
            print(f"Erro ao remover toxicidade: {e.code} - {e.read().decode('utf-8')}")
    except Exception as e:
        print(f"Erro de conexão com o Toxiproxy: {e}")
        print("Certifique-se de que os containers estão rodando com 'docker compose up'.")

if __name__ == "__main__":
    reset()
