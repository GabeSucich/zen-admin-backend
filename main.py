from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

from fastapi import Depends, FastAPI

from routers.auth import require_auth, router as auth_router
from routers.todos import router as todos_router
from routers.clients import router as clients_router
from routers.calendar_suggestions import router as calendar_suggestions_router
from routers.n8n_ingestion import router as n8n_router

app = FastAPI()

app.include_router(auth_router)
app.include_router(todos_router, dependencies=[Depends(require_auth)])
app.include_router(clients_router, dependencies=[Depends(require_auth)])
app.include_router(calendar_suggestions_router, dependencies=[Depends(require_auth)])
app.include_router(n8n_router, dependencies=[Depends(require_auth)])
