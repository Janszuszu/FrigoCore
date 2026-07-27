<script setup lang="ts">
import { ref, computed, watch, onMounted } from "vue";
import { useObjectsStore } from "@/stores/objects";
import { useSensorsStore } from "@/stores/sensors";
import { useAlarmsStore } from "@/stores/alarms";
import { apiAlarms } from "@/api";
import type { AlarmItem, MeasurementItem } from "@/types";

const objectsStore = useObjectsStore();
const sensorsStore = useSensorsStore();
const alarmsStore = useAlarmsStore();

const selectedObjectId = ref<string>("");
const dashboardAlarms = ref<AlarmItem[]>([]);

const currentTemp = computed(() =>
  sensorsStore.selectedSensor?.current_temperature ?? null
);

const tempStats = computed(() => {
  const m = sensorsStore.measurements;
  if (m.length === 0) return { min: null, max: null, avg: null };
  const temps = m.map((x: MeasurementItem) => x.temperature);
  return {
    min: Math.min(...temps).toFixed(1),
    max: Math.max(...temps).toFixed(1),
    avg: (temps.reduce((a: number, b: number) => a + b, 0) / temps.length).toFixed(1),
  };
});

const isOnline = computed(() => {
  const s = sensorsStore.selectedSensor;
  if (!s || !s.last_message_at) return false;
  const last = new Date(s.last_message_at).getTime();
  const now = Date.now();
  return (now - last) < s.offline_timeout_seconds * 1000;
});

const chartPath = computed(() => {
  const m = sensorsStore.measurements;
  if (m.length < 2) return "";
  const reversed = [...m].reverse();
  const maxT = Math.max(...reversed.map((x: MeasurementItem) => x.temperature));
  const minT = Math.min(...reversed.map((x: MeasurementItem) => x.temperature));
  const range = maxT - minT || 1;
  const w = 100 / (reversed.length - 1);
  let d = `M 0,${100 - ((reversed[0].temperature - minT) / range) * 80 - 10}`;
  for (let i = 1; i < reversed.length; i++) {
    const x = i * w;
    const y = 100 - ((reversed[i].temperature - minT) / range) * 80 - 10;
    d += ` L ${x},${y}`;
  }
  return d;
});

function loadDashboard() {
  if (!selectedObjectId.value) return;
  sensorsStore.fetchSensors(selectedObjectId.value);
  loadAlarms();
}

function onSensorSelect(sensorId: string) {
  const s = sensorsStore.sensors.find((x) => x.id === sensorId) ?? null;
  sensorsStore.selectSensor(s);
}

async function loadAlarms() {
  if (!selectedObjectId.value) return;
  try {
    dashboardAlarms.value = await apiAlarms.list(selectedObjectId.value);
  } catch {
    dashboardAlarms.value = [];
  }
}

function formatDate(d: string | null) {
  if (!d) return "—";
  return new Date(d).toLocaleString("pl-PL");
}

function formatTemp(v: number | null) {
  if (v === null || v === undefined) return "—";
  return v.toFixed(1) + " °C";
}

function alarmBadgeClass(status: string) {
  switch (status) {
    case "triggered":
      return "bg-red-600 text-white";
    case "pending":
      return "bg-yellow-500 text-black";
    case "acknowledged":
      return "bg-blue-500 text-white";
    case "resolved":
      return "bg-green-600 text-white";
    default:
      return "bg-gray-600 text-white";
  }
}

watch(selectedObjectId, () => {
  sensorsStore.selectSensor(null);
  loadDashboard();
});

onMounted(() => {
  objectsStore.fetchObjects();
  alarmsStore.fetchAlarms();
});
</script>

<template>
  <div class="space-y-6">
    <!-- Top bar: object + sensor selectors -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div>
        <label class="block text-sm text-gray-400 mb-1">Obiekt</label>
        <select
          v-model="selectedObjectId"
          class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-gray-200 focus:outline-none focus:border-cyan-500"
        >
          <option value="">— Wybierz obiekt —</option>
          <option
            v-for="obj in objectsStore.activeObjects"
            :key="obj.id"
            :value="obj.id"
          >
            {{ obj.name }}
          </option>
        </select>
      </div>
      <div>
        <label class="block text-sm text-gray-400 mb-1">Sensor</label>
        <select
          v-model="sensorsStore.selectedSensor"
          @change="onSensorSelect(($event.target as HTMLSelectElement).value)"
          :disabled="!selectedObjectId || sensorsStore.loading"
          class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-gray-200 focus:outline-none focus:border-cyan-500 disabled:opacity-50"
        >
          <option :value="null">— Wybierz sensor —</option>
          <option
            v-for="s in sensorsStore.sensors"
            :key="s.id"
            :value="s"
          >
            {{ s.name }} ({{ s.slug }})
          </option>
        </select>
      </div>
    </div>

    <div v-if="!sensorsStore.selectedSensor" class="text-center text-gray-500 py-20">
      Wybierz obiekt i sensor, aby zobaczyć dane.
    </div>

    <!-- Temperature cards -->
    <div
      v-if="sensorsStore.selectedSensor"
      class="grid grid-cols-2 md:grid-cols-4 gap-4"
    >
      <div class="bg-gray-900 border border-gray-800 rounded-xl p-4 text-center">
        <div class="text-xs text-gray-500 uppercase mb-1">Aktualna</div>
        <div class="text-3xl font-bold text-cyan-400">
          {{ formatTemp(currentTemp) }}
        </div>
      </div>
      <div class="bg-gray-900 border border-gray-800 rounded-xl p-4 text-center">
        <div class="text-xs text-gray-500 uppercase mb-1">Minimum</div>
        <div class="text-3xl font-bold text-blue-400">
          {{ tempStats.min ? tempStats.min + " °C" : "—" }}
        </div>
      </div>
      <div class="bg-gray-900 border border-gray-800 rounded-xl p-4 text-center">
        <div class="text-xs text-gray-500 uppercase mb-1">Maksimum</div>
        <div class="text-3xl font-bold text-red-400">
          {{ tempStats.max ? tempStats.max + " °C" : "—" }}
        </div>
      </div>
      <div class="bg-gray-900 border border-gray-800 rounded-xl p-4 text-center">
        <div class="text-xs text-gray-500 uppercase mb-1">Średnia</div>
        <div class="text-3xl font-bold text-yellow-400">
          {{ tempStats.avg ? tempStats.avg + " °C" : "—" }}
        </div>
      </div>
    </div>

    <!-- Status + Chart row -->
    <div
      v-if="sensorsStore.selectedSensor"
      class="grid grid-cols-1 lg:grid-cols-3 gap-6"
    >
      <!-- Status -->
      <div class="bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div class="text-sm text-gray-400 mb-3">Status</div>
        <div class="flex items-center gap-3">
          <span
            :class="isOnline ? 'bg-green-500' : 'bg-red-500'"
            class="w-3 h-3 rounded-full animate-pulse"
          />
          <span
            :class="isOnline ? 'text-green-400' : 'text-red-400'"
            class="text-xl font-bold uppercase"
          >
            {{ isOnline ? "ONLINE" : "OFFLINE" }}
          </span>
        </div>
        <div class="text-xs text-gray-500 mt-2">
          Ostatnia wiadomość: {{ formatDate(sensorsStore.selectedSensor.last_message_at) }}
        </div>
      </div>

      <!-- Chart -->
      <div class="lg:col-span-2 bg-gray-900 border border-gray-800 rounded-xl p-4">
        <div class="text-sm text-gray-400 mb-2">Wykres temperatury</div>
        <div v-if="sensorsStore.measurements.length < 2" class="text-gray-600 text-sm py-10 text-center">
          Za mało danych do wykresu
        </div>
        <svg
          v-else
          viewBox="0 0 100 100"
          preserveAspectRatio="none"
          class="w-full h-48"
        >
          <path
            :d="chartPath"
            fill="none"
            stroke="#22d3ee"
            stroke-width="1.5"
            vector-effect="non-scaling-stroke"
          />
        </svg>
      </div>
    </div>

    <!-- Alarms for selected object -->
    <div
      v-if="selectedObjectId"
      class="bg-gray-900 border border-gray-800 rounded-xl p-4"
    >
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm text-gray-400">Alarmy dla obiektu</h3>
        <button
          @click="loadAlarms"
          class="text-xs text-cyan-400 hover:text-cyan-300 cursor-pointer bg-transparent border-none"
        >
          Odśwież
        </button>
      </div>
      <div v-if="dashboardAlarms.length === 0" class="text-gray-600 text-sm text-center py-4">
        Brak alarmów
      </div>
      <div v-else class="space-y-2 max-h-64 overflow-y-auto">
        <div
          v-for="alarm in dashboardAlarms"
          :key="alarm.id"
          class="flex items-center gap-3 p-3 bg-gray-800 rounded-lg"
        >
          <span
            :class="alarmBadgeClass(alarm.status)"
            class="text-xs px-2 py-0.5 rounded-full font-medium uppercase"
          >
            {{ alarm.status }}
          </span>
          <span class="text-sm text-gray-300 flex-1">
            {{ alarm.alarm_type === "high_temperature" ? "Wysoka temp." : alarm.alarm_type === "low_temperature" ? "Niska temp." : "Offline" }}
            <span v-if="alarm.trigger_value !== null" class="text-gray-500 ml-1">
              ({{ formatTemp(alarm.trigger_value) }})
            </span>
          </span>
          <span class="text-xs text-gray-500">{{ formatDate(alarm.detected_at) }}</span>
          <button
            v-if="alarm.status === 'triggered'"
            @click="alarmsStore.acknowledgeAlarm(alarm.id); loadAlarms()"
            class="text-xs px-2 py-1 bg-red-600 hover:bg-red-500 text-white rounded cursor-pointer border-none"
          >
            ACK
          </button>
        </div>
      </div>
    </div>
  </div>
</template>