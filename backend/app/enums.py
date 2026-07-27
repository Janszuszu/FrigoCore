"""FrigoCore — Domain Enums."""

from enum import Enum


class UserRole(str, Enum):
    """System user role."""

    ADMIN = "admin"  # Full access: objects, sensors, alarms, MQTT, notifications, users, integrations
    CLIENT = "client"  # Dashboard + Alarms only, assigned to exactly one Object


class AlarmType(str, Enum):
    """Types of alarms supported by the system."""

    HIGH_TEMPERATURE = "high_temperature"
    LOW_TEMPERATURE = "low_temperature"
    OFFLINE = "offline"


class AlarmStatus(str, Enum):
    """Lifecycle status of an alarm."""

    PENDING = "pending"  # Condition detected, delay timer running
    TRIGGERED = "triggered"  # Active alarm — sent to notification profile
    ACKNOWLEDGED = "acknowledged"  # Seen by a user
    RESOLVED = "resolved"  # Condition cleared


class NotificationChannel(str, Enum):
    """Delivery channels for alarm notifications."""

    TELEGRAM = "telegram"
    FCM = "fcm"  # Firebase Cloud Messaging (push)
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"