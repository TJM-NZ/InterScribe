from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import videos
from app.routers import phase1
from app.routers import phase2
from app.routers import condensation


app = FastAPI(title="InterScribe")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(videos.router)
app.include_router(phase1.router)
app.include_router(phase2.router)
app.include_router(condensation.router)
