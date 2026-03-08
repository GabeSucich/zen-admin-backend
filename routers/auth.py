import asyncio

from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader
from fastapi_login import LoginManager
from utils.auth import verify_password
from database import async_session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models import User
from utils.env_vars import EnvVarName, load_env_var

manager = LoginManager(load_env_var(EnvVarName.SECRET), token_url="/auth/login")

N8N_API_KEY = load_env_var(EnvVarName.N8N_API_KEY)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

router = APIRouter(tags=["Auth"])

@manager.user_loader()
async def load_user(username: str):
    for attempt in range(3):
        try:
            async with async_session() as db:
                user_query = await db.execute(
                    select(User)
                    .where(User.username == username)
                )
                user: User | None = user_query.scalar_one_or_none()
                if user is None:
                    raise HTTPException(status_code=500, detail="Username was not recognized")
                return user
        except HTTPException:
            raise
        except Exception:
            if attempt == 2:
                raise
            await asyncio.sleep(2)

async def require_auth(request: Request, api_key: str | None = Security(api_key_header)):
    # Try API key first (n8n)
    if api_key is not None:
        if api_key != N8N_API_KEY:
            raise HTTPException(status_code=403, detail="Invalid API key")
        return None
    # Fall back to JWT token (user dashboard)
    user = await manager(request)
    return user

class LoginRequestData(BaseModel):
    username: str
    password: str

class LoginResponseData(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    token: str

@router.post("/login", operation_id="login", response_model=LoginResponseData)
async def login(data: LoginRequestData) -> LoginResponseData:
    user = await load_user(data.username)
    if not user or not verify_password(data.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    token = manager.create_access_token(data={"sub": user.username})
    return LoginResponseData(user_id=user.id, first_name=user.first_name, last_name=user.last_name, token=token)
