from enum import StrEnum

class TodoSource(StrEnum):
    AUTO = "Auto"
    MANUAL = "Manual"

class TodoType(StrEnum):
    MANUAL_EVENT_REVIEW = "Manual Event Review"
    NEW_CLIENT_ONBOARDING = "New Client Onboarding"
    CONSULTATION_BILLING_REVIEW = "Consultation Billing Review"
    GENERAL = "General"

class Location(StrEnum):
    EVERGREEN = "Evergreen"
    CHICAGO = "Chicago"

class MeetingType(StrEnum):
    NEW_PATIENT_CONSULTATION = "New Patient Consultation"
    FOLLOW_UP_CONSULTATION = "Follow Up Consultation"
    PELLET_INSERTION = "Pellet Insertion"
    BOTOX_FILLER = "Botox and Filler"
    IV_THERAPY = "IV Therapy"
    GENERAL = "General"

class ProcessingState(StrEnum):
    IN_PROGRESS = "In Progress"
    COMPLETE = "Complete"
    ERROR = "Error"

class MembershipStatus(StrEnum):
    MEMBER = "Member"
    NON_MEMBER = "Non Member"
    GRANDFATHERED = "Grandfathered"
