import { ref, onMounted, onUnmounted } from "vue";

const WS_URL = `ws://${window.location.hostname}:8000/ws/events`;

export function useWebSocket() {
  const connected = ref(false);
  let ws: WebSocket | null = null;

  function connect() {
    ws = new WebSocket(WS_URL);
    ws.onopen = () => {
      connected.value = true;
      console.log("WebSocket connected");
    };
    ws.onclose = () => {
      connected.value = false;
      console.log("WebSocket disconnected — reconnecting in 3s…");
      setTimeout(connect, 3000);
    };
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      console.log(`[WS] ${msg.event}`, msg.data);
    };
    ws.onerror = (err) => {
      console.error("WebSocket error", err);
    };
  }

  onMounted(connect);
  onUnmounted(() => ws?.close());

  return { connected };
}