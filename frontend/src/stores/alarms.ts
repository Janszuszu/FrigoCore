import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { apiAlarms } from "@/api";
import type { AlarmItem } from "@/types";

export const useAlarmsStore = defineStore("alarms", () => {
  const alarms = ref<AlarmItem[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);
  const statusFilter = ref<string>("");
  const objectFilter = ref<string>("");

  const filteredAlarms = computed(() => {
    let list = alarms.value;
    if (objectFilter.value) {
      list = list.filter((a) => a.object_id === objectFilter.value);
    }
    if (statusFilter.value) {
      list = list.filter((a) => a.status === statusFilter.value);
    }
    return list;
  });

  const triggeredCount = computed(
    () => alarms.value.filter((a) => a.status === "triggered").length
  );
  const pendingCount = computed(
    () => alarms.value.filter((a) => a.status === "pending").length
  );

  async function fetchAlarms(objectId?: string, status?: string) {
    loading.value = true;
    error.value = null;
    try {
      alarms.value = await apiAlarms.list(objectId, status);
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : "Failed to load alarms";
    } finally {
      loading.value = false;
    }
  }

  async function acknowledgeAlarm(id: string) {
    try {
      const updated = await apiAlarms.acknowledge(id);
      const idx = alarms.value.findIndex((a) => a.id === id);
      if (idx !== -1) alarms.value[idx] = updated;
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : "Failed to acknowledge";
    }
  }

  function addAlarmFromWs(alarm: AlarmItem) {
    const idx = alarms.value.findIndex((a) => a.id === alarm.id);
    if (idx !== -1) {
      alarms.value[idx] = alarm;
    } else {
      alarms.value.unshift(alarm);
    }
  }

  function setStatusFilter(status: string) {
    statusFilter.value = status;
  }

  function setObjectFilter(objectId: string) {
    objectFilter.value = objectId;
  }

  return {
    alarms,
    loading,
    error,
    statusFilter,
    objectFilter,
    filteredAlarms,
    triggeredCount,
    pendingCount,
    fetchAlarms,
    acknowledgeAlarm,
    addAlarmFromWs,
    setStatusFilter,
    setObjectFilter,
  };
});