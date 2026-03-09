import base64


def gcal_event_link(event_id: str, calendar_id: str = "drbex@zenforcewellness.com") -> str:
    split_id = event_id.split('@')[0]
    encoded = base64.b64encode(f"{split_id} {calendar_id}".encode()).decode().rstrip('=')
    return f"https://www.google.com/calendar/event?eid={encoded}"
