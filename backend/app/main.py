from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import videos
from app.routers import phase1
from app.routers import phase2


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="InterScribe", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(videos.router)
app.include_router(phase1.router)
app.include_router(phase2.router)
