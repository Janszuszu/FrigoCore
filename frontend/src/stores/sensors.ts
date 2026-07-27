import { defineStore } from "pinia";
import { ref } from "vue";
import { apiSensors, apiMeasurements } from "@/api";
import type { ChartRange, SensorItem, MeasurementItem, SensorCreate, SensorUpdate } from "@/types";

// How far back each preset range reaches. CUSTOM is handled separately.
const RANGE_DURATION_MS: Record<Exclude<ChartRange, "CUSTOM">, number> = {
  LIVE: 15 * 60 * 1000,
  "1H": 60 * 60 * 1000,
  "6H": 6 * 60 * 60 * 1000,
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

  async function fetchMeasurementsForRange(
    range: ChartRange,
    customStart?: Date,
    customEnd?: Date,
  ) {
    const sensor = selectedSensor.value;
    if (!sensor) return;
    currentRange.value = range;
    rangeLoading.value = true;
    try {
      if (range === "LIVE") {
        measurements.value = await apiMeasurements.list(sensor.id, LIVE_CAP);
        return;
      }
      const now = Date.now();
      const untilMs = range === "CUSTOM" && customEnd ? customEnd.getTime() : now;
      const sinceMs =
        range === "CUSTOM"
          ? (customStart?.getTime() ?? now - RANGE_DURATION_MS["24H"])
          : now - RANGE_DURATION_MS[range];
      measurements.value = await fetchMeasurementsSince(sensor.id, sinceMs, untilMs);
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