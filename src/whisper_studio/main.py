from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import av
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from faster_whisper import WhisperModel
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent.parent.parent
PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
UPLOAD_DIR = BASE_DIR / "uploads"
RESULT_DIR = BASE_DIR / "results"
HISTORY_PATH = RESULT_DIR / "history.json"
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".mp4", ".flac", ".ogg", ".aac"}

UPLOAD_DIR.mkdir(exist_ok=True)
RESULT_DIR.mkdir(exist_ok=True)

MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "turbo")
MODEL_DEVICE = os.getenv("WHISPER_DEVICE", "cuda")
MODEL_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float16")


class JobState(BaseModel):
    id: str
    filename: str
    status: str = "queued"
    progress: int = 0
    progress_ratio: float = 0.0
    stage: str = "Waiting"
    error: Optional[str] = None
    detected_language: Optional[str] = None
    language_probability: Optional[float] = None
    task: str = "translate"
    text: str = ""
    txt_path: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    elapsed_seconds: Optional[float] = None
    audio_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    processed_seconds: float = 0.0
    segments: List[Dict[str, Any]] = Field(default_factory=list)


app = FastAPI(title="Local Whisper Web")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

jobs: Dict[str, JobState] = {}
jobs_lock = threading.Lock()
history_lock = threading.Lock()
model_lock = threading.Lock()
model_instance: Optional[WhisperModel] = None


def get_model() -> WhisperModel:
    global model_instance
    with model_lock:
        if model_instance is None:
            model_instance = WhisperModel(
                MODEL_SIZE,
                device=MODEL_DEVICE,
                compute_type=MODEL_COMPUTE_TYPE,
            )
        return model_instance


def format_timestamp(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours:02d}:{minutes:02d}:{secs:05.2f}"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def seconds_between(started_at: Optional[str], finished_at: Optional[str]) -> Optional[float]:
    if not started_at or not finished_at:
        return None

    try:
        start = datetime.fromisoformat(started_at)
        end = datetime.fromisoformat(finished_at)
        return max(0.0, (end - start).total_seconds())
    except ValueError:
        return None


def get_audio_duration(audio_path: Path) -> Optional[float]:
    try:
        with av.open(str(audio_path), mode="r", metadata_errors="ignore") as container:
            if container.duration is not None:
                return float(container.duration / av.time_base)

            stream = next((stream for stream in container.streams if stream.type == "audio"), None)
            if stream and stream.duration is not None and stream.time_base is not None:
                return float(stream.duration * stream.time_base)
    except Exception:
        return None
    return None


def load_history() -> Dict[str, JobState]:
    if not HISTORY_PATH.exists():
        return {}

    try:
        raw_items = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        return {item["id"]: JobState(**item) for item in raw_items}
    except Exception:
        return {}


def save_history() -> None:
    with history_lock:
        items = sorted(jobs.values(), key=lambda item: item.created_at, reverse=True)
        HISTORY_PATH.write_text(
            json.dumps([item.model_dump() for item in items], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def update_job(job_id: str, save: bool = False, **changes: Any) -> None:
    with jobs_lock:
        job = jobs[job_id]
        for key, value in changes.items():
            setattr(job, key, value)
    if save:
        save_history()


def build_progress(processed_seconds: float, duration_seconds: Optional[float]) -> Dict[str, Any]:
    if duration_seconds and duration_seconds > 0:
        ratio = max(0.0, min(processed_seconds / duration_seconds, 0.99))
        progress = max(8, min(99, int(ratio * 100)))
        stage = f"Processed {processed_seconds:.1f}s / {duration_seconds:.1f}s"
    else:
        ratio = 0.0
        progress = 12
        stage = "Processing segments"
    return {"progress": progress, "progress_ratio": ratio, "stage": stage}


def process_audio(job_id: str, audio_path: Path, task: str) -> None:
    try:
        duration_seconds = get_audio_duration(audio_path)
        started_at = now_iso()
        update_job(
            job_id,
            status="processing",
            progress=3,
            progress_ratio=0.03,
            stage="Loading model",
            started_at=started_at,
            duration_seconds=duration_seconds,
        )
        model = get_model()

        update_job(job_id, progress=6, progress_ratio=0.06, stage="Running Whisper")
        segments_iter, info = model.transcribe(
            str(audio_path),
            beam_size=5,
            task=task,
            vad_filter=True,
        )

        update_job(
            job_id,
            progress=8,
            progress_ratio=0.08,
            stage="Language detected",
            detected_language=info.language,
            language_probability=float(info.language_probability),
        )

        segments: List[Dict[str, Any]] = []
        lines: List[str] = []
        collected_text: List[str] = []
        processed_seconds = 0.0

        for index, segment in enumerate(segments_iter, start=1):
            text = segment.text.strip()
            if text:
                collected_text.append(text)

            processed_seconds = max(processed_seconds, float(segment.end))
            item = {
                "index": index,
                "start": segment.start,
                "end": segment.end,
                "start_label": format_timestamp(segment.start),
                "end_label": format_timestamp(segment.end),
                "text": text,
            }
            segments.append(item)
            lines.append(f"[{item['start_label']} -> {item['end_label']}] {text}")

            progress_update = build_progress(processed_seconds, duration_seconds)
            update_job(
                job_id,
                processed_seconds=processed_seconds,
                segments=segments.copy(),
                **progress_update,
            )

        final_text = "\n".join(collected_text).strip()
        txt_path = RESULT_DIR / f"{job_id}-{audio_path.stem}-{task}.txt"
        txt_path.write_text("\n".join(lines), encoding="utf-8")
        finished_at = now_iso()

        update_job(
            job_id,
            status="completed",
            progress=100,
            progress_ratio=1.0,
            stage="Completed",
            text=final_text,
            txt_path=str(txt_path),
            segments=segments,
            processed_seconds=processed_seconds,
            finished_at=finished_at,
            elapsed_seconds=seconds_between(started_at, finished_at),
            save=True,
        )
    except Exception as exc:
        finished_at = now_iso()
        update_job(
            job_id,
            status="failed",
            progress=100,
            progress_ratio=1.0,
            stage="Failed",
            error=str(exc),
            finished_at=finished_at,
            elapsed_seconds=seconds_between(jobs[job_id].started_at, finished_at),
            save=True,
        )


@app.on_event("startup")
def startup() -> None:
    history_jobs = load_history()
    with jobs_lock:
        jobs.update(history_jobs)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/history", response_class=HTMLResponse)
def history_page() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "history.html").read_text(encoding="utf-8"))


@app.post("/api/jobs")
async def create_job(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    task: str = "translate",
) -> Dict[str, str]:
    if task not in {"translate", "transcribe"}:
        raise HTTPException(status_code=400, detail="task must be 'translate' or 'transcribe'")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in AUDIO_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    job_id = uuid.uuid4().hex
    safe_name = Path(file.filename or f"{job_id}{suffix}").name
    upload_path = UPLOAD_DIR / f"{job_id}-{safe_name}"
    upload_path.write_bytes(await file.read())

    job = JobState(
        id=job_id,
        filename=safe_name,
        task=task,
        created_at=now_iso(),
        audio_path=str(upload_path),
    )
    with jobs_lock:
        jobs[job_id] = job
    save_history()

    background_tasks.add_task(process_audio, job_id, upload_path, task)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> JobState:
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job


@app.get("/api/history")
def get_history() -> List[JobState]:
    with jobs_lock:
        items = sorted(jobs.values(), key=lambda item: item.created_at, reverse=True)
        return items


@app.get("/api/jobs/{job_id}/download")
def download_result(job_id: str) -> FileResponse:
    with jobs_lock:
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        if job.status != "completed" or not job.txt_path:
            raise HTTPException(status_code=400, detail="Result not ready")
        txt_path = Path(job.txt_path)

    return FileResponse(path=txt_path, filename=txt_path.name, media_type="text/plain")
