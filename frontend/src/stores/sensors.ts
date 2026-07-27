import { defineStore } from "pinia";
import { ref } from "vue";
import { apiSensors, apiMeasurements } from "@/api";
import type { SensorItem, MeasurementItem, SensorCreate, SensorUpdate } from "@/types";

export const useSensorsStore = defineStore("sensors", () => {
  const sensors = ref<SensorItem[]>([]);
  const selectedSensor = ref<SensorItem | null>(null);
  const measurements = ref<MeasurementItem[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

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
      fetchMeasurements(sensor.id);
    } else {
      measurements.value = [];
    }
  }

  async function fetchMeasurements(sensorId: string) {
    try {
      measurements.value = await apiMeasurements.list(sensorId, 50);
    } catch {
      measurements.value = [];
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
    if (selectedSensor.value?.id === measurement.sensor_id) {
      measurements.value.unshift(measurement);
      if (measurements.value.length > 50) measurements.value.pop();
    }
  }

  return {
    sensors,
    selectedSensor,
    measurements,
    loading,
    error,
    fetchSensors,
    selectSensor,
    fetchMeasurements,
    createSensor,
    updateSensor,
    deleteSensor,
    updateSensorFromWs,
    addMeasurementFromWs,
  };
});