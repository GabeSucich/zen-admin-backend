# Zen Admin Backed Design

## Architecture components
This section defines the components of the larger system in which this backend exists.

1. N8N
Tool used for ingesting daily events from calendar and creating backend records via API

2. Zen Admin Frontend
UI for viewing and managing todos and clients in the backend

3. Zen Admin Backend (this component)
Data storage and management server. FastAPI server with SQLAlchemy Postgres db management.

## Data Models
An initial implementation of all necessary data models for this app are present in `zen_admin_backend/models/db.py` (enums in `zen_admin_backend/models/constants.py`). During implementation, if you see any flaws in the model, you may make edits, but please document them (more on documentation below).

## Intended Data Flow
This section describes how data is intended to flow, and will reference the existing data models.

**IMPORTANT**: In the description below, there will be places that I annotate with an `(API ROUTE)` tag. This indicates that I imagine we should have a distinct backend api route implemented to handle this.

### 1. N8N ingests calendar data on a daily basis
1. N8N will bring in all data from google calendar at a fixed time each day.
2. First, N8N will ingest all calendar events from the last 24 hours
3. Next, N8N will send a request with an array of `eventId` values from all the events `(API ROUTE)`. This route will return all eventIds for which a `CalendarEvent` object DOES NOT exist in the database. This will help us avoid duplicates.
4. Next, for all calendar events that are net new, N8N will send a request to the backend to create todos for calendar events in bulk `(API ROUTE)`. The logic for this creation is described in sections below.

**IMPORTANT:** The process below should happen as a background task that is handled asynchronously after the request is sent. We should return a response to N8N immediately afterward. We can use `BackgroundTasks` (FastAPI builtin) for this. 

#### 1A. Calendar Event Client Matching
N8N will send an API request containg data for new calendar events to be processed. This request will containg the following data:
* The calendar event ID (string)
* The calendar title (string)
* The calendar attendee names (list of strings)
* The calendar data as json

**IMPORTANT:** For all calls to OpenAI API, we should use a `pydantic` response model, and wrap the call in it's own helper function rather than defining it in the body of another function.

Processing logic will occur as follows:
1. We will create a `CalendarEvent` record in the DB.
2. We will pull all `Client` objects from the database where `user_confirmed` is True. 
    * We will parse out 2 values from all these records -- id and name -- and order them into an array of objects
    * We will the make a request to openAI that includes this array, and the attendees and title for of th emeeting.
    * Our prompt will indicate that this is the data for a meeting between a provider named Doctor Bex and a client. We want to find the best match from the array of existing clients for the client in the meeting. If there is not a good match, it is preferable to return no match.
    * We will provide the meeting title and the list of attendees
    * We will ask the LLM to return the following data structure:
        - `first_name`: str
        - `last_name`: str
        - `client_id`: int | None (Defined if the a match was found from the array, otherwise None)
3. If the API call above returns a client ID, then we will store that. If it does not return a clientID, then we will do the following:
    * We will call OpenAI with a new prompt that says we are trying to extract all as much of the following information from the google calendar event data as possible:
        - `email`: str | None
        - `phone`: str | None
    * We will then use the information that we have to create a `Client` in the db with `user_confirmed=False` and `source="auto"`
    * We will create a `CalendarEventClientSuggestion` with `client_id` pointing to that ID, and `user_confirmed`=`False`
4. If any of the API calls fail, we will create a `Todo` in the `title`=`"Calender Event Review Required"`, `todo_type`=`MANUAL_EVENT_REVIEW`, and a note indicating `Automated calendar event processing failed. Please review calendar event https://www.google.com/calendar/event?eid={eventId}`, where we string interpolate the eventId from the request. This should have a due date of the current day.
5. If we hit the failure case in step (4), we will be done. Otherwise, we will move on to section 1B below.

#### 1B: Calendar Event Todo Creation
The process above will have given us a `client_id` for a Client in the database for each calendar event. The next step is to create todos for this. For the time being, here is our mapping of calendar events to Todos:
1. New patient consultations will map to a todo with `todo_type`=`NEW_CLIENT_ONBOARDING`:
    - title: `New Client Onboarding: {Full Name}`
    - notes: A newline formatted list with reminders to: Add patient to charm, Review client data in dashboard, Send intake forms, Add stripe invoicing for clients on membership, Add any consult-specific todos manually in dashboard.
2. For follow up consultations, a todo with `todo_type`=`Consultation Billing Review`:
    - title: `Consultation Billing Review: {Full Name}
    - notes: If {Full Name} is not on membership program, be sure to invoice them for {meeting duration minutes} minute consultation on {meeting data}
3. All other consultations, a todo with `todo_type`=`GENERAL`:
    - title: `Review: {meeting title}`
    - notes: Add any todos from the meeting with {Full name} on {Meeting date}

The OpenAI Api should be called to extract the meeting type enum from the meeting title and data, and then logic should be used to create the `Todo` in the database. ALL TODOS CREATED FROM THIS FLOW MUST HAVE `user_confirmed`=`False`.

### 2. User interaction with Todos from dashboard
The process above will create todos for the user to review in the database. The backend must also be able to provide logic for the following user interactions with data:

#### 2A. Fetch and edit all non-archived `Client` data
1. `(API ROUTE)` Fet for all Client objects where `archived=False`. Should have an optional query param that is a `user_confirmed` boolean. If this provided, only return clients where `user_confirmed` matches that value. Otherwise, return all clients.

#### 2B. Edit `Client` data
We need the ability to edit a client's data:

`(API ROUTE)` PATCH for existing `Client`. THis should be a route that allows a client's data to be updated. Specifically, the following fields should be exposted for update, and we should only overwrite them if they are present in the request:
    * first_name
    * last_name
    * email
    * phone
    * notes
    * address
    * location
    * membership_status
    * charm_id
`(API ROUTE)` POST archive client. This will set `Client.archived = True`.

#### 3B: Create `Client`

`(API ROUTE)` POST create_client: Allows the user to create a client. All optional fields can be passed and are opportunistically saved, but not required.

#### 4B: Fetch and edit all non-user-confirmed `CalendarEventClientSuggestion` data

* `(API ROUTE)` GET for all `user_confirmed=False` `CalendarEventClientSuggestion` objects. This data needs to have the attached `Client` object, as well as all associated `Todos`
* `(API ROUTE)` POST confirm_calendar_client_event_suggestion. This request will confirm a calendar event suggestion. It will have an optional request body field called `replacement_client_id`. The logic will be as follows:
    1. If there is no `replacement_client_id`, we will set `user_confirmed=True` on the existing `CalendarEventClientSuggestion` object and associated `Client`.
    2. If there is a `replacement_client_id`, we will:
        1. Fetch all `Todos` of the `CalendarEventClientSuggestion` object and updated `client_id` on them to point to the `replacement_client_id`.
        2. Update `user_confirmed` on the `CalendarEventClientSuggestion` to True.
        3. If the `Client` that the `CalendarEventClientSuggestion` is pointing to has `user_confirmed=True`, do nothing. If `user_confirmed=False`, set `archived=True` on the `Client`.

#### 5B: Fetch and edit all confirmed Todos

* `(API ROUTE)` GET get_confirmed_todos This should return all `Todo` objects where either the associated `CalendarEventClientSuggestion` is None, or is defined by `user_confirmed`=True. This should also take two optional params:
    * "due_before_or_on": str | None: If defined, this is a date in form YYYY-MM-DD. We should return `Todo` objects where due_date is before or on this date.
    * "is_completed": bool | None: If True, only return `Todo` objects where `completed_at` is defined. If False, only return `Todo` objects where `complted_at` is not defined. Otherwise, return all `Todos`
* `(API ROUTE)` POST mark_todo_complete This should take a `Todo` ID and updated `completed_at` with the current date
* `(API ROUTE)` POST change_due_date: This should take an argument for the new due date in form YYYY-MM-DD and update the todo with that value
* `(API ROUTE)` DELETE This should delete a todo

## Error Handling
1. Create a generic `Error` database model that has information we would want for errors.
2. For all endpoints, create a decorator that wraps the endpoint in a try-catch that logs error information to the database. You should still raise any exceptions from this decorator so that they are not silenced.
3. For Background tasks, any unhandled exceptions should be caught and logged to the database as well

# Instructions

## Goal
You, Claude, are my implementer. The goal of this document is to give you all the knowledge in order to do a first pass at implementing this backend.

## General Steps
1. Implement the API handlers for the automated calendar ingestion in their own router. Tag this as `N8nIngestion`
2. Implement the API handlers for user interaction in whatever hierarchy of routers you see as most intuitive.
3. Do a pass for any possible refactoring after your initial implementation

## General Practices and Guidelines
Here are a list of general practices and guidelines that you should adhere to:
1. Reuse pydantic models on API response types. If different APIs are return `Todos` at some level of the data nesting, this should use the same model.
2. Define conversions of DB model to Pydantic model as `@classmethod from_model` definitions on `pydantic` models, so that these conversions appear more concise in the body of handlers.


