<script setup lang="ts">
import { useWebSocket } from "./composables/useWebSocket";

const { connected } = useWebSocket();
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <header class="bg-gray-900 border-b border-gray-800 px-6 py-4">
      <h1 class="text-xl font-bold text-cyan-400">❄️ FrigoCore</h1>
      <p class="text-sm text-gray-500 mt-1">
        IoT Refrigeration Monitoring
        <span
          :class="connected ? 'text-green-400' : 'text-red-400'"
          class="ml-4"
        >
          {{ connected ? "● Live" : "● Disconnected" }}
        </span>
      </p>
    </header>

    <main class="flex-1 p-6 grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- Objects Panel -->
      <section class="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <h2 class="text-lg font-semibold text-gray-200 mb-4">📦 Objects</h2>
        <p class="text-sm text-gray-500">REST API: <code class="text-cyan-400">GET /api/v1/objects</code></p>
      </section>

      <!-- Alarms Panel -->
      <section class="bg-gray-900 rounded-xl border border-gray-800 p-6">
        <h2 class="text-lg font-semibold text-gray-200 mb-4">🚨 Alarms</h2>
        <p class="text-sm text-gray-500">REST API: <code class="text-cyan-400">GET /api/v1/alarms</code></p>
      </section>

      <!-- WebSocket Events -->
      <section class="bg-gray-900 rounded-xl border border-gray-800 p-6 lg:col-span-2">
        <h2 class="text-lg font-semibold text-gray-200 mb-4">📡 Real-time Events (WebSocket)</h2>
        <p class="text-sm text-gray-500">Connected to <code class="text-cyan-400">ws://localhost:8000/ws/events</code></p>
      </section>
    </main>

    <footer class="bg-gray-900 border-t border-gray-800 px-6 py-3 text-center text-xs text-gray-600">
      FrigoCore v0.1.0 — Backend API on port 8000 | WebSocket on /ws/events
    </footer>
  </div>
</template>