import type {
  AlarmItem,
  ObjectCreate,
  ObjectItem,
  ObjectUpdate,
  SensorCreate,
  SensorItem,
  SensorUpdate,
  MeasurementItem,
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
};

// ─── Measurements ──────────────────────────────────────────────────

export const apiMeasurements = {
  list: (sensorId: string, limit = 50) =>
    request<MeasurementItem[]>(
      `/sensors/${sensorId}/measurements?limit=${limit}`
    ),
};

// ─── Alarms ────────────────────────────────────────────────────────

export const apiAlarms = {
  list: (objectId?: string, status?: string) => {
    const params = new URLSearchParams();
    if (objectId) params.set("object_id", objectId);
    if (status) params.set("status", status);
    const qs = params.toString();
    return request<AlarmItem[]>(`/alarms${qs ? `?${qs}` : ""}`);
  },
  get: (id: string) => request<AlarmItem>(`/alarms/${id}`),
  acknowledge: (id: string) =>
    request<AlarmItem>(`/alarms/${id}/acknowledge`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
};