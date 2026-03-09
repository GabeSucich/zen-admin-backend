import traceback
import functools

from database import async_session
from models.db import Error


def log_error_to_db(func):
    """Decorator that logs endpoint errors to the database and re-raises them."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            try:
                async with async_session() as session:
                    error = Error(
                        endpoint=func.__name__,
                        method="ENDPOINT",
                        error_type=type(e).__name__,
                        error_message=str(e),
                        traceback_str=traceback.format_exc(),
                    )
                    session.add(error)
                    await session.commit()
            except Exception:
                pass  # Don't let error logging failures mask the original error
            raise
    return wrapper


async def log_background_error(task_name: str, error: Exception, *, calendar_event_id: int | None = None):
    """Log a background task error to the database."""
    try:
        async with async_session() as session:
            err = Error(
                endpoint=task_name,
                method="BACKGROUND_TASK",
                error_type=type(error).__name__,
                error_message=str(error),
                traceback_str=traceback.format_exc(),
                calendar_event_id=calendar_event_id,
            )
            session.add(err)
            await session.commit()
    except Exception:
        pass
