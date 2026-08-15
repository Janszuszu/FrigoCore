import { ref, onUnmounted, watch } from "vue";
import { useAlarmsStore } from "@/stores/alarms";
import { useAuthStore } from "@/stores/auth";
import { useSensorsStore } from "@/stores/sensors";
import type { AlarmItem, MeasurementItem, WsEvent } from "@/types";

function wsUrl(token: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/ws/events?token=${encodeURIComponent(token)}`;
}

let wsInstance: WebSocket | null = null;
const connected = ref(false);
const listeners: Map<string, Set<(data: unknown) => void>> = new Map();

function handleEvent(event: string, data: Record<string, unknown>) {
  const alarmsStore = useAlarmsStore();
  const sensorsStore = useSensorsStore();

  switch (event) {
    case "measurement.created":
      sensorsStore.addMeasurementFromWs(data as unknown as MeasurementItem);
      break;
    case "sensor.updated":
      sensorsStore.updateSensorFromWs(data.id as string, data as Record<string, unknown>);
      break;
    case "alarm.pending":
    case "alarm.triggered":
    case "alarm.acknowledged":
    case "alarm.resolved":
      alarmsStore.addAlarmFromWs(data as unknown as AlarmItem);
      break;
  }

  const subs = listeners.get(event);
  if (subs) {
    subs.forEach((fn) => fn(data));
  }
}

export function onWsEvent(event: string, fn: (data: unknown) => void) {
  if (!listeners.has(event)) {
    listeners.set(event, new Set());
  }
  listeners.get(event)!.add(fn);
  return () => {
    listeners.get(event)?.delete(fn);
  };
}

export function useWebSocket() {
  const authStore = useAuthStore();

  function connect() {
    if (wsInstance && wsInstance.readyState === WebSocket.OPEN) return;
    if (!authStore.token) return;
    wsInstance = new WebSocket(wsUrl(authStore.token));
    wsInstance.onopen = () => {
      connected.value = true;
    };
    wsInstance.onclose = () => {
      connected.value = false;
      if (authStore.token) setTimeout(connect, 3000);
    };
    wsInstance.onmessage = (msg) => {
      try {
        const parsed: WsEvent = JSON.parse(msg.data);
        handleEvent(parsed.event, parsed.data);
      } catch {
        // ignore malformed
      }
    };
    wsInstance.onerror = () => {};
  }

  function disconnect() {
    wsInstance?.close();
    wsInstance = null;
    connected.value = false;
  }

  // Reacts to login/logout, not just the initial token restored from
  // localStorage — otherwise a fresh login (no reload) would never open a
  // socket, since onMounted only fires once, before the token exists.
  const stopWatch = watch(
    () => authStore.token,
    (token) => {
      if (token) connect();
      else disconnect();
    },
    { immediate: true },
  );

  onUnmounted(() => {
    stopWatch();
    disconnect();
  });

  return { connected };
}