<script setup lang="ts">
/**
 * Ustawienia — user administration. Admin only (gated in App.vue).
 */
import { computed, onMounted, ref } from "vue";
import { useObjectsStore } from "@/stores/objects";
import { useUsersStore } from "@/stores/users";
import type { UserItem } from "@/types";
import UserFormModal from "@/components/UserFormModal.vue";

const usersStore = useUsersStore();
const objectsStore = useObjectsStore();

const editing = ref<UserItem | null>(null);
const creating = ref(false);

onMounted(() => {
  void usersStore.fetchUsers();
  if (!objectsStore.objects.length) void objectsStore.fetchObjects();
});

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrator",
  serwisant: "Serwisant",
  user: "Użytkownik",
};

function roleLabel(role: string) {
  return ROLE_LABELS[role] ?? role;
}

function objectNames(user: UserItem) {
  if (user.role !== "user") return "Wszystkie obiekty";
  if (!user.object_ids.length) return "Brak przypisanych obiektów";
  const byId = new Map(objectsStore.objects.map((o) => [o.id, o.name]));
  return user.object_ids.map((id) => byId.get(id) ?? id).join(", ");
}

function closeModal() {
  editing.value = null;
  creating.value = false;
}

async function onSaved() {
  closeModal();
  await usersStore.fetchUsers();
}

async function onDeleted() {
  closeModal();
}
</script>

<template>
  <div class="settings-view">
    <div class="toolbar">
      <h1>Ustawienia — Użytkownicy</h1>
      <button type="button" class="primary" @click="creating = true">+ Dodaj użytkownika</button>
    </div>

    <p v-if="usersStore.error" class="error">{{ usersStore.error }}</p>
    <p v-if="usersStore.loading" class="muted">Ładowanie…</p>

    <table v-else class="grid">
      <thead>
        <tr>
          <th>Użytkownik</th>
          <th>E-mail</th>
          <th>Rola</th>
          <th>Dostęp do obiektów</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="user in usersStore.users" :key="user.id">
          <td>
            <strong>{{ user.username }}</strong>
            <small v-if="user.full_name">{{ user.full_name }}</small>
          </td>
          <td class="dim">{{ user.email }}</td>
          <td><span class="role">{{ roleLabel(user.role) }}</span></td>
          <td class="dim">{{ objectNames(user) }}</td>
          <td>
            <span :class="['status', user.is_active ? 'on' : 'off']">
              {{ user.is_active ? "Aktywny" : "Nieaktywny" }}
            </span>
          </td>
          <td class="right">
            <button type="button" class="link" @click="editing = user">Edytuj</button>
          </td>
        </tr>
        <tr v-if="!usersStore.users.length">
          <td colspan="6" class="empty">Brak użytkowników</td>
        </tr>
      </tbody>
    </table>

    <UserFormModal
      v-if="creating"
      @close="closeModal"
      @saved="onSaved"
    />
    <UserFormModal
      v-if="editing"
      :user="editing"
      @close="closeModal"
      @saved="onSaved"
      @deleted="onDeleted"
    />
  </div>
</template>

<style scoped>
.settings-view {
  padding: 24px 28px 40px;
  max-width: 1100px;
  margin: 0 auto;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 16px;
}

.toolbar h1 {
  font-size: 19px;
  font-weight: 600;
  margin: 0;
  color: #e9f2ff;
}

.primary {
  padding: 9px 18px;
  background: linear-gradient(115deg, #06c7f3, #078de4);
  border: 1px solid #139de5;
  border-radius: 6px;
  color: #02141f;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  background: #08151f;
  border: 1px solid #1d3b53;
  border-radius: 10px;
  overflow: hidden;
}

.grid th {
  text-align: left;
  font-weight: 500;
  color: #7d93af;
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 12px 14px;
  border-bottom: 1px solid #16324a;
  background: #061220;
}

.grid td {
  padding: 12px 14px;
  border-bottom: 1px solid #102638;
  vertical-align: middle;
  color: #dbe6f4;
}

.grid td strong {
  display: block;
  font-weight: 500;
  color: #e9f2ff;
}

.grid td small {
  display: block;
  margin-top: 2px;
  color: #7d93af;
  font-size: 12px;
}

.grid .dim {
  color: #90a7c4;
}

.grid .right {
  text-align: right;
  white-space: nowrap;
}

.grid .empty {
  text-align: center;
  color: #7d93af;
  padding: 24px;
}

.role {
  display: inline-block;
  padding: 2px 8px;
  border: 1px solid #234662;
  border-radius: 20px;
  color: #9fb6d2;
  font-size: 11px;
  text-transform: uppercase;
}

.status {
  font-size: 12px;
}

.status.on {
  color: #00e08a;
}

.status.off {
  color: #e0788a;
}

.link {
  background: none;
  border: 0;
  color: #00d9ed;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  padding: 0;
}

.link:hover {
  text-decoration: underline;
}

.muted {
  color: #8ea6c4;
  font-size: 13px;
}

.error {
  color: #ff8497;
  font-size: 13px;
}
</style>
