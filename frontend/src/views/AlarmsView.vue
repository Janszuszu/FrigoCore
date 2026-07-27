<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useAlarmsStore } from "@/stores/alarms";
import { useObjectsStore } from "@/stores/objects";

const alarmsStore = useAlarmsStore();
const objectsStore = useObjectsStore();

const search = ref("");

const filteredAlarms = computed(() => {
  const list = alarmsStore.filteredAlarms;
  if (!search.value) return list;
  const q = search.value.toLowerCase();
  return list.filter(
    (a) =>
      a.alarm_type.toLowerCase().includes(q) ||
      a.status.toLowerCase().includes(q) ||
      a.description.toLowerCase().includes(q)
  );
});

function statusBadge(status: string) {
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

function statusLabel(status: string) {
  switch (status) {
    case "triggered":
      return "AKTYWNY";
    case "pending":
      return "OCZEKUJĄCY";
    case "acknowledged":
      return "POTWIERDZONY";
    case "resolved":
      return "ROZWIĄZANY";
    default:
      return status.toUpperCase();
  }
}

function alarmTypeLabel(type: string) {
  switch (type) {
    case "high_temperature":
      return "Wysoka temperatura";
    case "low_temperature":
      return "Niska temperatura";
    case "offline":
      return "Offline";
    default:
      return type;
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

function handleAck(id: string) {
  alarmsStore.acknowledgeAlarm(id);
}

function getObjectName(objectId: string) {
  const obj = objectsStore.objects.find((o) => o.id === objectId);
  return obj ? obj.name : objectId.slice(0, 8);
}

onMounted(() => {
  alarmsStore.fetchAlarms();
  objectsStore.fetchObjects();
});
</script>

<template>
  <div class="space-y-6">
    <!-- Top bar -->
    <div class="flex flex-col sm:flex-row gap-4 items-start sm:items-center justify-between">
      <div class="relative w-full sm:max-w-xs">
        <input
          v-model="search"
          placeholder="Szukaj..."
          class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 pl-10 text-gray-200 focus:outline-none focus:border-cyan-500"
        />
        <span class="absolute left-3 top-2.5 text-gray-500 text-sm">🔍</span>
      </div>

      <!-- Filter pills -->
      <div class="flex flex-wrap gap-2">
        <button
          @click="alarmsStore.setStatusFilter('')"
          :class="alarmsStore.statusFilter === '' ? 'bg-cyan-600 text-white' : 'bg-gray-800 text-gray-400'"
          class="text-xs px-3 py-1.5 rounded-full cursor-pointer border-none hover:bg-gray-700"
        >
          Wszystkie
          <span class="ml-1 text-gray-500">({{ alarmsStore.alarms.length }})</span>
        </button>
        <button
          @click="alarmsStore.setStatusFilter('triggered')"
          :class="alarmsStore.statusFilter === 'triggered' ? 'bg-red-600 text-white' : 'bg-gray-800 text-red-400'"
          class="text-xs px-3 py-1.5 rounded-full cursor-pointer border-none hover:bg-red-900"
        >
          Aktywne
          <span class="ml-1">({{ alarmsStore.triggeredCount }})</span>
        </button>
        <button
          @click="alarmsStore.setStatusFilter('pending')"
          :class="alarmsStore.statusFilter === 'pending' ? 'bg-yellow-600 text-white' : 'bg-gray-800 text-yellow-400'"
          class="text-xs px-3 py-1.5 rounded-full cursor-pointer border-none hover:bg-yellow-900"
        >
          Oczekujące
          <span class="ml-1">({{ alarmsStore.pendingCount }})</span>
        </button>
        <button
          @click="alarmsStore.setStatusFilter('acknowledged')"
          :class="alarmsStore.statusFilter === 'acknowledged' ? 'bg-blue-600 text-white' : 'bg-gray-800 text-blue-400'"
          class="text-xs px-3 py-1.5 rounded-full cursor-pointer border-none hover:bg-blue-900"
        >
          Potwierdzone
        </button>
        <button
          @click="alarmsStore.setStatusFilter('resolved')"
          :class="alarmsStore.statusFilter === 'resolved' ? 'bg-green-600 text-white' : 'bg-gray-800 text-green-400'"
          class="text-xs px-3 py-1.5 rounded-full cursor-pointer border-none hover:bg-green-900"
        >
          Rozwiązane
        </button>
      </div>

      <button
        @click="alarmsStore.fetchAlarms(alarmsStore.objectFilter || undefined, alarmsStore.statusFilter || undefined)"
        class="text-xs text-cyan-400 hover:text-cyan-300 cursor-pointer bg-transparent border-none"
      >
        Odśwież
      </button>
    </div>

    <!-- Alarms list -->
    <div v-if="alarmsStore.loading" class="text-center text-gray-500 py-10">
      Ładowanie...
    </div>

    <div v-else-if="filteredAlarms.length === 0" class="text-center text-gray-600 py-20">
      Brak alarmów
    </div>

    <div v-else class="space-y-3">
      <div
        v-for="alarm in filteredAlarms"
        :key="alarm.id"
        :class="[
          'border rounded-xl p-4',
          alarm.status === 'triggered'
            ? 'bg-red-950/30 border-red-800'
            : alarm.status === 'pending'
            ? 'bg-yellow-950/30 border-yellow-800'
            : 'bg-gray-900 border-gray-800',
        ]"
      >
        <div class="flex items-start justify-between gap-4">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap mb-1">
              <span
                :class="statusBadge(alarm.status)"
                class="text-xs px-2 py-0.5 rounded-full font-medium uppercase"
              >
                {{ statusLabel(alarm.status) }}
              </span>
              <span class="text-sm font-medium text-gray-200">
                {{ alarmTypeLabel(alarm.alarm_type) }}
              </span>
              <span v-if="alarm.trigger_value !== null" class="text-sm text-cyan-400">
                {{ formatTemp(alarm.trigger_value) }}
              </span>
            </div>
            <div class="text-xs text-gray-500 space-y-0.5">
              <div>Obiekt: {{ getObjectName(alarm.object_id) }}</div>
              <div>Wykryto: {{ formatDate(alarm.detected_at) }}</div>
              <div v-if="alarm.triggered_at">Wyzwolony: {{ formatDate(alarm.triggered_at) }}</div>
              <div v-if="alarm.acknowledged_at">
                Potwierdzony: {{ formatDate(alarm.acknowledged_at) }}
              </div>
              <div v-if="alarm.resolved_at">Rozwiązany: {{ formatDate(alarm.resolved_at) }}</div>
              <div v-if="alarm.description" class="text-gray-400 mt-1">
                {{ alarm.description }}
              </div>
            </div>
          </div>
          <div class="flex-shrink-0">
            <button
              v-if="alarm.status === 'triggered'"
              @click="handleAck(alarm.id)"
              class="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-lg font-medium cursor-pointer border-none"
            >
              ACK
            </button>
            <span
              v-else-if="alarm.status === 'pending'"
              class="text-xs text-yellow-400"
            >
              Oczekiwanie...
            </span>
            <span
              v-else-if="alarm.status === 'acknowledged'"
              class="text-xs text-blue-400"
            >
              ✓ Potwierdzony
            </span>
            <span
              v-else
              class="text-xs text-green-400"
            >
              ✓ Rozwiązany
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>