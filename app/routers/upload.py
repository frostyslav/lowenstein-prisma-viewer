"""Upload API for .pcfg and .pdat files."""

import zipfile

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.parsers.archive_processor import process_pcfg, process_pdat

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("")
async def upload_archive(file: UploadFile, db: Session = Depends(get_db)) -> dict:
    """Upload a .pcfg or .pdat archive for processing."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    filename = file.filename.lower()
    if not filename.endswith((".pcfg", ".pdat")):
        raise HTTPException(
            status_code=400,
            detail="Only .pcfg and .pdat files are supported",
        )

    content = await file.read()

    try:
        if filename.endswith(".pcfg"):
            result = process_pcfg(db, content, file.filename)
        else:
            result = process_pdat(db, content, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (OSError, KeyError, zipfile.BadZipFile) as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}") from e

    return {"status": "ok", "filename": file.filename, **result}
