<script setup lang="ts">
/**
 * Create or edit a user account: role, per-object assignment (only relevant
 * for the 'user' role), password, and — when editing — deletion.
 */
import { computed, ref } from "vue";
import { useObjectsStore } from "@/stores/objects";
import { useUsersStore } from "@/stores/users";
import type { UserItem, UserRole } from "@/types";

const props = defineProps<{ user?: UserItem }>();
const emit = defineEmits<{ close: []; saved: []; deleted: [] }>();

const objectsStore = useObjectsStore();
const usersStore = useUsersStore();

const isEdit = computed(() => !!props.user);

type Section = "general" | "password" | "danger";
const SECTIONS = computed<{ key: Section; label: string }[]>(() => {
  const items: { key: Section; label: string }[] = [{ key: "general", label: "Dane i rola" }];
  if (isEdit.value) {
    items.push({ key: "password", label: "Hasło" });
    items.push({ key: "danger", label: "Usuń konto" });
  }
  return items;
});
const section = ref<Section>("general");

const ROLES: { key: UserRole; label: string; hint: string }[] = [
  { key: "admin", label: "Administrator", hint: "Pełny dostęp do wszystkich zakładek, może edytować" },
  { key: "serwisant", label: "Serwisant", hint: "Dostęp do pulpitów i alarmów wszystkich obiektów, bez edycji" },
  { key: "user", label: "Użytkownik", hint: "Dostęp tylko do przydzielonych obiektów" },
];

const form = ref({
  username: props.user?.username ?? "",
  email: props.user?.email ?? "",
  full_name: props.user?.full_name ?? "",
  role: (props.user?.role ?? "user") as UserRole,
  password: "",
});
const selectedObjects = ref<Set<string>>(new Set(props.user?.object_ids ?? []));

function toggleObject(id: string) {
  if (selectedObjects.value.has(id)) selectedObjects.value.delete(id);
  else selectedObjects.value.add(id);
}

const saving = ref(false);
const error = ref("");

async function save() {
  saving.value = true;
  error.value = "";
  try {
    const object_ids = form.value.role === "user" ? Array.from(selectedObjects.value) : [];
    if (isEdit.value && props.user) {
      await usersStore.updateUser(props.user.id, {
        email: form.value.email,
        full_name: form.value.full_name,
        role: form.value.role,
        object_ids,
      });
    } else {
      if (form.value.password.length < 8) {
        error.value = "Hasło musi mieć co najmniej 8 znaków";
        saving.value = false;
        return;
      }
      await usersStore.createUser({
        username: form.value.username,
        email: form.value.email,
        full_name: form.value.full_name,
        password: form.value.password,
        role: form.value.role,
        object_ids,
      });
    }
    emit("saved");
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Nie udało się zapisać użytkownika";
  } finally {
    saving.value = false;
  }
}

// ─── Password change (edit mode only) ───────────────────────────────
const newPassword = ref("");
const passwordSaving = ref(false);
const passwordError = ref("");
const passwordSaved = ref(false);

async function changePassword() {
  if (!props.user || newPassword.value.length < 8) {
    passwordError.value = "Hasło musi mieć co najmniej 8 znaków";
    return;
  }
  passwordSaving.value = true;
  passwordError.value = "";
  passwordSaved.value = false;
  try {
    await usersStore.setPassword(props.user.id, newPassword.value);
    newPassword.value = "";
    passwordSaved.value = true;
  } catch (e) {
    passwordError.value = e instanceof Error ? e.message : "Nie udało się zmienić hasła";
  } finally {
    passwordSaving.value = false;
  }
}

// ─── Delete (edit mode only) ─────────────────────────────────────────
const confirmDelete = ref("");
const deleting = ref(false);
const deleteArmed = computed(
  () => !!props.user && confirmDelete.value.trim().toLowerCase() === props.user.username.trim().toLowerCase(),
);

async function remove() {
  if (!props.user || !deleteArmed.value) return;
  deleting.value = true;
  error.value = "";
  try {
    await usersStore.deleteUser(props.user.id);
    emit("deleted");
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Nie udało się usunąć użytkownika";
    deleting.value = false;
  }
}
</script>

<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="settings-modal" role="dialog" aria-label="Użytkownik">
      <header>
        <svg viewBox="0 0 24 24" class="head-icon">
          <circle cx="12" cy="8" r="4" /><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7" />
        </svg>
        <div>
          <h2>{{ isEdit ? "Edytuj użytkownika" : "Nowy użytkownik" }}</h2>
          <p v-if="isEdit">{{ user!.username }}</p>
        </div>
        <button class="icon-btn close" aria-label="Zamknij" @click="emit('close')">✕</button>
      </header>

      <div class="body">
        <nav class="sections">
          <button
            v-for="item in SECTIONS"
            :key="item.key"
            type="button"
            :class="{ active: section === item.key, danger: item.key === 'danger' }"
            @click="section = item.key"
          >
            {{ item.label }}
          </button>
        </nav>

        <div class="pane">
          <!-- GENERAL -->
          <section v-if="section === 'general'">
            <label class="field">
              <span>Nazwa użytkownika</span>
              <input v-model="form.username" :disabled="isEdit" maxlength="128" />
            </label>
            <label class="field">
              <span>E-mail</span>
              <input v-model="form.email" type="email" maxlength="320" />
            </label>
            <label class="field">
              <span>Imię i nazwisko</span>
              <input v-model="form.full_name" maxlength="256" />
            </label>
            <label v-if="!isEdit" class="field">
              <span>Hasło</span>
              <input v-model="form.password" type="password" autocomplete="new-password" />
            </label>

            <div class="field">
              <span>Rola</span>
              <div class="role-picker">
                <label v-for="r in ROLES" :key="r.key" :class="['role-option', { active: form.role === r.key }]">
                  <input v-model="form.role" type="radio" :value="r.key" name="role" />
                  <div>
                    <strong>{{ r.label }}</strong>
                    <small>{{ r.hint }}</small>
                  </div>
                </label>
              </div>
            </div>

            <div v-if="form.role === 'user'" class="field">
              <span>Przydzielone obiekty</span>
              <div class="object-picker">
                <label v-for="obj in objectsStore.objects" :key="obj.id" class="object-option">
                  <input
                    type="checkbox"
                    :checked="selectedObjects.has(obj.id)"
                    @change="toggleObject(obj.id)"
                  />
                  {{ obj.name }}
                </label>
                <p v-if="!objectsStore.objects.length" class="muted small">Brak obiektów w systemie</p>
              </div>
            </div>
          </section>

          <!-- PASSWORD -->
          <section v-else-if="section === 'password'">
            <p class="pane-hint">Ustaw nowe hasło dla tego konta. Użytkownik zostanie wylogowany z bieżącej sesji dopiero przy następnym żądaniu.</p>
            <label class="field">
              <span>Nowe hasło</span>
              <input v-model="newPassword" type="password" autocomplete="new-password" />
            </label>
            <p v-if="passwordError" class="error-inline">{{ passwordError }}</p>
            <p v-if="passwordSaved" class="success-inline">Hasło zostało zmienione.</p>
            <button type="button" class="secondary" :disabled="passwordSaving" @click="changePassword">
              {{ passwordSaving ? "Zapisywanie…" : "Zmień hasło" }}
            </button>
          </section>

          <!-- DANGER -->
          <section v-else>
            <p class="pane-hint danger-hint">
              Usunięcie konta jest nieodwracalne. Użytkownik straci dostęp do systemu natychmiast.
            </p>
            <label class="field">
              <span>Wpisz nazwę użytkownika, aby potwierdzić</span>
              <input v-model="confirmDelete" :placeholder="user?.username" />
            </label>
            <button type="button" class="delete-btn" :disabled="!deleteArmed || deleting" @click="remove">
              {{ deleting ? "Usuwanie…" : "Usuń użytkownika" }}
            </button>
          </section>
        </div>
      </div>

      <p v-if="error" class="error">{{ error }}</p>

      <footer v-if="section === 'general'">
        <button type="button" @click="emit('close')" :disabled="saving">Anuluj</button>
        <button type="button" class="primary" :disabled="saving" @click="save">
          {{ saving ? "Zapisywanie…" : "Zapisz" }}
        </button>
      </footer>
      <footer v-else>
        <button type="button" @click="emit('close')">Zamknij</button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(2, 8, 15, 0.78);
  display: grid;
  place-items: center;
  z-index: 20;
  padding: 24px;
}

.settings-modal {
  width: min(560px, 100%);
  max-height: min(760px, 92vh);
  display: flex;
  flex-direction: column;
  background: #08151f;
  border: 1px solid #1d3b53;
  border-radius: 10px;
  color: #e9f2ff;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
}

header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid #16324a;
}

.head-icon {
  width: 22px;
  height: 22px;
  fill: none;
  stroke: #00d9ed;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
}

header h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 600;
}

header p {
  margin: 2px 0 0;
  font-size: 13px;
  color: #8ea6c4;
}

header .close {
  margin-left: auto;
}

.body {
  display: grid;
  grid-template-columns: 150px 1fr;
  min-height: 0;
  flex: 1;
}

.sections {
  display: flex;
  flex-direction: column;
  padding: 12px 8px;
  gap: 2px;
  border-right: 1px solid #16324a;
  background: #061220;
}

.sections button {
  text-align: left;
  padding: 9px 12px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #a9bdd8;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

.sections button:hover {
  background: #0d2334;
  color: #e9f2ff;
}

.sections button.active {
  background: #0a3243;
  color: #00dde1;
}

.sections button.danger {
  margin-top: auto;
  color: #e0788a;
}

.sections button.danger.active {
  background: #34121a;
  color: #ff8497;
}

.pane {
  padding: 20px 24px;
  overflow-y: auto;
}

.pane-hint {
  margin: 0 0 16px;
  font-size: 13px;
  color: #90a7c4;
  line-height: 1.5;
}

.danger-hint {
  color: #e8a3ae;
}

.field {
  display: block;
  margin-bottom: 16px;
}

.field > span {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  color: #a9bdd8;
}

.field input:not([type="checkbox"]):not([type="radio"]) {
  width: 100%;
  box-sizing: border-box;
  background: #050f1a;
  border: 1px solid #234662;
  border-radius: 6px;
  color: #f1f6ff;
  padding: 8px 10px;
  font: inherit;
  font-size: 14px;
}

.field input:disabled {
  opacity: 0.5;
}

.field input:focus {
  outline: none;
  border-color: #00b6d6;
}

.role-picker {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.role-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #234662;
  border-radius: 8px;
  cursor: pointer;
}

.role-option.active {
  border-color: #00b6d6;
  background: #0a2634;
}

.role-option input {
  margin-top: 4px;
}

.role-option strong {
  display: block;
  font-size: 13px;
  color: #e9f2ff;
}

.role-option small {
  display: block;
  color: #8ea6c4;
  font-size: 12px;
  margin-top: 2px;
}

.object-picker {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 160px;
  overflow-y: auto;
  padding: 10px 12px;
  border: 1px solid #234662;
  border-radius: 8px;
}

.object-option {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #dbe6f4;
}

.muted {
  color: #8ea6c4;
  font-size: 13px;
}

.muted.small {
  font-size: 12px;
  margin: 0;
}

.secondary {
  padding: 8px 16px;
  background: #072a37;
  border: 1px solid #00aee2;
  border-radius: 6px;
  color: #00d9ed;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
}

.secondary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.delete-btn {
  padding: 9px 18px;
  background: #7c1122;
  border: 1px solid #a4213a;
  border-radius: 6px;
  color: #ffe3e7;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

.delete-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.icon-btn {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  background: #0b1e2d;
  border: 1px solid #234662;
  border-radius: 6px;
  color: #b7cbe4;
  cursor: pointer;
  font-size: 14px;
}

.icon-btn:hover {
  border-color: #00b6d6;
  color: #00dde1;
}

.error,
.error-inline {
  color: #ff8497;
  font-size: 13px;
}

.success-inline {
  color: #00e08a;
  font-size: 13px;
}

.error {
  margin: 0;
  padding: 10px 20px;
  border-top: 1px solid #16324a;
}

footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 20px;
  border-top: 1px solid #16324a;
}

footer button {
  padding: 8px 18px;
  border: 1px solid #234662;
  border-radius: 6px;
  background: #0b1e2d;
  color: #e9f2ff;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

footer .primary {
  background: linear-gradient(115deg, #06c7f3, #078de4);
  border-color: #139de5;
  color: #02141f;
  font-weight: 600;
}

footer button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
