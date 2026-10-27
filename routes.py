"""HTTP routes."""

from __future__ import annotations

import json
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sse_starlette.sse import EventSourceResponse

from backend.app import __version__
from backend.app.api.deps import Container, cache_key, get_container, rate_limit
from backend.app.api.schemas import (
    AskRequest,
    AskResponse,
    InteractionRequest,
    LocalAnaestheticRequest,
    RegimenRequest,
    SearchRequest,
)
from backend.app.clinical import tools
from backend.app.generation.rag_pipeline import SourceView
from backend.app.guardrails import pii

router = APIRouter()


@router.get("/health", tags=["system"])
async def health(container: Container = Depends(get_container)) -> dict:
    return {
        "status": "ok", "version": __version__, "chunks_indexed": container.store.count(),
        "llm_provider": container.pipeline.provider.name, "cache": container.cache is not None,
    }


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> PlainTextResponse:
    return PlainTextResponse(generate_latest().decode(), media_type=CONTENT_TYPE_LATEST)


@router.post("/v1/ask", response_model=AskResponse, tags=["assistant"], dependencies=[Depends(rate_limit)])
async def ask(body: AskRequest, container: Container = Depends(get_container)) -> AskResponse:
    filters = body.filters.to_store_filters() if body.filters else None
    key = cache_key(pii.redact(body.question).text, body.history, filters, body.provider, body.patient_context)
    if container.cache is not None and (hit := container.cache.get(key)):
        return AskResponse.model_validate_json(hit)
    pipeline = container.pipeline_for(body.provider)
    result = await pipeline.answer(body.question, body.history, filters, body.patient_context)
    response = AskResponse.model_validate(asdict(result))
    if container.cache is not None and not result.abstained and result.grounded and not result.emergency_banner:
        container.cache.setex(key, container.settings.cache_ttl_seconds, response.model_dump_json())
    return response


@router.post("/v1/ask/stream", tags=["assistant"], dependencies=[Depends(rate_limit)])
async def ask_stream(body: AskRequest, container: Container = Depends(get_container)) -> EventSourceResponse:
    filters = body.filters.to_store_filters() if body.filters else None
    pipeline = container.pipeline_for(body.provider)

    async def events():  # type: ignore[no-untyped-def]
        async for event in pipeline.stream(body.question, body.history, filters, body.patient_context):
            yield {"event": event["event"], "data": json.dumps(event["data"])}

    return EventSourceResponse(events())


@router.post("/v1/search", tags=["evidence"], dependencies=[Depends(rate_limit)])
async def search(body: SearchRequest, container: Container = Depends(get_container)) -> dict:
    filters = body.filters.to_store_filters() if body.filters else None
    chunks, trace = container.retriever.retrieve(pii.redact(body.query).text, body.top_k, filters)
    return {"results": [asdict(SourceView.from_retrieved(i, c)) for i, c in enumerate(chunks, 1)],
            "retrieval": asdict(trace)}


@router.post("/v1/tools/regimen", tags=["clinical tools"])
async def regimen(body: RegimenRequest) -> dict:
    try:
        return asdict(tools.lookup_regimen(body.drug, body.age_years))
    except (KeyError, ValueError) as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/v1/tools/anaesthetic", tags=["clinical tools"])
async def local_anaesthetic(body: LocalAnaestheticRequest) -> dict:
    try:
        return asdict(tools.local_anaesthetic_max(body.product, body.weight_kg))
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/v1/tools/interactions", tags=["clinical tools"])
async def interactions(body: InteractionRequest) -> dict:
    return {"interactions": tools.check_interactions(body.drugs), "checked": body.drugs,
            "note": "Curated dental subset only. Absence of a result is not proof of safety; check the BNF."}


@router.get("/v1/tools/adrenaline", tags=["clinical tools"])
async def adrenaline(age_years: float) -> dict:
    try:
        return tools.adrenaline_dose(age_years)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
