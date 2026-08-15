import { defineStore } from "pinia";
import { ref } from "vue";
import { apiUsers } from "@/api";
import type { UserCreate, UserItem, UserUpdate } from "@/types";

export const useUsersStore = defineStore("users", () => {
  const users = ref<UserItem[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  async function fetchUsers() {
    loading.value = true;
    error.value = null;
    try {
      users.value = await apiUsers.list();
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : "Nie udało się pobrać użytkowników";
    } finally {
      loading.value = false;
    }
  }

  async function createUser(data: UserCreate) {
    const created = await apiUsers.create(data);
    users.value.push(created);
    return created;
  }

  async function updateUser(id: string, data: UserUpdate) {
    const updated = await apiUsers.update(id, data);
    const idx = users.value.findIndex((u) => u.id === id);
    if (idx !== -1) users.value[idx] = updated;
    return updated;
  }

  async function setPassword(id: string, password: string) {
    return apiUsers.setPassword(id, password);
  }

  async function deleteUser(id: string) {
    await apiUsers.delete(id);
    users.value = users.value.filter((u) => u.id !== id);
  }

  return {
    users,
    loading,
    error,
    fetchUsers,
    createUser,
    updateUser,
    setPassword,
    deleteUser,
  };
});
