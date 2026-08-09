<script setup lang="ts">
/**
 * Object administration — general details, who has access to the object,
 * its notification profile and channels, and deletion.
 *
 * Access assignment uses the existing User.object_id relationship: a client
 * belongs to one object, an administrator sees all of them.
 */
import { computed, onMounted, ref } from "vue";
import { apiNotifications, apiObjectUsers, apiUsers } from "@/api";
import { useObjectsStore } from "@/stores/objects";
import type {
  NotificationChannel,
  NotificationEndpointItem,
  NotificationProfileItem,
  ObjectItem,
  UserItem,
} from "@/types";

const props = defineProps<{ object: ObjectItem }>();
const emit = defineEmits<{ close: []; saved: []; deleted: [] }>();

const objectsStore = useObjectsStore();

type Section = "general" | "users" | "notifications" | "danger";
const SECTIONS: { key: Section; label: string }[] = [
  { key: "general", label: "Ogólne" },
  { key: "users", label: "Użytkownicy" },
  { key: "notifications", label: "Powiadomienia" },
  { key: "danger", label: "Usuń obiekt" },
];
const section = ref<Section>("general");

// configKey must match the key each channel handler reads out of
// NotificationEndpoint.config in the backend's NotificationEngine —
// storing the address under any other name would deliver nothing.
const CHANNELS: {
  key: NotificationChannel;
  label: string;
  hint: string;
  configKey: string;
}[] = [
  { key: "telegram", label: "Telegram", hint: "chat_id", configKey: "chat_id" },
  { key: "fcm", label: "FCM", hint: "token urządzenia", configKey: "device_token" },
  { key: "email", label: "E-mail", hint: "adres e-mail", configKey: "to" },
  { key: "sms", label: "SMS", hint: "numer telefonu", configKey: "phone_number" },
  { key: "webhook", label: "Webhook", hint: "adres URL", configKey: "url" },
];

const saving = ref(false);
const deleting = ref(false);
const error = ref("");

const form = ref({ name: props.object.name, description: props.object.description });

// ─── Users ────────────────────────────────────────────────────────
const assigned = ref<UserItem[]>([]);
const available = ref<UserItem[]>([]);
const pickedUser = ref("");
const usersLoading = ref(true);
const usersError = ref("");

async function loadUsers() {
  usersLoading.value = true;
  usersError.value = "";
  try {
    const [objectUsers, unassigned] = await Promise.all([
      apiObjectUsers.list(props.object.id),
      apiUsers.list(true),
    ]);
    assigned.value = objectUsers;
    // Administrators already see every object, so they are not offered here.
    available.value = unassigned.filter((u) => u.role !== "admin");
    pickedUser.value = "";
  } catch (e) {
    usersError.value = e instanceof Error ? e.message : "Nie udało się pobrać użytkowników";
  } finally {
    usersLoading.value = false;
  }
}

async function grantAccess() {
  if (!pickedUser.value) return;
  usersError.value = "";
  try {
    await apiObjectUsers.assign(props.object.id, pickedUser.value);
    await loadUsers();
  } catch (e) {
    usersError.value = e instanceof Error ? e.message : "Nie udało się nadać dostępu";
  }
}

async function revokeAccess(user: UserItem) {
  if (!confirm(`Odebrać dostęp do obiektu użytkownikowi ${user.username}?`)) return;
  usersError.value = "";
  try {
    await apiObjectUsers.revoke(props.object.id, user.id);
    await loadUsers();
  } catch (e) {
    usersError.value = e instanceof Error ? e.message : "Nie udało się odebrać dostępu";
  }
}

// ─── Notifications ────────────────────────────────────────────────
const profile = ref<NotificationProfileItem | null>(null);
const profileName = ref("");
const endpoints = ref<NotificationEndpointItem[]>([]);
const notifLoading = ref(true);
const notifError = ref("");
const newEndpoint = ref<{ channel: NotificationChannel; label: string; target: string }>({
  channel: "telegram",
  label: "",
  target: "",
});

const endpointsByChannel = computed(() => {
  const grouped: Record<string, NotificationEndpointItem[]> = {};
  for (const endpoint of endpoints.value) {
    (grouped[endpoint.channel] ||= []).push(endpoint);
  }
  return grouped;
});

function endpointTarget(endpoint: NotificationEndpointItem): string {
  const config = endpoint.config || {};
  for (const key of ["chat_id", "device_token", "to", "phone_number", "url", "target"]) {
    const value = config[key];
    if (typeof value === "string" && value) return value;
  }
  return "—";
}

async function loadNotifications() {
  notifLoading.value = true;
  notifError.value = "";
  try {
    profile.value = await apiNotifications.getProfile(props.object.id);
    profileName.value = profile.value.name;
    endpoints.value = await apiNotifications.listEndpoints(props.object.id);
  } catch {
    // A 404 simply means this object has no profile yet — that is a normal
    // starting state, not an error to show the administrator.
    profile.value = null;
    profileName.value = `Powiadomienia — ${props.object.name}`;
    endpoints.value = [];
  } finally {
    notifLoading.value = false;
  }
}

async function createProfile() {
  notifError.value = "";
  try {
    profile.value = await apiNotifications.createProfile(props.object.id, profileName.value);
    endpoints.value = [];
  } catch (e) {
    notifError.value = e instanceof Error ? e.message : "Nie udało się utworzyć profilu";
  }
}

async function addEndpoint() {
  if (!profile.value || !newEndpoint.value.target.trim()) return;
  notifError.value = "";
  const channel = CHANNELS.find((c) => c.key === newEndpoint.value.channel);
  if (!channel) return;
  try {
    await apiNotifications.createEndpoint(props.object.id, {
      channel: channel.key,
      label: newEndpoint.value.label,
      config: { [channel.configKey]: newEndpoint.value.target.trim() },
      is_enabled: true,
    });
    newEndpoint.value.label = "";
    newEndpoint.value.target = "";
    endpoints.value = await apiNotifications.listEndpoints(props.object.id);
  } catch (e) {
    notifError.value = e instanceof Error ? e.message : "Nie udało się dodać kanału";
  }
}

async function toggleEndpoint(endpoint: NotificationEndpointItem) {
  notifError.value = "";
  try {
    await apiNotifications.updateEndpoint(props.object.id, endpoint.id, {
      is_enabled: !endpoint.is_enabled,
    });
    endpoints.value = await apiNotifications.listEndpoints(props.object.id);
  } catch (e) {
    notifError.value = e instanceof Error ? e.message : "Nie udało się zmienić kanału";
  }
}

async function removeEndpoint(endpoint: NotificationEndpointItem) {
  if (!confirm("Usunąć ten kanał powiadomień?")) return;
  notifError.value = "";
  try {
    await apiNotifications.deleteEndpoint(props.object.id, endpoint.id);
    endpoints.value = await apiNotifications.listEndpoints(props.object.id);
  } catch (e) {
    notifError.value = e instanceof Error ? e.message : "Nie udało się usunąć kanału";
  }
}

// ─── Save / delete ────────────────────────────────────────────────
const confirmDelete = ref("");
const deleteArmed = computed(
  () => confirmDelete.value.trim().toLowerCase() === props.object.name.trim().toLowerCase(),
);

async function save() {
  saving.value = true;
  error.value = "";
  try {
    await objectsStore.updateObject(props.object.id, {
      name: form.value.name,
      description: form.value.description,
    });
    if (profile.value && profileName.value !== profile.value.name) {
      await apiNotifications.updateProfile(props.object.id, profileName.value);
    }
    emit("saved");
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Nie udało się zapisać obiektu";
  } finally {
    saving.value = false;
  }
}

async function remove() {
  if (!deleteArmed.value) return;
  deleting.value = true;
  error.value = "";
  try {
    await objectsStore.deleteObject(props.object.id);
    emit("deleted");
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Nie udało się usunąć obiektu";
    deleting.value = false;
  }
}

onMounted(() => {
  void loadUsers();
  void loadNotifications();
});
</script>

<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="settings-modal" role="dialog" aria-label="Ustawienia obiektu">
      <header>
        <svg viewBox="0 0 24 24" class="head-icon">
          <path d="M4 21V4h16v17M8 8h2m4 0h2M8 12h2m4 0h2M8 16h2m4 0h2" />
        </svg>
        <div>
          <h2>Ustawienia obiektu</h2>
          <p>{{ object.name }}</p>
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
              <span>Nazwa obiektu</span>
              <input v-model="form.name" maxlength="256" />
            </label>
            <label class="field">
              <span>Opis</span>
              <textarea v-model="form.description" rows="3"></textarea>
            </label>
          </section>

          <!-- USERS -->
          <section v-else-if="section === 'users'">
            <p class="pane-hint">
              Użytkownicy z dostępem widzą pulpit i alarmy tego obiektu.
              Administratorzy mają dostęp do wszystkich obiektów i nie są tu
              wymieniani.
            </p>

            <p v-if="usersLoading" class="muted">Ładowanie…</p>
            <template v-else>
              <table class="grid">
                <thead>
                  <tr>
                    <th>Użytkownik</th>
                    <th>E-mail</th>
                    <th>Rola</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="user in assigned" :key="user.id">
                    <td>
                      <strong>{{ user.username }}</strong>
                      <small v-if="user.full_name">{{ user.full_name }}</small>
                    </td>
                    <td class="dim">{{ user.email }}</td>
                    <td><span class="role">{{ user.role }}</span></td>
                    <td class="right">
                      <button type="button" class="link-danger" @click="revokeAccess(user)">
                        Odbierz dostęp
                      </button>
                    </td>
                  </tr>
                  <tr v-if="!assigned.length">
                    <td colspan="4" class="empty">Brak przypisanych użytkowników</td>
                  </tr>
                </tbody>
              </table>

              <div class="add-row">
                <select v-model="pickedUser">
                  <option value="">Wybierz użytkownika…</option>
                  <option v-for="user in available" :key="user.id" :value="user.id">
                    {{ user.username }} — {{ user.email }}
                  </option>
                </select>
                <button type="button" class="secondary" :disabled="!pickedUser" @click="grantAccess">
                  Nadaj dostęp
                </button>
              </div>
              <p v-if="!available.length" class="muted">
                Wszyscy klienci są już przypisani do obiektów.
              </p>
              <p v-if="usersError" class="error-inline">{{ usersError }}</p>
            </template>
          </section>

          <!-- NOTIFICATIONS -->
          <section v-else-if="section === 'notifications'">
            <p v-if="notifLoading" class="muted">Ładowanie…</p>

            <template v-else-if="!profile">
              <p class="pane-hint">
                Ten obiekt nie ma jeszcze profilu powiadomień. Profil zbiera
                wszystkie kanały alarmowe dla obiektu.
              </p>
              <label class="field">
                <span>Nazwa profilu</span>
                <input v-model="profileName" maxlength="256" />
              </label>
              <button type="button" class="secondary" @click="createProfile">
                Utwórz profil powiadomień
              </button>
            </template>

            <template v-else>
              <label class="field">
                <span>Nazwa profilu</span>
                <input v-model="profileName" maxlength="256" />
              </label>

              <div v-for="channel in CHANNELS" :key="channel.key" class="channel-block">
                <h4>{{ channel.label }}</h4>
                <table class="grid" v-if="endpointsByChannel[channel.key]?.length">
                  <tbody>
                    <tr v-for="endpoint in endpointsByChannel[channel.key]" :key="endpoint.id">
                      <td>
                        <strong>{{ endpoint.label || channel.label }}</strong>
                        <small>{{ endpointTarget(endpoint) }}</small>
                      </td>
                      <td class="right">
                        <button
                          type="button"
                          :class="['pill', endpoint.is_enabled ? 'on' : 'off']"
                          @click="toggleEndpoint(endpoint)"
                        >
                          {{ endpoint.is_enabled ? "Włączony" : "Wyłączony" }}
                        </button>
                        <button type="button" class="link-danger" @click="removeEndpoint(endpoint)">
                          Usuń
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
                <p v-else class="muted small">Brak kanałów</p>
              </div>

              <div class="add-row wrap">
                <select v-model="newEndpoint.channel">
                  <option v-for="channel in CHANNELS" :key="channel.key" :value="channel.key">
                    {{ channel.label }}
                  </option>
                </select>
                <input v-model="newEndpoint.label" placeholder="Etykieta (opcjonalna)" />
                <input
                  v-model="newEndpoint.target"
                  :placeholder="CHANNELS.find((c) => c.key === newEndpoint.channel)?.hint"
                />
                <button
                  type="button"
                  class="secondary"
                  :disabled="!newEndpoint.target.trim()"
                  @click="addEndpoint"
                >
                  Dodaj kanał
                </button>
              </div>
              <p v-if="notifError" class="error-inline">{{ notifError }}</p>
            </template>
          </section>

          <!-- DANGER -->
          <section v-else>
            <p class="pane-hint danger-hint">
              Usunięcie obiektu kasuje jego sensory, pomiary, alarmy i profil
              powiadomień. Przypisani użytkownicy stracą dostęp, ale ich konta
              pozostaną. Operacji nie można cofnąć.
            </p>
            <label class="field">
              <span>Wpisz nazwę obiektu, aby potwierdzić</span>
              <input v-model="confirmDelete" :placeholder="object.name" />
            </label>
            <button type="button" class="delete-btn" :disabled="!deleteArmed || deleting" @click="remove">
              {{ deleting ? "Usuwanie…" : "Usuń obiekt" }}
            </button>
          </section>
        </div>
      </div>

      <p v-if="error" class="error">{{ error }}</p>

      <footer>
        <button type="button" @click="emit('close')" :disabled="saving">Anuluj</button>
        <button type="button" class="primary" :disabled="saving" @click="save">
          {{ saving ? "Zapisywanie…" : "Zapisz" }}
        </button>
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
  width: min(880px, 100%);
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
  grid-template-columns: 190px 1fr;
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
  max-width: 62ch;
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

.field input,
.field textarea {
  width: 100%;
  background: #050f1a;
  border: 1px solid #234662;
  border-radius: 6px;
  color: #f1f6ff;
  padding: 8px 10px;
  font: inherit;
  font-size: 14px;
  resize: vertical;
}

.field input:focus,
.field textarea:focus {
  outline: none;
  border-color: #00b6d6;
}

.grid {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 14px;
  font-size: 13px;
}

.grid th {
  text-align: left;
  font-weight: 500;
  color: #7d93af;
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  padding: 0 10px 7px;
  border-bottom: 1px solid #16324a;
}

.grid td {
  padding: 9px 10px;
  border-bottom: 1px solid #102638;
  vertical-align: middle;
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
  padding: 16px;
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

.add-row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 6px;
}

.add-row.wrap {
  flex-wrap: wrap;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid #16324a;
}

.add-row select,
.add-row input {
  flex: 1;
  min-width: 130px;
  background: #050f1a;
  border: 1px solid #234662;
  border-radius: 6px;
  color: #f1f6ff;
  padding: 8px 10px;
  font: inherit;
  font-size: 13px;
}

.channel-block {
  margin-bottom: 12px;
}

.channel-block h4 {
  margin: 0 0 6px;
  font-size: 13px;
  color: #00dde1;
  font-weight: 500;
}

.pill {
  padding: 3px 10px;
  margin-right: 10px;
  border-radius: 20px;
  border: 1px solid #234662;
  background: transparent;
  color: #9fb6d2;
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.pill.on {
  border-color: #007b52;
  color: #00e08a;
}

.link-danger {
  background: none;
  border: 0;
  color: #e0788a;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  padding: 0;
}

.link-danger:hover {
  color: #ff8497;
  text-decoration: underline;
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

.muted {
  color: #8ea6c4;
  font-size: 13px;
}

.muted.small {
  font-size: 12px;
  margin: 0 0 4px;
}

.error,
.error-inline {
  color: #ff8497;
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
