<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from "vue";
import { useWebSocket } from "./composables/useWebSocket";
import DashboardView from "./views/DashboardView.vue";
import ObjectsView from "./views/ObjectsView.vue";
import AlarmsView from "./views/AlarmsView.vue";

const { connected } = useWebSocket();
const activeTab = ref<"dashboard" | "objects" | "alarms">("dashboard");
const menuOpen = ref(false);
const now = ref(new Date());
let timer: ReturnType<typeof setInterval> | null = null;
const time = computed(() => now.value.toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit", second: "2-digit" }));
const date = computed(() => now.value.toLocaleDateString("pl-PL"));

onMounted(() => {
  timer = setInterval(() => {
    now.value = new Date();
  }, 1000);
});

onUnmounted(() => {
  if (timer !== null) {
    clearInterval(timer);
    timer = null;
  }
});
</script>

<template>
  <div class="app-shell">
    <header class="app-header">
      <button class="menu-button" aria-label="Menu" @click="menuOpen = true"><svg viewBox="0 0 24 24"><path d="M3 6h18M3 12h18M3 18h18" /></svg></button>
      <div class="brand"><svg viewBox="0 0 24 24"><path d="m12 2 8 4.5v11L12 22l-8-4.5v-11L12 2Z"/><path d="m4 6.5 8 4.5 8-4.5M12 11v11" /></svg><span>FRIGO CORE</span></div>
      <div class="header-meta">
        <span :class="['live-chip', { offline: !connected }]"><i></i>{{ connected ? "LIVE" : "OFFLINE" }}</span>
        <span class="clock"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>{{ time }}</span>
        <span class="header-date">{{ date }}</span>
        <button class="refresh" aria-label="Odśwież"><svg viewBox="0 0 24 24"><path d="M20 11a8 8 0 1 0 2 5.5M20 4v7h-7" /></svg></button>
      </div>
    </header>
    <div v-if="menuOpen" class="drawer-backdrop" @click="menuOpen = false"></div>
    <aside :class="['side-drawer', { open: menuOpen }]" aria-label="Nawigacja">
      <div class="drawer-brand"><svg viewBox="0 0 24 24"><path d="m12 2 8 4.5v11L12 22l-8-4.5v-11L12 2Z"/><path d="m4 6.5 8 4.5 8-4.5M12 11v11" /></svg><span>FRIGO CORE</span></div>
      <button :class="{ active: activeTab === 'dashboard' }" @click="activeTab = 'dashboard'; menuOpen = false"><svg viewBox="0 0 24 24"><path d="m3 10 9-7 9 7v10H3z"/></svg>Pulpit</button>
      <button :class="{ active: activeTab === 'objects' }" @click="activeTab = 'objects'; menuOpen = false"><svg viewBox="0 0 24 24"><path d="M4 21V4h16v17M8 8h2m4 0h2M8 12h2m4 0h2M8 16h2m4 0h2"/></svg>Obiekty</button>
      <button :class="{ active: activeTab === 'alarms' }" @click="activeTab = 'alarms'; menuOpen = false"><svg viewBox="0 0 24 24"><path d="M12 3 2 21h20L12 3Z"/><path d="M12 9v5m0 3h.01"/></svg>Alarmy</button>
    </aside>
    <main class="app-content">
      <DashboardView v-if="activeTab === 'dashboard'" />
      <ObjectsView v-else-if="activeTab === 'objects'" />
      <AlarmsView v-else />
    </main>
    <nav class="bottom-nav">
      <button :class="{ active: activeTab === 'dashboard' }" @click="activeTab = 'dashboard'"><svg viewBox="0 0 24 24"><path d="m3 10 9-7 9 7v10H3z"/></svg><span>PULPIT</span></button>
      <button :class="{ active: activeTab === 'objects' }" @click="activeTab = 'objects'"><svg viewBox="0 0 24 24"><path d="M4 21V4h16v17M8 8h2m4 0h2M8 12h2m4 0h2M8 16h2m4 0h2"/></svg><span>OBIEKTY</span></button>
      <button :class="{ active: activeTab === 'alarms' }" @click="activeTab = 'alarms'"><svg viewBox="0 0 24 24"><path d="M12 3 2 21h20L12 3Z"/><path d="M12 9v5m0 3h.01"/></svg><span>ALARMY</span></button>
      <button><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.1 2.1-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56v.1h-3v-.1A1.7 1.7 0 0 0 10.7 18.64a1.7 1.7 0 0 0-1.88.34l-.06.06-2.1-2.1.06-.06A1.7 1.7 0 0 0 7.06 15a1.7 1.7 0 0 0-1.56-1.03h-.1v-3h.1A1.7 1.7 0 0 0 7.06 9.94a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.1-2.1.06.06a1.7 1.7 0 0 0 1.88.34A1.7 1.7 0 0 0 11.73 4.75v-.1h3v.1A1.7 1.7 0 0 0 15.76 6.3a1.7 1.7 0 0 0 1.88-.34l.06-.06 2.1 2.1-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.03h.1v3h-.1A1.7 1.7 0 0 0 19.4 15Z"/></svg><span>USTAWIENIA</span></button>
    </nav>
  </div>
</template>

<style scoped>
.app-shell { height:100vh; background:#020910; color:#edf4ff; display:flex; flex-direction:column; }
.app-header { height:68px; border-bottom:1px solid #172638; background:linear-gradient(100deg,#02070d,#06111c); display:flex; align-items:center; padding:0 26px; gap:26px; flex:none; }
button { font:inherit; } .menu-button,.refresh { display:grid; place-items:center; color:#b8c8e1; background:transparent; border:0; padding:0; cursor:pointer; } .menu-button svg { width:28px; height:28px; } .refresh svg { width:25px; height:25px; }
svg { fill:none; stroke:currentColor; stroke-width:1.7; stroke-linecap:round; stroke-linejoin:round; }
.brand { display:flex; align-items:center; gap:14px; color:#12e5e6; font-size:21px; letter-spacing:1px; font-weight:600; } .brand svg { width:29px; height:33px; stroke-width:1.7; }
.header-meta { margin-left:auto; display:flex; align-items:center; gap:27px; color:#d8dfec; font-size:15px; white-space:nowrap; }.live-chip{height:35px; padding:0 13px; border:1px solid #007b42; color:#00f08a; display:flex; align-items:center; gap:8px; border-radius:6px; font-size:14px; font-weight:600;}.live-chip i{width:8px;height:8px;border-radius:50%;background:#00e77b}.live-chip.offline{color:#ff7380;border-color:#962a38}.live-chip.offline i{background:#ee3d52}.clock{display:flex;align-items:center;gap:10px}.clock svg{width:22px;height:22px}.app-content{flex:1;min-height:0;overflow:auto}.bottom-nav{height:89px;display:flex;justify-content:space-around;align-items:center;background:linear-gradient(90deg,#061321,#091829);border-top:1px solid #102235;flex:none}.bottom-nav button{background:none;border:0;color:#8ea1be;min-width:135px;display:flex;flex-direction:column;align-items:center;gap:7px;font-size:12px;cursor:pointer}.bottom-nav svg{width:24px;height:24px}.bottom-nav .active{color:#08e4e9}
.drawer-backdrop{position:fixed;inset:0;background:#0008;z-index:9}.side-drawer{position:fixed;z-index:10;top:0;bottom:0;left:0;width:286px;transform:translateX(-100%);transition:transform .22s ease;background:#081421;border-right:1px solid #203b51;box-shadow:8px 0 28px #0008;padding:18px 10px}.side-drawer.open{transform:translateX(0)}.drawer-brand{height:55px;display:flex;align-items:center;gap:13px;padding:0 14px;margin-bottom:12px;color:#10e0e5;font-size:18px;font-weight:600;letter-spacing:.8px;border-bottom:1px solid #1a3042}.drawer-brand svg{width:27px;height:27px}.side-drawer button{width:100%;height:49px;display:flex;align-items:center;gap:20px;padding:0 16px;background:transparent;color:#c4d1e4;border:0;border-radius:0 24px 24px 0;font-size:16px;text-align:left;cursor:pointer}.side-drawer button:hover{background:#10283a}.side-drawer button.active{background:#083a48;color:#08e3e9}.side-drawer button svg{width:22px;height:22px}
@media (max-width:700px){.app-header{padding:0 14px;gap:15px}.brand span{font-size:16px}.header-meta{gap:10px}.header-date,.clock{display:none}.bottom-nav button{min-width:0;font-size:10px}.bottom-nav{height:70px}.app-content{overflow-x:hidden}}
</style>
