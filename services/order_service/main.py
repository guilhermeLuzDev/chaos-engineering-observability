import os
import time
import uuid
import asyncio
import logging
from enum import Enum
from typing import Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel
import httpx
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# Configuração de logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("order-service")

app = FastAPI(title="Order Service (Resilient with Circuit Breaker)")

# URL do serviço de pagamentos passando pelo Toxiproxy
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL", "http://toxiproxy:8475/pay")

# ---------------------------------------------------------
# MÉTRICAS PROMETHEUS (Sinais RED e Estado de Resiliência)
# ---------------------------------------------------------
# Rate & Errors: Contagem de requisições por status e uso de fallback
REQUEST_COUNT = Counter(
    "order_requests_total",
    "Total de requisições recebidas pelo Order Service",
    ["status", "fallback"]
)

# Duration: Histograma de latência das requisições (método RED)
REQUEST_LATENCY = Histogram(
    "order_request_duration_seconds",
    "Latência de resposta da API de pedidos em segundos",
    buckets=[0.02, 0.05, 0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
)

# Estado do Circuit Breaker: 0 = CLOSED (Normal), 1 = OPEN (Falha/Caos), 2 = HALF-OPEN (Testando recuperação)
CIRCUIT_BREAKER_STATE = Gauge(
    "circuit_breaker_state",
    "Estado atual do Circuit Breaker (0=CLOSED, 1=OPEN, 2=HALF-OPEN)"
)

CIRCUIT_BREAKER_FAILURES = Gauge(
    "circuit_breaker_failures_count",
    "Contador de falhas consecutivas antes de desarmar"
)

# ---------------------------------------------------------
# IMPLEMENTAÇÃO DIDÁTICA DO CIRCUIT BREAKER
# ---------------------------------------------------------
class CircuitState(str, Enum):
    CLOSED = "CLOSED"       # 0: Saudável. Todas as chamadas passam para a dependência.
    OPEN = "OPEN"           # 1: Disparado. Chamadas falham rápido (Fail-Fast) sem esperar.
    HALF_OPEN = "HALF_OPEN" # 2: Teste. Permite uma chamada piloto para verificar se a dependência voltou.

class CircuitBreakerOpenException(Exception):
    pass

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 8.0, half_open_success_threshold: int = 16):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_success_threshold = half_open_success_threshold  # Exige ~4 segundos de testes saudáveis
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_state_change = time.time()
        self._sync_metric()

    def _sync_metric(self):
        state_map = {CircuitState.CLOSED: 0, CircuitState.OPEN: 1, CircuitState.HALF_OPEN: 2}
        CIRCUIT_BREAKER_STATE.set(state_map[self.state])
        CIRCUIT_BREAKER_FAILURES.set(self.failure_count)

    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            logger.info(f"🧪 Teste em HALF-OPEN bem-sucedido ({self.success_count}/{self.half_open_success_threshold})")
            if self.success_count >= self.half_open_success_threshold:
                logger.info("🔄 Circuit Breaker recuperado após bateria de testes! HALF-OPEN -> CLOSED")
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0
        self._sync_metric()

    def record_failure(self):
        self.failure_count += 1
        self.success_count = 0
        logger.warning(f"⚠️ Falha registrada ({self.failure_count}/{self.failure_threshold})")
        if self.state == CircuitState.HALF_OPEN or self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.last_state_change = time.time()
            logger.error(f"🚨 CIRCUIT BREAKER ABRIU! Estado: OPEN (Protegendo o sistema contra falhas em cascata)")
        self._sync_metric()

    def allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            elapsed = time.time() - self.last_state_change
            if elapsed >= self.recovery_timeout:
                logger.info("⏳ Tempo de recuperação atingido. Mudando para HALF-OPEN para testar dependência...")
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                self._sync_metric()
                return True
            return False

        # HALF_OPEN permite passar as requisições piloto de teste
        return True

# Instância do Circuit Breaker:
# Abre após 3 falhas seguidas, aguarda 8s e exige 16 requisições de teste (~4s) em HALF-OPEN antes de fechar
circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=8.0, half_open_success_threshold=16)


# ---------------------------------------------------------
# MODELOS E ROTAS DA API
# ---------------------------------------------------------
class OrderRequest(BaseModel):
    customer_id: Optional[str] = "cliente-123"
    amount: Optional[float] = 99.90

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/metrics")
def metrics():
    """Endpoint raspado pelo Prometheus a cada 2 segundos"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

@app.get("/circuit-breaker/status")
def cb_status():
    return {
        "state": circuit_breaker.state.value,
        "failure_count": circuit_breaker.failure_count,
        "failure_threshold": circuit_breaker.failure_threshold,
        "recovery_timeout_seconds": circuit_breaker.recovery_timeout
    }

@app.post("/orders")
async def create_order(order: OrderRequest):
    order_id = str(uuid.uuid4())[:8]
    start_time = time.time()
    fallback_activated = False

    # 1. Verifica se o Circuit Breaker permite chamar o serviço de pagamentos
    if not circuit_breaker.allow_request():
        # Fail-Fast: O Circuit Breaker está ABERTO!
        # Não tentamos fazer a requisição HTTP. Retornamos o fallback imediatamente.
        fallback_activated = True
        duration = time.time() - start_time
        REQUEST_LATENCY.observe(duration)
        REQUEST_COUNT.labels(status="fallback", fallback="true").inc()

        logger.info(f"🛡️ Pedido {order_id}: Circuit Breaker ABERTO -> Fallback imediato em {duration*1000:.1f}ms")
        return JSONResponse(
            status_code=200,
            content={
                "order_id": order_id,
                "status": "PENDING_OFFLINE",
                "message": "Pagamento em contingência acionado pelo Circuit Breaker. Pedido enfileirado para processamento posterior.",
                "circuit_breaker": "OPEN (Fail-Fast)",
                "duration_ms": round(duration * 1000, 2)
            }
        )

    # 2. Tenta chamar o serviço de pagamentos com Timeout rígido de 1.0s
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            resp = await client.post(
                PAYMENT_SERVICE_URL,
                json={"order_id": order_id, "amount": order.amount}
            )
            resp.raise_for_status()
            circuit_breaker.record_success()

            duration = time.time() - start_time
            REQUEST_LATENCY.observe(duration)
            REQUEST_COUNT.labels(status="success", fallback="false").inc()

            return {
                "order_id": order_id,
                "status": "CONFIRMED",
                "payment_info": resp.json(),
                "circuit_breaker": circuit_breaker.state.value,
                "duration_ms": round(duration * 1000, 2)
            }

    except (httpx.TimeoutException, httpx.HTTPError, Exception) as exc:
        # A chamada falhou (ou tomou timeout de 1s devido ao caos injetado)
        circuit_breaker.record_failure()
        fallback_activated = True

        duration = time.time() - start_time
        REQUEST_LATENCY.observe(duration)
        REQUEST_COUNT.labels(status="degraded_fallback", fallback="true").inc()

        logger.warning(f"⚠️ Pedido {order_id}: Falha na dependência ({type(exc).__name__}). Ativando fallback.")
        return JSONResponse(
            status_code=200,
            content={
                "order_id": order_id,
                "status": "PENDING_OFFLINE",
                "message": f"Falha na comunicação com gateway de pagamento. Pedido salvo em contingência.",
                "error": str(exc),
                "circuit_breaker": circuit_breaker.state.value,
                "duration_ms": round(duration * 1000, 2)
            }
        )
