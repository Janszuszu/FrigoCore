"""FrigoCore — Domain Enums."""

from enum import Enum


class UserRole(str, Enum):
    """System user role."""

    ADMIN = "admin"  # Full access: objects, sensors, alarms, MQTT, notifications, users, integrations — can edit
    SERWISANT = "serwisant"  # Read access to every object's dashboard + alarms, can acknowledge alarms, no editing
    KIEROWNIK = "kierownik"  # Service manager — top escalation tier, receives dispatches like a serwisant plus escalations
    USER = "user"  # Read access to only the objects assigned to them (dashboard + alarms), no editing


class AlarmType(str, Enum):
    """Types of alarms supported by the system."""

    HIGH_TEMPERATURE = "high_temperature"
    LOW_TEMPERATURE = "low_temperature"
    OFFLINE = "offline"


class AlarmStatus(str, Enum):
    """Lifecycle status of an alarm.

    PENDING → TRIGGERED → ACKNOWLEDGED → EN_ROUTE → RESOLVED → ARCHIVED

    A technician declining an assignment does NOT change alarm status — the
    alarm stays TRIGGERED and the escalation engine reassigns immediately.
    """

    PENDING = "pending"  # Condition detected, delay timer running
    TRIGGERED = "triggered"  # Active alarm — requires service action / dispatch
    ACKNOWLEDGED = "acknowledged"  # Assigned technician accepted responsibility
    EN_ROUTE = "en_route"  # Technician is travelling to the site
    RESOLVED = "resolved"  # Condition cleared / service issue resolved
    ARCHIVED = "archived"  # Hidden from the default history, retained for chart evidence


class NotificationChannel(str, Enum):
    """Delivery channels for alarm notifications."""

    TELEGRAM = "telegram"
    FCM = "fcm"  # Firebase Cloud Messaging (push)
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"


class AssignmentOutcome(str, Enum):
    """Result of a single dispatch attempt (AlarmAssignment)."""

    PENDING = "pending"  # Dispatched, awaiting response
    ACCEPTED = "accepted"  # Target accepted — alarm moves to ACKNOWLEDGED
    DECLINED = "declined"  # Target declined — immediate escalation
    EXPIRED = "expired"  # Timeout elapsed with no response — escalation


class EscalationTargetType(str, Enum):
    """What an EscalationTier dispatches to."""

    USER = "user"  # A specific technician (target_user_id)
    ROLE = "role"  # Any active user holding target_role


class DevicePlatform(str, Enum):
    """Platform of a registered push-notification device."""

    ANDROID = "android"
    IOS = "ios"


class AlarmEventType(str, Enum):
    """Explicit, closed set of audit-trail event types for AlarmEvent.

    Keeping this closed (rather than free-form strings scattered through the
    codebase) is what makes the event history reliably machine-readable.
    """

    ALARM_TRIGGERED = "alarm_triggered"
    ASSIGNMENT_CREATED = "assignment_created"
    NOTIFICATION_SENT = "notification_sent"
    NOTIFICATION_DELIVERED = "notification_delivered"
    ASSIGNMENT_ACCEPTED = "assignment_accepted"
    ASSIGNMENT_DECLINED = "assignment_declined"
    ASSIGNMENT_EXPIRED = "assignment_expired"
    ESCALATED = "escalated"
    ESCALATION_EXHAUSTED = "escalation_exhausted"  # No further tiers configured
    ALARM_ACKNOWLEDGED = "alarm_acknowledged"
    ALARM_EN_ROUTE = "alarm_en_route"
    CLIENT_NOTIFIED = "client_notified"
    ALARM_RESOLVED = "alarm_resolved"
    ALARM_ARCHIVED = "alarm_archived"
