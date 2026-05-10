from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.production_endpoints import router as production_router

app = FastAPI(title="LLM Multi-Agent System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(production_router)


@app.get("/", include_in_schema=False)
async def root():
    return {"status": "ok", "service": "llm-multi-agent"}
