export interface ObjectItem {
  id: string;
  name: string;
  description: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  sensor_count: number;
  online_sensor_count: number;
}

export interface SensorItem {
  id: string;
  name: string;
  mqtt_topic: string;
  current_temperature: number | null;
  last_message_at: string | null;
  offline_timeout_seconds: number;
  is_active: boolean;
  icon: string;
  display_order: number;
  calibration_offset: number;
  object_id: string;
  created_at: string;
  updated_at: string;
}

export type UserRole = "admin" | "serwisant" | "user";

export interface UserItem {
  id: string;
  username: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  object_ids: string[];
}

export interface UserCreate {
  username: string;
  email: string;
  full_name?: string;
  password: string;
  role: UserRole;
  object_ids?: string[];
}

export interface UserUpdate {
  email?: string;
  full_name?: string;
  role?: UserRole;
  is_active?: boolean;
  object_ids?: string[];
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: UserItem;
}

export interface NotificationProfileItem {
  id: string;
  name: string;
  object_id: string;
  created_at: string;
  updated_at: string;
}

export type NotificationChannel =
  | "telegram"
  | "fcm"
  | "email"
  | "sms"
  | "webhook";

export interface NotificationEndpointItem {
  id: string;
  channel: NotificationChannel;
  label: string;
  config: Record<string, unknown>;
  is_enabled: boolean;
  profile_id: string;
  created_at: string;
  updated_at: string;
}

export interface NotificationEndpointCreate {
  channel: NotificationChannel;
  label?: string;
  config?: Record<string, unknown>;
  is_enabled?: boolean;
}

export interface NotificationEndpointUpdate {
  label?: string;
  config?: Record<string, unknown>;
  is_enabled?: boolean;
}

export interface MeasurementItem {
  id: string;
  temperature: number;
  received_at: string;
  sensor_id: string;
}

export interface AlarmItem {
  id: string;
  alarm_type: string;
  status: string;
  trigger_value: number | null;
  detected_at: string;
  triggered_at: string | null;
  acknowledged_at: string | null;
  resolved_at: string | null;
  description: string;
  object_id: string;
  sensor_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlarmConfigItem {
  id: string;
  alarm_type: string;
  threshold_value: number | null;
  trigger_delay_seconds: number;
  is_enabled: boolean;
  sensor_id: string;
  created_at: string;
  updated_at: string;
}

export interface AlarmConfigCreate {
  alarm_type: "high_temperature" | "low_temperature" | "offline";
  threshold_value: number | null;
  trigger_delay_seconds: number;
  is_enabled: boolean;
}

export interface AlarmConfigUpdate {
  threshold_value?: number | null;
  trigger_delay_seconds?: number;
  is_enabled?: boolean;
}

export interface ObjectCreate {
  name: string;
  description?: string;
}

export interface ObjectUpdate {
  name?: string;
  description?: string;
  is_active?: boolean;
}

export interface SensorCreate {
  name: string;
  mqtt_topic: string;
  offline_timeout_seconds?: number;
  icon?: string;
  calibration_offset?: number;
}

export interface SensorUpdate {
  name?: string;
  mqtt_topic?: string;
  offline_timeout_seconds?: number;
  is_active?: boolean;
  icon?: string;
  display_order?: number;
  calibration_offset?: number;
}

export interface WsEvent {
  event: string;
  data: Record<string, unknown>;
}

export type ChartRange = "LIVE" | "1H" | "24H" | "7D";
