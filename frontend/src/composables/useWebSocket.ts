import { ref, onMounted, onUnmounted } from "vue";
import { useAlarmsStore } from "@/stores/alarms";
import { useSensorsStore } from "@/stores/sensors";
import type { AlarmItem, MeasurementItem, WsEvent } from "@/types";

const WS_URL = `ws://${window.location.hostname}:8000/ws/events`;

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
  function connect() {
    if (wsInstance && wsInstance.readyState === WebSocket.OPEN) return;
    wsInstance = new WebSocket(WS_URL);
    wsInstance.onopen = () => {
      connected.value = true;
    };
    wsInstance.onclose = () => {
      connected.value = false;
      setTimeout(connect, 3000);
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

  onMounted(connect);
  onUnmounted(() => {
    wsInstance?.close();
    wsInstance = null;
  });

  return { connected };
}