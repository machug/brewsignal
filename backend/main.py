from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: init DB, start scanner
    print("Starting Tilt UI...")
    yield
    # Shutdown: stop scanner
    print("Shutting down Tilt UI...")


app = FastAPI(title="Tilt UI", version="0.1.0", lifespan=lifespan)


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


# Mount static files (Svelte build output)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
