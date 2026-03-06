from enum import StrEnum

class TodoSource(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"

class TodoType(StrEnum):
    NEW_CLIENT_REVIEW = "New Client Review"
    FOLLOW_UP = "Follow Up"
    MANUAL = "Manual"

class Location(StrEnum):
    EVERGREEN = "Evergreen"
    CHICAGO = "Chicago"

class MembershipStatus(StrEnum):
    MEMBER = "Member"
    NON_MEMBER = "Non Member"
    GRANDFATHERED = "Grandfathered"
