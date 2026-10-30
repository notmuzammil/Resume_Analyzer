import asyncio
import json
import logging
import time
import os
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from . import config
from .llm import (
    MAX_JD_CHARS, MAX_RESUME_CHARS, analyze_jd, available_models, clean_jd_analysis, evaluate_resume, resolve_model,
)
from .logging_setup import RequestLogMiddleware, request_id, setup_logging
from .parsers import ParseError, extract_text

setup_logging()
logger = logging.getLogger("app.main")
logger.info("Starting: default provider=%s model=%s log_level=%s", config.DEFAULT_PROVIDER or "none", config.DEFAULT_MODEL or "first listed", config.LOG_LEVEL)
for p in config.PROVIDERS.values():
    logger.info(
        "Provider %s (%s): base_url=%s models=%s fallback=%s concurrency=%d timeout=%ds key=%s",
        p.id, p.label, p.base_url, ",".join(p.models) or "asked from the server", p.fallback_model or "none",
        p.concurrency, p.timeout, "set" if p.api_key else "none",
    )
for name in config.SKIPPED_PROVIDERS:
    logger.warning("Provider %s is left out: set %s_BASE_URL (and %s_API_KEY if it needs one) in Backend/.env", name, name, name)
if not config.llm_configured():
    logger.error("No AI provider is configured: set LLM_PROVIDERS and each provider's settings in Backend/.env")

LLM_NOT_CONFIGURED = "No AI model is configured. Set LLM_PROVIDERS and the provider settings in Backend/.env and restart the server."

app = FastAPI(title="Resume Shortlisting API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)
app.add_middleware(RequestLogMiddleware)
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "llm_configured": config.llm_configured(),
        "providers": await available_models(),
        "default": {"provider": config.DEFAULT_PROVIDER, "model": config.DEFAULT_MODEL},
        "max_resumes": config.MAX_RESUMES,
    }
async def _choose_model(provider: str, model: str):
    if not config.llm_configured():
        raise HTTPException(500, LLM_NOT_CONFIGURED)
    try:
        chosen_provider, chosen_model = await resolve_model(provider, model)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.warning("Could not reach provider %s: %s", provider or config.DEFAULT_PROVIDER, exc)
        raise HTTPException(502, f"Could not reach the AI server for '{provider or config.DEFAULT_PROVIDER}'. Is it running?")
    logger.info("Using model %s on %s", chosen_model, chosen_provider.label)
    return chosen_provider, chosen_model
async def _read_upload(file: UploadFile) -> bytes:
    data = await file.read()
    if len(data) > config.MAX_FILE_BYTES:
        raise ParseError(f"File is larger than {config.MAX_FILE_BYTES // (1024 * 1024)} MB.")
    return data
async def _read_jd(jd_text: str, jd_file: UploadFile | None) -> str:
    if jd_file is not None and jd_file.filename:
        try:
            jd = extract_text(jd_file.filename, await _read_upload(jd_file))
        except ParseError as exc:
            logger.warning("Could not read JD file %s: %s", jd_file.filename, exc)
            raise HTTPException(400, f"Job description: {exc}")
    else:
        jd = jd_text.strip()
    if len(jd) < 50:
        raise HTTPException(400, "Please provide a job description (upload a file or paste at least a few lines).")
    if len(jd) > MAX_JD_CHARS:
        logger.warning("JD is %d chars; only the first %d are used", len(jd), MAX_JD_CHARS)
    return jd
@app.post("/api/analyze-jd")
async def analyze_job_description(
    jd_text: str = Form(""),
    jd_file: UploadFile | None = File(None),
    provider: str = Form(""),
    model: str = Form(""),
):
    chosen_provider, chosen_model = await _choose_model(provider, model)
    jd = await _read_jd(jd_text, jd_file)
    logger.info("Analysing JD from %s (%d chars)", f"file {jd_file.filename}" if jd_file and jd_file.filename else "pasted text", len(jd))
    try:
        analysis = await analyze_jd(jd, chosen_provider, chosen_model)
    except Exception as exc:
        logger.exception("JD analysis failed")
        raise HTTPException(502, f"Could not analyse the job description: {exc}")
    _log_analysis(analysis)
    return analysis
@app.post("/api/screen")
async def screen(
    resumes: list[UploadFile] = File(...),
    jd_text: str = Form(""),
    jd_file: UploadFile | None = File(None),
    jd_analysis: str = Form(""),
    ids: str = Form(""),
    provider: str = Form(""),
    model: str = Form(""),
):
    try:
        previous_analysis = clean_jd_analysis(json.loads(jd_analysis)) if jd_analysis else None
        resume_ids = json.loads(ids) if ids else list(range(len(resumes)))
    except (json.JSONDecodeError, ValueError):
        logger.warning("Rejected screening request: invalid JD analysis or retry data")
        raise HTTPException(400, "Invalid job description analysis or retry data.")
    if len(resume_ids) != len(resumes):
        raise HTTPException(400, "Invalid retry data.")

    if len(resumes) > config.MAX_RESUMES:
        raise HTTPException(400, f"You can upload at most {config.MAX_RESUMES} resumes at a time.")

    chosen_provider, chosen_model = await _choose_model(provider, model)
    jd = await _read_jd(jd_text, jd_file)
    logger.info("Screening %d resume(s)%s", len(resumes), " (retry)" if ids else "")
    if previous_analysis:
        _log_analysis(previous_analysis, reviewed=True)

    items = []
    for resume_id, file in zip(resume_ids, resumes):
        item = {"id": resume_id,"file_name": file.filename, "text": None, "error": None}
        try:
            item["text"] = extract_text(file.filename or "", await _read_upload(file))
            logger.info("Read %s: %d chars", file.filename, len(item["text"]))
            if len(item["text"]) > MAX_RESUME_CHARS:
                logger.warning("%s is %d chars; only the first %d are evaluated", file.filename, len(item["text"]), MAX_RESUME_CHARS)
        except ParseError as exc:
            item["error"] = str(exc)
            logger.warning("Could not read %s: %s", file.filename, exc)
        items.append(item)

    semaphore = asyncio.Semaphore(chosen_provider.concurrency)
    async def run(item: dict, analysis: dict) -> dict:
        base = {"id": item["id"], "file_name": item["file_name"]}
        if item["error"]:
            return {**base, "status": "error", "error": item["error"]}
        try:
            async with semaphore:
                start = time.perf_counter()
                evaluation = await evaluate_resume(jd, analysis, item["text"], chosen_provider, chosen_model)
            logger.info(
                "%s: score %d, %s in %.1fs%s%s", item["file_name"], evaluation["score"], evaluation["category"],
                time.perf_counter() - start,
                f", missing deal-breakers: {evaluation['failed_deal_breakers']}" if evaluation["failed_deal_breakers"] else "",
                f", to check: {evaluation['unverified_deal_breakers']}" if evaluation["unverified_deal_breakers"] else "",
            )
            return {**base, "status": "ok", **evaluation}
        except Exception as exc:
            logger.exception("Evaluation of %s failed", item["file_name"])
            return {**base, "status": "error", "error": f"AI evaluation failed: {exc}"}

    async def stream():
        start = time.perf_counter()
        yield _event("start", total=len(items), request_id=request_id.get())
        if previous_analysis:
            analysis = previous_analysis
        else:
            try:
                analysis = await analyze_jd(jd, chosen_provider, chosen_model)
            except Exception as exc:
                logger.exception("JD analysis failed")
                yield _event("error", message=f"Could not analyse the job description: {exc}")
                return
            _log_analysis(analysis)
        yield _event("jd", data=analysis)

        tasks = [asyncio.create_task(run(item, analysis)) for item in items]
        results = []
        try:
            for next_done in asyncio.as_completed(tasks):
                results.append(await next_done)
                yield _event("result", data=results[-1])
            yield _event("done")
            failed = sum(r["status"] != "ok" for r in results)
            logger.info("Screening finished in %.0fs: %d ok, %d failed", time.perf_counter() - start, len(results) - failed, failed)
        except (asyncio.CancelledError, GeneratorExit):
            logger.warning("Browser disconnected after %d of %d results; stopping the rest", len(results), len(items))
            raise
        finally:
            for task in tasks:
                task.cancel()

    return StreamingResponse(stream(), media_type="application/x-ndjson")
def _log_analysis(analysis: dict, reviewed: bool = False) -> None:
    logger.info(
        "%s JD: %r, weights %s, min years %s, must-haves %s, deal-breakers %s",
        "Reviewed" if reviewed else "Analysed", analysis["job_title"], analysis["weights"],
        analysis["min_experience_years"], analysis["must_haves"], analysis["deal_breakers"],
    )
def _event(event_type: str, **fields) -> str:
    return json.dumps({"type": event_type, **fields}) + "\n"

FRONTEND_DIST = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "Frontend", "dist"))

if os.path.exists(FRONTEND_DIST):
    # Serve assets folder
    assets_dir = os.path.join(FRONTEND_DIST, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # Catch-all to serve index.html for React SPA routing
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
else:
    logger.warning("Frontend build not found at %s. Run 'npm run build' inside Frontend/", FRONTEND_DIST)
