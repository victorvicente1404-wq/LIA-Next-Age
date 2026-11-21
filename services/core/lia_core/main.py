from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Lia Core", version="0.1.0")


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "lia-core"
    inference: str = "not_configured"


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()
