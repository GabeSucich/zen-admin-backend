import os

from dotenv import load_dotenv
load_dotenv(dotenv_path=".env")

from fastapi import Depends, FastAPI
from fastapi.routing import APIRoute

from routers.auth import require_auth, router as auth_router
from routers.todos import router as todos_router
from routers.clients import router as clients_router
from routers.calendar_suggestions import router as calendar_suggestions_router
from routers.meeting_notes import router as meeting_notes_router
from routers.meeting_types import router as meeting_types_router
from routers.meeting_type_todo_templates import router as meeting_type_todo_templates_router
from routers.n8n_ingestion import router as n8n_router
from routers.errors import router as error_router
from fastapi.middleware.cors import CORSMiddleware 

def generate_operation_id(route: APIRoute) -> str:
    return route.name

app = FastAPI(generate_unique_id_function=generate_operation_id)

origins = [                                                                                                                                                                        
      "http://localhost:5173",                              
      os.getenv("ZEN_ADMIN_FRONTEND_URL", ""),  # set in prod env
  ]

app.include_router(auth_router)
app.include_router(todos_router, dependencies=[Depends(require_auth)])
app.include_router(clients_router, dependencies=[Depends(require_auth)])
app.include_router(calendar_suggestions_router, dependencies=[Depends(require_auth)])
app.include_router(meeting_types_router, dependencies=[Depends(require_auth)])
app.include_router(meeting_type_todo_templates_router, dependencies=[Depends(require_auth)])
app.include_router(n8n_router, dependencies=[Depends(require_auth)])
app.include_router(meeting_notes_router, dependencies=[Depends(require_auth)])
app.include_router(error_router, dependencies=[Depends(require_auth)])

app.add_middleware(
      CORSMiddleware,
      allow_origins=[o for o in origins if o],
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )