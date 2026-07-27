<script setup lang="ts">
import { ref, computed, onMounted } from "vue";
import { useObjectsStore } from "@/stores/objects";
import { useSensorsStore } from "@/stores/sensors";
import type { ObjectItem } from "@/types";

const objectsStore = useObjectsStore();
const sensorsStore = useSensorsStore();

const search = ref("");
const showModal = ref(false);
const editingObject = ref<ObjectItem | null>(null);
const formName = ref("");
const formSlug = ref("");
const formDescription = ref("");
const formError = ref("");
const sensorCounts = ref<Record<string, number>>({});

const filteredObjects = computed(() => {
  if (!search.value) return objectsStore.objects;
  const q = search.value.toLowerCase();
  return objectsStore.objects.filter(
    (o) =>
      o.name.toLowerCase().includes(q) || o.slug.toLowerCase().includes(q)
  );
});

async function loadSensorCounts() {
  for (const obj of objectsStore.objects) {
    try {
      const sensors = await sensorsStore.fetchSensors(obj.id);
      sensorCounts.value[obj.id] =
        (sensorsStore.sensors && sensorsStore.sensors.length) || 0;
    } catch {
      sensorCounts.value[obj.id] = 0;
    }
  }
}

function openCreate() {
  editingObject.value = null;
  formName.value = "";
  formSlug.value = "";
  formDescription.value = "";
  formError.value = "";
  showModal.value = true;
}

function openEdit(obj: ObjectItem) {
  editingObject.value = obj;
  formName.value = obj.name;
  formSlug.value = obj.slug;
  formDescription.value = obj.description;
  formError.value = "";
  showModal.value = true;
}

async function handleSubmit() {
  formError.value = "";
  try {
    if (editingObject.value) {
      await objectsStore.updateObject(editingObject.value.id, {
        name: formName.value,
        description: formDescription.value,
      });
    } else {
      await objectsStore.createObject({
        name: formName.value,
        slug: formSlug.value,
        description: formDescription.value,
      });
    }
    showModal.value = false;
  } catch (e: unknown) {
    formError.value = e instanceof Error ? e.message : "Error";
  }
}

async function handleDelete(id: string) {
  if (!confirm("Usunąć ten obiekt?")) return;
  await objectsStore.deleteObject(id);
  delete sensorCounts.value[id];
}

function formatDate(d: string) {
  return new Date(d).toLocaleString("pl-PL");
}

onMounted(async () => {
  await objectsStore.fetchObjects();
  loadSensorCounts();
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
      <button
        @click="openCreate"
        class="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg font-medium cursor-pointer border-none"
      >
        + Dodaj obiekt
      </button>
    </div>

    <!-- Table -->
    <div class="bg-gray-900 border border-gray-800 rounded-xl overflow-x-auto">
      <table class="w-full text-sm text-gray-300">
        <thead>
          <tr class="border-b border-gray-800 text-gray-500 text-xs uppercase">
            <th class="px-4 py-3 text-left">Nazwa</th>
            <th class="px-4 py-3 text-left">Slug</th>
            <th class="px-4 py-3 text-left">Opis</th>
            <th class="px-4 py-3 text-center">Sensory</th>
            <th class="px-4 py-3 text-center">Status</th>
            <th class="px-4 py-3 text-center">Utworzono</th>
            <th class="px-4 py-3 text-right">Akcje</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="obj in filteredObjects"
            :key="obj.id"
            class="border-b border-gray-800/50 hover:bg-gray-800/50"
          >
            <td class="px-4 py-3 font-medium text-gray-200">{{ obj.name }}</td>
            <td class="px-4 py-3 text-gray-500 font-mono text-xs">{{ obj.slug }}</td>
            <td class="px-4 py-3 text-gray-500 max-w-xs truncate">
              {{ obj.description || "—" }}
            </td>
            <td class="px-4 py-3 text-center text-cyan-400">
              {{ sensorCounts[obj.id] ?? "..." }}
            </td>
            <td class="px-4 py-3 text-center">
              <span
                :class="obj.is_active ? 'bg-green-600' : 'bg-gray-600'"
                class="text-xs px-2 py-0.5 rounded-full text-white uppercase"
              >
                {{ obj.is_active ? "Aktywny" : "Nieaktywny" }}
              </span>
            </td>
            <td class="px-4 py-3 text-center text-gray-500 text-xs">
              {{ formatDate(obj.created_at) }}
            </td>
            <td class="px-4 py-3 text-right">
              <button
                @click="openEdit(obj)"
                class="text-xs px-2 py-1 bg-blue-600 hover:bg-blue-500 text-white rounded mr-1 cursor-pointer border-none"
              >
                Edytuj
              </button>
              <button
                @click="handleDelete(obj.id)"
                class="text-xs px-2 py-1 bg-red-600 hover:bg-red-500 text-white rounded cursor-pointer border-none"
              >
                Usuń
              </button>
            </td>
          </tr>
          <tr v-if="filteredObjects.length === 0">
            <td colspan="7" class="px-4 py-10 text-center text-gray-600">
              Brak obiektów
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Modal -->
    <div
      v-if="showModal"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      @click.self="showModal = false"
    >
      <div class="bg-gray-900 border border-gray-800 rounded-xl p-6 w-full max-w-md mx-4">
        <h3 class="text-lg font-semibold text-gray-200 mb-4">
          {{ editingObject ? "Edytuj obiekt" : "Dodaj obiekt" }}
        </h3>
        <form @submit.prevent="handleSubmit" class="space-y-4">
          <div>
            <label class="block text-sm text-gray-400 mb-1">Nazwa</label>
            <input
              v-model="formName"
              required
              class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-gray-200 focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div v-if="!editingObject">
            <label class="block text-sm text-gray-400 mb-1">Slug</label>
            <input
              v-model="formSlug"
              required
              pattern="^[a-z0-9]+(-[a-z0-9]+)*$"
              class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-gray-200 focus:outline-none focus:border-cyan-500 font-mono text-sm"
            />
          </div>
          <div v-else>
            <label class="block text-sm text-gray-400 mb-1">Slug</label>
            <input
              :value="formSlug"
              disabled
              class="w-full bg-gray-800/50 border border-gray-700 rounded-lg px-4 py-2 text-gray-500 font-mono text-sm cursor-not-allowed"
            />
          </div>
          <div>
            <label class="block text-sm text-gray-400 mb-1">Opis</label>
            <textarea
              v-model="formDescription"
              rows="3"
              class="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-2 text-gray-200 focus:outline-none focus:border-cyan-500"
            />
          </div>
          <div v-if="formError" class="text-red-400 text-sm">{{ formError }}</div>
          <div class="flex justify-end gap-3 pt-2">
            <button
              type="button"
              @click="showModal = false"
              class="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded-lg cursor-pointer border-none"
            >
              Anuluj
            </button>
            <button
              type="submit"
              class="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white rounded-lg font-medium cursor-pointer border-none"
            >
              {{ editingObject ? "Zapisz" : "Dodaj" }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>