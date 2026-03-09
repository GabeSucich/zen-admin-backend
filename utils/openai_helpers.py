from openai import AsyncOpenAI
from pydantic import BaseModel

from models.constants import MeetingType
from utils.env_vars import EnvVarName, load_env_var

openai_client = AsyncOpenAI(api_key=load_env_var(EnvVarName.OPENAI_API_KEY))


class CancellationCheckResult(BaseModel):
    is_cancellation: bool


async def check_if_cancellation(meeting_title: str) -> CancellationCheckResult:
    """Check if a meeting title indicates a cancelled appointment."""
    response = await openai_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Determine if this meeting title indicates a cancelled or rescheduled appointment. "
                    "Look for keywords like 'cancelled', 'canceled', 'cancellation', 'rescheduled', "
                    "'no show', 'no-show', or similar indicators. "
                    "Return true if the meeting appears to be cancelled, false otherwise."
                ),
            },
            {
                "role": "user",
                "content": f"Meeting title: {meeting_title}",
            },
        ],
        response_format=CancellationCheckResult,
    )
    return response.choices[0].message.parsed


class ClientNameResult(BaseModel):
    first_name: str | None
    last_name: str | None


async def extract_client_name(meeting_title: str) -> ClientNameResult:
    """Extract the client's name from a meeting title."""
    response = await openai_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are extracting the client's name from a meeting title. "
                    "The meeting is between a healthcare provider named Doctor Bex and a client. "
                    "Extract the client's first and last name from the title. "
                    "Doctor Bex (or any variation like 'Dr. Bex', 'Bex') is the provider, not the client. "
                    "If the title contains another person's name, that is the client. "
                    "If you cannot determine a client name, return null for both fields."
                ),
            },
            {
                "role": "user",
                "content": f"Meeting title: {meeting_title}",
            },
        ],
        response_format=ClientNameResult,
    )
    return response.choices[0].message.parsed


class ClientEmailResult(BaseModel):
    email: str | None


async def extract_client_email(
    attendee_emails: list[str],
    client_first_name: str | None,
    client_last_name: str | None,
) -> ClientEmailResult:
    """Extract the client's email from the attendee list, ignoring the provider's email."""
    response = await openai_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are identifying a client's email from a list of meeting attendee emails. "
                    "The provider's email is drbex@zenforcewellness.com — NEVER return this email. "
                    "You may also be given the client's first and last name to help identify their email. "
                    "Return the single email address that most likely belongs to the client. "
                    "If you cannot determine which email belongs to the client, or the list is empty, "
                    "return null."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Client name: {client_first_name} {client_last_name}\n"
                    f"Attendee emails: {attendee_emails}"
                ),
            },
        ],
        response_format=ClientEmailResult,
    )
    return response.choices[0].message.parsed


class ClientMatchResult(BaseModel):
    client_id: int | None


async def match_client_to_existing(
    existing_clients: list[dict],
    client_email: str | None,
    client_first_name: str | None,
    client_last_name: str | None,
) -> ClientMatchResult:
    """Match a client name and/or email to existing clients."""
    response = await openai_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are matching a client to an existing client record in a database. "
                    "You will be given a client name (which may be null), a client email "
                    "(which may be null), and an array of existing clients "
                    "with their id, name, and email (email may be null).\n\n"
                    "Matching rules:\n"
                    "- If the client email exactly matches a client's email, that is a definite match.\n"
                    "- If the client name closely matches an existing client's name, that is a match.\n"
                    "- If there is not a good match, return null for client_id. "
                    "It is preferable to return no match than an incorrect match."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Client name: {client_first_name} {client_last_name}\n"
                    f"Client email: {client_email}\n\n"
                    f"Existing clients:\n{existing_clients}"
                ),
            },
        ],
        response_format=ClientMatchResult,
    )
    return response.choices[0].message.parsed


class MeetingTypeResult(BaseModel):
    meeting_type: MeetingType


async def classify_meeting_type(
    meeting_title: str,
    meeting_description: str | None,
) -> MeetingTypeResult:
    """Classify the meeting type from the title and description using OpenAI."""
    non_general_types = [mt.value for mt in MeetingType if mt != MeetingType.GENERAL]
    type_list = "\n".join(f"- '{mt}'" for mt in non_general_types)

    user_content = f"Meeting title: {meeting_title}"
    if meeting_description:
        user_content += f"\nMeeting description: {meeting_description}"

    response = await openai_client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Classify this meeting between a healthcare provider (Doctor Bex) and a client. "
                    "Try to match it to one of the following meeting types:\n"
                    f"{type_list}\n\n"
                    "If the meeting does not clearly match any of the above, return 'General'."
                ),
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
        response_format=MeetingTypeResult,
    )
    return response.choices[0].message.parsed
