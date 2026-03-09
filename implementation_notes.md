# Implementation Notes

## Bug Fixes in Existing Code

### models/db.py
1. **Removed `from tkinter import NONE`** — This was being used as the default for `Todo.cal_event_client_suggestion_id`. Replaced with Python's built-in `None`.
2. **Fixed relationship string typos:**
   - `CalendarEvent.cal_event_client_suggestions` had `relationship("CalenderEventClientSuggestions", ...)` — fixed to `"CalendarEventClientSuggestion"` (typo in class name + incorrect pluralization).
   - `CalendarEventClientSuggestion.todos` had `relationship("Todos", ...)` — fixed to `"Todo"`.
3. **Fixed `Client.location` column:** Was defined as `nullable=False` with `default=None`, which would cause a database error. Changed to `nullable=True`.
4. **Removed unused imports:** Cleaned up `Index`, `text`, `event` from sqlalchemy imports that were not used.

### routers/todos.py (pre-existing file)
5. **Removed non-existent fields from `TodoResponse`:** The previous `TodoResponse` schema referenced `parent_todo_id`, `gcal_source_event_link`, and `user_confirmed` — none of which exist on the `Todo` database model. These would have caused runtime serialization errors. Replaced with a schema that matches the actual model.

## Model Changes

6. **Renamed `Client.archive` → `Client.archived`** — The design doc consistently uses `archived` (e.g., "set `Client.archived = True`"). Renamed the column to match. **Note:** If there is existing data, an Alembic migration will be needed to rename this column.

7. **Added `Error` model** — New table `errors` for the error logging system. Fields: `endpoint`, `method`, `error_type`, `error_message`, `traceback_str`, `context`. Inherits `id`, `created_at`, `updated_at` from `Base`.

8. **Added `MeetingType` enum** to `models/constants.py` — Used by OpenAI meeting classification to determine which type of todo to create. Values: `NEW_PATIENT_CONSULTATION`, `FOLLOW_UP_CONSULTATION`, `OTHER`.

## Architecture Decisions

9. **`CalendarEventClientSuggestion` created for ALL calendar events** — The design doc only explicitly mentions creating a `CalendarEventClientSuggestion` for unmatched clients (section 1A, step 3). However, I create one for matched clients as well, because:
   - It provides a consistent link between `CalendarEvent` → `Client` for all events
   - The todo confirmation logic (section 5B) relies on `CalendarEventClientSuggestion.user_confirmed` to determine if a todo is "confirmed"
   - Without it, todos from matched events would have no `cal_event_client_suggestion_id`, making them indistinguishable from manually-created todos

10. **Manually created clients have `user_confirmed=True`** — The design doc doesn't explicitly state this for the `POST create_client` endpoint, but it's the logical default since the user is explicitly creating the client.

11. **Manually created todos have `source=TodoSource.MANUAL`** — The `POST /todos/` endpoint always sets `source="manual"` since it represents user-created todos. The `source` field is not exposed in the `CreateTodoRequest` to prevent misuse.

12. **Todo "confirmed" status is derived, not stored** — Per section 5B, a todo is "confirmed" if its associated `CalendarEventClientSuggestion` is either `None` (not from calendar flow) or has `user_confirmed=True`. This is computed via a join query rather than storing a redundant `user_confirmed` field on `Todo`.

## New Files Created

| File | Purpose |
|------|---------|
| `schemas.py` | All Pydantic request/response models with `from_model` classmethods |
| `utils/openai_helpers.py` | OpenAI helper functions for client matching, contact extraction, meeting classification |
| `utils/error_logging.py` | `@log_error_to_db` decorator and `log_background_error` helper |
| `routers/n8n_ingestion.py` | N8N calendar ingestion endpoints (`/n8n/filter-events`, `/n8n/process-events`) |
| `routers/clients.py` | Client CRUD endpoints (`/clients/`) |
| `routers/calendar_suggestions.py` | Calendar suggestion endpoints (`/calendar-suggestions/`) |
| `utils/todo_builder.py` | `build_todos_from_client_meeting` — shared todo generation logic |

## Post-Design Adjustments

15. **`CalendarEventClientSuggestion.client_id` is nullable** — If the LLM cannot determine a first/last name from the calendar event, no `Client` is created and `client_id` is set to `None` on the suggestion. The `ClientMatchResult` schema now allows `first_name` and `last_name` to be null. Todo titles will use "Unknown" as the name in this case.

16. **Idempotent event processing** — Added `ProcessingState` enum (`IN_PROGRESS`, `COMPLETE`, `ERROR`) and a `processing_state` column on `CalendarEvent`. The `/n8n/filter-events` route returns errored event IDs alongside truly new ones, so N8N can retry failures. `_process_single_event` reuses the existing `CalendarEvent` row on retry instead of creating a duplicate. The `Error` model now has an optional `calendar_event_id` FK so errors from background processing are linked to the relevant calendar event.

17. **No todos created without a client** — During `process_events`, if the pipeline cannot resolve a `client_id` (no name extracted and no match found), the `CalendarEventClientSuggestion` is still created with `client_id=None` but no todos are generated. Todos are only created upon `confirm_suggestion` when a client is provided.

18. **`confirm_suggestion` regenerates todos** — On confirmation, all existing todos for the suggestion are deleted and regenerated using the (possibly replaced) client. This ensures todos always reflect the confirmed client. If both the suggestion's `client_id` and `replacement_client_id` are `None`, a 400 error is returned.

19. **`_build_todo_for_meeting` → `build_todos_from_client_meeting`** — Renamed and moved to `utils/todo_builder.py` for reuse across `n8n_ingestion.py` and `calendar_suggestions.py`. Now returns `list[Todo]` for future extensibility. Later refactored to be template-driven (see #20).

20. **Template-driven todo creation** — `build_todos_from_client_meeting` now queries `MeetingTypeTodoTemplates` from the DB instead of using hardcoded logic. Templates are filtered by `meeting_type` and ordered by `order`. Each template's `days_until_due` is added to `today` to compute the todo's `due_date`. The function is now async and requires a `db` session parameter. The old hardcoded titles/notes and `_estimate_duration_minutes` helper were removed.

## Dependencies Added

13. **`openai>=1.0.0`** added to `pyproject.toml` — Required for the OpenAI API calls in the calendar ingestion flow.

14. **`OPENAI_API_KEY`** added to `EnvVarName` enum — Must be set in `.env` file.

## API Route Summary

### N8N Ingestion (`/n8n`)
- `POST /n8n/filter-events` — Returns which event IDs are new (not yet in DB)
- `POST /n8n/process-events` — Queues events for background processing (client matching + todo creation)

### Clients (`/clients`)
- `GET /clients/` — List non-archived clients (optional `user_confirmed` filter)
- `POST /clients/` — Create a new client
- `PATCH /clients/{id}` — Update client fields
- `POST /clients/{id}/archive` — Archive a client

### Calendar Suggestions (`/calendar-suggestions`)
- `GET /calendar-suggestions/` — List unconfirmed suggestions with client + todos
- `POST /calendar-suggestions/{id}/confirm` — Confirm a suggestion (with optional client replacement)

### Todos (`/todos`)
- `GET /todos/confirmed` — List confirmed todos (optional `due_before_or_on`, `is_completed` filters)
- `GET /todos/{id}` — Get a single todo
- `POST /todos/` — Create a todo manually
- `PATCH /todos/{id}` — Update todo fields
- `POST /todos/{id}/complete` — Mark a todo complete
- `POST /todos/{id}/change-due-date` — Change a todo's due date
- `DELETE /todos/{id}` — Delete a todo
