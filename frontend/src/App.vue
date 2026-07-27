<script setup lang="ts">
import { ref } from "vue";
import { useWebSocket } from "./composables/useWebSocket";
import DashboardView from "./views/DashboardView.vue";
import ObjectsView from "./views/ObjectsView.vue";
import AlarmsView from "./views/AlarmsView.vue";

const { connected } = useWebSocket();
const activeTab = ref<"dashboard" | "objects" | "alarms">("dashboard");

const tabs = [
  { key: "dashboard" as const, label: "Pulpit", icon: "📊" },
  { key: "objects" as const, label: "Obiekty", icon: "📦" },
  { key: "alarms" as const, label: "Alarmy", icon: "🚨" },
] as const;
</script>

<template>
  <div class="min-h-screen bg-gray-950 flex">
    <!-- Sidebar -->
    <aside class="w-64 bg-gray-900 border-r border-gray-800 flex flex-col flex-shrink-0">
      <div class="px-6 py-5 border-b border-gray-800">
        <h1 class="text-lg font-bold text-cyan-400 tracking-tight">❄️ FrigoCore</h1>
        <p class="text-xs text-gray-600 mt-0.5">IoT Refrigeration Monitor</p>
      </div>

      <nav class="flex-1 p-4 space-y-1">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          @click="activeTab = tab.key"
          :class="[
            'w-full text-left px-4 py-3 rounded-lg text-sm font-medium flex items-center gap-3 cursor-pointer border-none',
            activeTab === tab.key
              ? 'bg-cyan-600/20 text-cyan-400'
              : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200',
          ]"
        >
          <span class="text-lg">{{ tab.icon }}</span>
          {{ tab.label }}
        </button>
      </nav>

      <div class="px-4 py-3 border-t border-gray-800">
        <div class="flex items-center gap-2 text-xs">
          <span
            :class="connected ? 'bg-green-500' : 'bg-red-500'"
            class="w-2 h-2 rounded-full"
          />
          <span :class="connected ? 'text-green-400' : 'text-red-400'">
            {{ connected ? "Live" : "Disconnected" }}
          </span>
        </div>
      </div>
    </aside>

    <!-- Main content -->
    <div class="flex-1 flex flex-col min-w-0">
      <header class="bg-gray-900 border-b border-gray-800 px-6 py-4">
        <h2 class="text-sm font-semibold text-gray-300 uppercase tracking-wider">
          {{ tabs.find((t) => t.key === activeTab)?.label }}
        </h2>
      </header>

      <main class="flex-1 p-6 overflow-auto">
        <DashboardView v-if="activeTab === 'dashboard'" />
        <ObjectsView v-else-if="activeTab === 'objects'" />
        <AlarmsView v-else />
      </main>

      <footer class="bg-gray-900 border-t border-gray-800 px-6 py-2 text-center text-xs text-gray-700">
        FrigoCore v0.1.0
      </footer>
    </div>
  </div>
</template>