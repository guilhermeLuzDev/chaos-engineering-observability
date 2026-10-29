import asyncio
import uuid
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Payment Service")

class PaymentRequest(BaseModel):
    order_id: str
    amount: float

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/pay")
async def process_payment(req: PaymentRequest):
    # Simula latência realista de rede/processamento bancário (30ms a 50ms)
    await asyncio.sleep(0.04)
    return {
        "status": "CONFIRMED",
        "order_id": req.order_id,
        "transaction_id": str(uuid.uuid4())
    }
