from openai import AsyncOpenAI
from pydantic import BaseModel

from models.constants import MeetingType
from utils.env_vars import EnvVarName, load_env_var

openai_client = AsyncOpenAI(api_key=load_env_var(EnvVarName.OPENAI_API_KEY))


class ClientMatchResult(BaseModel):
    first_name: str
    last_name: str
    client_id: int | None


async def match_client_from_meeting(
    existing_clients: list[dict],
    attendee_names: list[str],
    meeting_title: str,
) -> ClientMatchResult:
    """Match meeting attendees to existing clients using OpenAI."""
    response = await openai_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are helping match meeting attendees to existing clients. "
                    "This is a meeting between a provider named Doctor Bex and a client. "
                    "Given the meeting title and list of attendees, find the best match from "
                    "the array of existing clients. If there is not a good match, it is "
                    "preferable to return no match (client_id = null). "
                    "Always return the first_name and last_name of the client from the meeting."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Meeting title: {meeting_title}\n"
                    f"Attendees: {attendee_names}\n\n"
                    f"Existing clients:\n{existing_clients}"
                ),
            },
        ],
        response_format=ClientMatchResult,
    )
    return response.choices[0].message.parsed


class ContactInfoResult(BaseModel):
    email: str | None
    phone: str | None


async def extract_contact_info(calendar_data: dict) -> ContactInfoResult:
    """Extract contact information from calendar event data using OpenAI."""
    response = await openai_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract as much contact information as possible from this Google Calendar "
                    "event data. Look for email addresses and phone numbers in attendees, "
                    "description, location, or any other fields."
                ),
            },
            {
                "role": "user",
                "content": f"Calendar event data:\n{calendar_data}",
            },
        ],
        response_format=ContactInfoResult,
    )
    return response.choices[0].message.parsed


class MeetingTypeResult(BaseModel):
    meeting_type: MeetingType


async def classify_meeting_type(
    meeting_title: str,
    calendar_data: dict,
) -> MeetingTypeResult:
    """Classify the meeting type from calendar event data using OpenAI."""
    response = await openai_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Classify this meeting between a healthcare provider (Doctor Bex) and a client. "
                    "Determine if it is:\n"
                    "- 'New Patient Consultation': A first-time consultation with a new patient\n"
                    "- 'Follow Up Consultation': A follow-up visit with an existing patient\n"
                    "- 'Other': Any other type of meeting\n"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Meeting title: {meeting_title}\n"
                    f"Calendar data: {calendar_data}"
                ),
            },
        ],
        response_format=MeetingTypeResult,
    )
    return response.choices[0].message.parsed
