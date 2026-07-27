export interface ObjectItem {
  id: string;
  name: string;
  description: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  sensor_count?: number;
}

export interface SensorItem {
  id: string;
  name: string;
  mqtt_topic: string;
  current_temperature: number | null;
  last_message_at: string | null;
  offline_timeout_seconds: number;
  is_active: boolean;
  object_id: string;
  created_at: string;
  updated_at: string;
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
}

export interface SensorUpdate {
  name?: string;
  mqtt_topic?: string;
  offline_timeout_seconds?: number;
  is_active?: boolean;
}

export interface WsEvent {
  event: string;
  data: Record<string, unknown>;
}

export type ChartRange = "LIVE" | "1H" | "6H" | "24H" | "7D" | "CUSTOM";
