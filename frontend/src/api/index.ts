import type {
  AlarmConfigCreate,
  AlarmConfigItem,
  AlarmConfigUpdate,
  AlarmItem,
  NotificationEndpointCreate,
  NotificationEndpointItem,
  NotificationEndpointUpdate,
  NotificationProfileItem,
  ObjectCreate,
  ObjectItem,
  ObjectUpdate,
  SensorCreate,
  SensorItem,
  SensorUpdate,
  MeasurementItem,
  UserItem,
} from "@/types";

const BASE = "/api/v1";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || `${res.status} ${res.statusText}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

// ─── Objects ───────────────────────────────────────────────────────

export const apiObjects = {
  list: () => request<ObjectItem[]>("/objects"),
  get: (id: string) => request<ObjectItem>(`/objects/${id}`),
  create: (data: ObjectCreate) =>
    request<ObjectItem>("/objects", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: string, data: ObjectUpdate) =>
    request<ObjectItem>(`/objects/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: string) =>
    request<void>(`/objects/${id}`, { method: "DELETE" }),
};

// ─── Sensors ───────────────────────────────────────────────────────

export const apiSensors = {
  list: (objectId: string) =>
    request<SensorItem[]>(`/objects/${objectId}/sensors`),
  get: (objectId: string, sensorId: string) =>
    request<SensorItem>(`/objects/${objectId}/sensors/${sensorId}`),
  create: (objectId: string, data: SensorCreate) =>
    request<SensorItem>(`/objects/${objectId}/sensors`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (objectId: string, sensorId: string, data: SensorUpdate) =>
    request<SensorItem>(`/objects/${objectId}/sensors/${sensorId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (objectId: string, sensorId: string) =>
    request<void>(`/objects/${objectId}/sensors/${sensorId}`, {
      method: "DELETE",
    }),
  /** Persist the object's dashboard sensor order, first to last. */
  reorder: (objectId: string, sensorIds: string[]) =>
    request<SensorItem[]>(`/objects/${objectId}/sensors/reorder`, {
      method: "POST",
      body: JSON.stringify({ sensor_ids: sensorIds }),
    }),
};

// ─── Object access (users assigned to an object) ───────────────────

export const apiObjectUsers = {
  list: (objectId: string) =>
    request<UserItem[]>(`/objects/${objectId}/users`),
  assign: (objectId: string, userId: string) =>
    request<UserItem>(`/objects/${objectId}/users`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    }),
  revoke: (objectId: string, userId: string) =>
    request<UserItem>(`/objects/${objectId}/users/${userId}`, {
      method: "DELETE",
    }),
};

export const apiUsers = {
  list: (unassignedOnly = false) =>
    request<UserItem[]>(
      `/users${unassignedOnly ? "?unassigned_only=true" : ""}`
    ),
};

// ─── Notifications (profile + endpoints belong to an object) ───────

export const apiNotifications = {
  getProfile: (objectId: string) =>
    request<NotificationProfileItem>(`/objects/${objectId}/notification-profile`),
  createProfile: (objectId: string, name: string) =>
    request<NotificationProfileItem>(`/objects/${objectId}/notification-profile`, {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  updateProfile: (objectId: string, name: string) =>
    request<NotificationProfileItem>(`/objects/${objectId}/notification-profile`, {
      method: "PATCH",
      body: JSON.stringify({ name }),
    }),
  listEndpoints: (objectId: string) =>
    request<NotificationEndpointItem[]>(`/objects/${objectId}/notification-endpoints`),
  createEndpoint: (objectId: string, data: NotificationEndpointCreate) =>
    request<NotificationEndpointItem>(`/objects/${objectId}/notification-endpoints`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateEndpoint: (
    objectId: string,
    endpointId: string,
    data: NotificationEndpointUpdate
  ) =>
    request<NotificationEndpointItem>(
      `/objects/${objectId}/notification-endpoints/${endpointId}`,
      { method: "PATCH", body: JSON.stringify(data) }
    ),
  deleteEndpoint: (objectId: string, endpointId: string) =>
    request<void>(`/objects/${objectId}/notification-endpoints/${endpointId}`, {
      method: "DELETE",
    }),
};

// ─── Measurements ──────────────────────────────────────────────────

export const apiMeasurements = {
  list: (sensorId: string, limit = 50, skip = 0) =>
    request<MeasurementItem[]>(
      `/sensors/${sensorId}/measurements?limit=${limit}&skip=${skip}`
    ),
  listAggregated: (
    sensorId: string,
    sinceMs: number,
    untilMs: number,
    targetColumns: number
  ) =>
    request<MeasurementItem[]>(
      `/sensors/${sensorId}/measurements/aggregated?since=${encodeURIComponent(
        new Date(sinceMs).toISOString()
      )}&until=${encodeURIComponent(new Date(untilMs).toISOString())}&target_points=${targetColumns}`
    ),
};

// ─── Alarms ────────────────────────────────────────────────────────

// ─── Alarm Configs (per sensor, one row per alarm type — the model the
// alarm engine actually evaluates) ─────────────────────────────────

export const apiAlarmConfigs = {
  list: (sensorId: string) =>
    request<AlarmConfigItem[]>(`/sensors/${sensorId}/alarm-configs`),
  create: (sensorId: string, data: AlarmConfigCreate) =>
    request<AlarmConfigItem>(`/sensors/${sensorId}/alarm-configs`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (sensorId: string, configId: string, data: AlarmConfigUpdate) =>
    request<AlarmConfigItem>(`/sensors/${sensorId}/alarm-configs/${configId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (sensorId: string, configId: string) =>
    request<void>(`/sensors/${sensorId}/alarm-configs/${configId}`, {
      method: "DELETE",
    }),
};

export const apiAlarms = {
  list: (objectId?: string, status?: string, limit?: number) => {
    const params = new URLSearchParams();
    if (objectId) params.set("object_id", objectId);
    if (status) params.set("status", status);
    if (limit) params.set("limit", String(limit));
    const qs = params.toString();
    return request<AlarmItem[]>(`/alarms${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => request<AlarmItem>(`/alarms/${id}`),
  acknowledge: (id: string) =>
    request<AlarmItem>(`/alarms/${id}/acknowledge`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  archive: (id: string) =>
    request<AlarmItem>(`/alarms/${id}/archive`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
};
