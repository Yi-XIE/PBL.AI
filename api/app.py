from fastapi import FastAPI

from api.routes.tasks import router as tasks_router


app = FastAPI(title="PBL Studio V4 API")
app.include_router(tasks_router, prefix="/api")
