"""A FastAPI app: create a verification link for a user, and receive the decision.

    pip install "proofage[fastapi]" uvicorn
    export PROOFAGE_API_KEY=pk_test_...  PROOFAGE_SECRET_KEY=sk_test_...
    uvicorn examples.fastapi_app.main:app

and set your workspace's webhook URL to https://<public host>/webhooks/proofage.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from pydantic import BaseModel

from proofage import AsyncProofAge
from proofage.integrations.fastapi import ProofAgeWebhook

# A real app keeps this in its database, and ignores a late retry of an older delivery.
statuses: dict[str, str] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with AsyncProofAge() as client:
        app.state.proofage = client
        yield


app = FastAPI(lifespan=lifespan)


class StartRequest(BaseModel):
    user_id: str


@app.post("/verifications")
async def start(body: StartRequest, request: Request) -> dict[str, str]:
    """Create a session for your user; send them to `url`."""
    client: AsyncProofAge = request.app.state.proofage
    verification = await client.verifications.create(external_id=body.user_id)
    return {"id": verification.id, "url": verification.url}


@app.post("/webhooks/proofage")
async def proofage_webhook(event: ProofAgeWebhook) -> dict[str, bool]:
    """ProofAge calls this with the decision; the event is already verified."""
    if event.external_id is not None:
        statuses[event.external_id] = str(event.status)
    return {"ok": True}


@app.get("/status/{user_id}")
async def status(user_id: str) -> dict[str, str | None]:
    return {"status": statuses.get(user_id)}
