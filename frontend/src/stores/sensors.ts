import { defineStore } from "pinia";
import { ref } from "vue";
import { apiSensors, apiMeasurements } from "@/api";
import type { ChartRange, SensorItem, MeasurementItem, SensorCreate, SensorUpdate } from "@/types";

// How far back each preset range reaches.
const RANGE_DURATION_MS: Record<Exclude<ChartRange, "LIVE">, number> = {
  "1H": 60 * 60 * 1000,
  "24H": 24 * 60 * 60 * 1000,
  "7D": 7 * 24 * 60 * 60 * 1000,
};

// Safety cap so a wide range (e.g. 7D on a fast-publishing sensor) can't
// trigger unbounded pagination against the API.
const PAGE_SIZE = 500;
const MAX_PAGES = 8;
const LIVE_CAP = 200;

export const useSensorsStore = defineStore("sensors", () => {
  const sensors = ref<SensorItem[]>([]);
  const selectedSensor = ref<SensorItem | null>(null);
  const measurements = ref<MeasurementItem[]>([]);
  const loading = ref(false);
  const rangeLoading = ref(false);
  const error = ref<string | null>(null);
  const currentRange = ref<ChartRange>("LIVE");

  async function fetchSensors(objectId: string) {
    loading.value = true;
    error.value = null;
    try {
      sensors.value = await apiSensors.list(objectId);
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : "Failed to load sensors";
    } finally {
      loading.value = false;
    }
  }

  function selectSensor(sensor: SensorItem | null) {
    selectedSensor.value = sensor;
    if (sensor) {
      fetchMeasurementsForRange("LIVE");
    } else {
      measurements.value = [];
    }
  }

  /**
   * Fetch measurements covering [since, until] by paginating the existing
   * /measurements endpoint (skip/limit, already supported server-side) —
   * no backend changes. Pages until the range is covered or MAX_PAGES is
   * hit, whichever comes first.
   */
  async function fetchMeasurementsSince(
    sensorId: string,
    sinceMs: number,
    untilMs: number,
  ): Promise<MeasurementItem[]> {
    const collected: MeasurementItem[] = [];
    let skip = 0;
    for (let page = 0; page < MAX_PAGES; page++) {
      const batch = await apiMeasurements.list(sensorId, PAGE_SIZE, skip);
      if (!batch.length) break;
      collected.push(...batch);
      const oldest = batch[batch.length - 1];
      const oldestMs = new Date(oldest.received_at).getTime();
      if (oldestMs <= sinceMs || batch.length < PAGE_SIZE) break;
      skip += PAGE_SIZE;
    }
    return collected.filter((m) => {
      const t = new Date(m.received_at).getTime();
      return t >= sinceMs && t <= untilMs;
    });
  }

  async function fetchMeasurementsForRange(range: ChartRange) {
    const sensor = selectedSensor.value;
    if (!sensor) return;
    currentRange.value = range;
    if (range === "LIVE") {
      // Oscilloscope-style LIVE: no historical backfill — the chart starts
      // empty and fills in only from live WS pushes (addMeasurementFromWs).
      measurements.value = [];
      rangeLoading.value = false;
      return;
    }
    rangeLoading.value = true;
    try {
      const now = Date.now();
      const sinceMs = now - RANGE_DURATION_MS[range];
      measurements.value = await fetchMeasurementsSince(sensor.id, sinceMs, now);
    } catch {
      measurements.value = [];
    } finally {
      rangeLoading.value = false;
    }
  }

  async function createSensor(objectId: string, data: SensorCreate) {
    const sensor = await apiSensors.create(objectId, data);
    sensors.value.push(sensor);
    return sensor;
  }

  async function updateSensor(objectId: string, sensorId: string, data: SensorUpdate) {
    const updated = await apiSensors.update(objectId, sensorId, data);
    const idx = sensors.value.findIndex((s) => s.id === sensorId);
    if (idx !== -1) sensors.value[idx] = updated;
    if (selectedSensor.value?.id === sensorId) {
      selectedSensor.value = updated;
    }
    return updated;
  }

  async function deleteSensor(objectId: string, sensorId: string) {
    await apiSensors.delete(objectId, sensorId);
    sensors.value = sensors.value.filter((s) => s.id !== sensorId);
    if (selectedSensor.value?.id === sensorId) {
      selectedSensor.value = null;
    }
  }

  function updateSensorFromWs(sensorId: string, data: Partial<SensorItem>) {
    const idx = sensors.value.findIndex((s) => s.id === sensorId);
    if (idx !== -1) {
      sensors.value[idx] = { ...sensors.value[idx], ...data };
    }
    if (selectedSensor.value?.id === sensorId) {
      selectedSensor.value = { ...selectedSensor.value, ...data };
    }
  }

  function addMeasurementFromWs(measurement: MeasurementItem) {
    if (selectedSensor.value?.id === measurement.sensor_id && currentRange.value === "LIVE") {
      measurements.value.unshift(measurement);
      if (measurements.value.length > LIVE_CAP) measurements.value.pop();
    }
  }

  return {
    sensors,
    selectedSensor,
    measurements,
    loading,
    rangeLoading,
    error,
    currentRange,
    fetchSensors,
    selectSensor,
    fetchMeasurementsForRange,
    createSensor,
    updateSensor,
    deleteSensor,
    updateSensorFromWs,
    addMeasurementFromWs,
  };
});