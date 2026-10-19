import { onMounted, onUnmounted } from "vue";

/**
 * Re-fetch live values on a timer while the page is visible, and at once
 * when it becomes visible again. The websocket alone is not enough: a mobile
 * browser freezes a background tab and silently drops its socket, so on
 * return the screen would keep showing the values from before.
 */
export function useLiveRefresh(refresh: () => unknown, intervalMs: number) {
  let timer: ReturnType<typeof setInterval> | null = null;

  function run() {
    if (document.visibilityState === "visible") void refresh();
  }

  function onVisibility() {
    if (document.visibilityState === "visible") run();
  }

  onMounted(() => {
    timer = setInterval(run, intervalMs);
    document.addEventListener("visibilitychange", onVisibility);
  });

  onUnmounted(() => {
    if (timer !== null) clearInterval(timer);
    document.removeEventListener("visibilitychange", onVisibility);
  });
}
