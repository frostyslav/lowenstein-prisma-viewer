"""Lowenstein Prisma CPAP Data Viewer — FastAPI application."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .routers import device, metrics, nights, scan, signals, upload

# Create all tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Lowenstein Prisma Viewer",
    version="0.1.0",
)

# CORS for local development (Vite dev server on :5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(upload.router)
app.include_router(scan.router)
app.include_router(signals.router)
app.include_router(nights.router)
app.include_router(device.router)
app.include_router(metrics.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


# Serve React frontend in production
# The built frontend is at /app/frontend/dist in the Docker image
FRONTEND_DIR = Path("/app/frontend/dist")
if FRONTEND_DIR.exists():
    # Serve static assets (JS, CSS, etc.)
    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_DIR / "assets")),
        name="assets",
    )

    # Catch-all: serve index.html for client-side routing
    @app.get("/{path:path}")
    async def serve_spa(path: str) -> FileResponse:
        """Serve the React SPA for client-side routing."""
        # If a static file exists, serve it
        file_path = FRONTEND_DIR / path
        if file_path.is_file():
            return FileResponse(file_path)
        # Otherwise serve index.html for React Router
        return FileResponse(FRONTEND_DIR / "index.html")
