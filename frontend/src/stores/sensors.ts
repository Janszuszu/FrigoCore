import { defineStore } from "pinia";
import { ref } from "vue";
import { apiSensors, apiMeasurements } from "@/api";
import type { ChartRange, SensorItem, MeasurementItem, SensorCreate, SensorUpdate } from "@/types";
import { targetColumnsForWidth } from "@/utils/chartColumns";

// How far back each preset range reaches.
const RANGE_DURATION_MS: Record<Exclude<ChartRange, "LIVE">, number> = {
  "1H": 60 * 60 * 1000,
  "24H": 24 * 60 * 60 * 1000,
  "7D": 7 * 24 * 60 * 60 * 1000,
};

const LIVE_CAP = 200;

// Only refetch when the chart's measured width implies a meaningfully
// different column target (e.g. a real breakpoint/orientation change),
// not on every sub-pixel ResizeObserver tick.
const TARGET_COLUMNS_REFETCH_DELTA = 0.15;

export const useSensorsStore = defineStore("sensors", () => {
  const sensors = ref<SensorItem[]>([]);
  const selectedSensor = ref<SensorItem | null>(null);
  const measurements = ref<MeasurementItem[]>([]);
  const loading = ref(false);
  const rangeLoading = ref(false);
  const error = ref<string | null>(null);
  const currentRange = ref<ChartRange>("24H");
  // Estimated up front from the viewport (the chart hasn't mounted/measured
  // itself yet at store-creation time); corrected via setTargetColumns once
  // the chart reports its real rendered width.
  const targetColumns = ref(
    targetColumnsForWidth(typeof window !== "undefined" ? window.innerWidth : 900),
  );

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

  function selectSensor(sensor: SensorItem | null, range: ChartRange = "24H") {
    selectedSensor.value = sensor;
    if (sensor) {
      fetchMeasurementsForRange(range);
    } else {
      measurements.value = [];
    }
  }

  /**
   * Fetches [since, until] already aggregated server-side down to
   * ~targetColumns points — the backend decides how many raw rows that
   * takes, not the frontend, so there's no client-side pagination loop
   * here anymore.
   */
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
      measurements.value = await apiMeasurements.listAggregated(
        sensor.id,
        sinceMs,
        now,
        targetColumns.value,
      );
    } catch {
      measurements.value = [];
    } finally {
      rangeLoading.value = false;
    }
  }

  /**
   * Called by the chart whenever its measured width implies a different
   * target column count. Only refetches when the change is big enough to
   * matter (see TARGET_COLUMNS_REFETCH_DELTA) — otherwise just remembers
   * the value for the next range change.
   */
  function setTargetColumns(count: number) {
    const prev = targetColumns.value;
    targetColumns.value = count;
    const changedEnough = Math.abs(count - prev) / prev > TARGET_COLUMNS_REFETCH_DELTA;
    if (changedEnough && selectedSensor.value && currentRange.value !== "LIVE") {
      fetchMeasurementsForRange(currentRange.value);
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
    targetColumns,
    fetchSensors,
    selectSensor,
    fetchMeasurementsForRange,
    setTargetColumns,
    createSensor,
    updateSensor,
    deleteSensor,
    updateSensorFromWs,
    addMeasurementFromWs,
  };
});