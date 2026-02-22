from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from api.routes.tasks import router as tasks_router


load_dotenv()

app = FastAPI(title="PBL Studio V4 API")
app.include_router(tasks_router, prefix="/api")

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/debug", response_model=None)
def debug_page() -> FileResponse | RedirectResponse:
    path = STATIC_DIR / "debug.html"
    if path.exists():
        return FileResponse(path)
    return RedirectResponse(url="/")
