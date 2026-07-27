import { defineStore } from "pinia";
import { ref, computed } from "vue";
import { apiObjects } from "@/api";
import type { ObjectItem, ObjectCreate, ObjectUpdate } from "@/types";

export const useObjectsStore = defineStore("objects", () => {
  const objects = ref<ObjectItem[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  const activeObjects = computed(() =>
    objects.value.filter((o) => o.is_active)
  );

  async function fetchObjects() {
    loading.value = true;
    error.value = null;
    try {
      objects.value = await apiObjects.list();
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : "Failed to load objects";
    } finally {
      loading.value = false;
    }
  }

  async function createObject(data: ObjectCreate) {
    const obj = await apiObjects.create(data);
    objects.value.push(obj);
    return obj;
  }

  async function updateObject(id: string, data: ObjectUpdate) {
    const updated = await apiObjects.update(id, data);
    const idx = objects.value.findIndex((o) => o.id === id);
    if (idx !== -1) objects.value[idx] = updated;
    return updated;
  }

  async function deleteObject(id: string) {
    await apiObjects.delete(id);
    objects.value = objects.value.filter((o) => o.id !== id);
  }

  return {
    objects,
    loading,
    error,
    activeObjects,
    fetchObjects,
    createObject,
    updateObject,
    deleteObject,
  };
});