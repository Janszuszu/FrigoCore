<script setup lang="ts">
/**
 * Ustawienia → Połączenia alarmowe — VoIPstudio API key, caller ID,
 * connection tests, and which phone numbers get called for each object's
 * alarms. Admin only (SettingsView is gated in App.vue).
 */
import { onMounted, reactive, ref } from "vue";
import { apiVoip } from "@/api";
import type { ObjectVoiceNumbers, VoiceNumber, VoipSettings, VoipTestResult } from "@/types";

const config = ref<VoipSettings | null>(null);
const objects = ref<ObjectVoiceNumbers[]>([]);
const loading = ref(true);
const loadError = ref("");

const tokenInput = ref("");
const callerIdInput = ref("");
const savingConfig = ref(false);
const configMessage = ref<VoipTestResult | null>(null);

const testing = ref(false);
const testPhone = ref("");
const calling = ref(false);
const testMessage = ref<VoipTestResult | null>(null);

// Per-object "add number" form state, keyed by object_id.
const drafts = reactive<Record<string, { label: string; phone: string }>>({});
const numbersError = reactive<Record<string, string>>({});
const busy = ref(false);

/** The API client throws the raw response body — surface FastAPI's `detail`. */
function errorText(e: unknown, fallback: string): string {
  if (!(e instanceof Error)) return fallback;
  try {
    const detail = JSON.parse(e.message).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return "Nieprawidłowe dane";
  } catch {
    /* not JSON */
  }
  return e.message || fallback;
}

function formatPhone(digits: string): string {
  if (/^48\d{9}$/.test(digits)) {
    return `+48 ${digits.slice(2, 5)} ${digits.slice(5, 8)} ${digits.slice(8)}`;
  }
  return `+${digits}`;
}

function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleString("pl-PL") : "";
}

function draftFor(objectId: string) {
  return (drafts[objectId] ||= { label: "", phone: "" });
}

async function load() {
  loading.value = true;
  loadError.value = "";
  try {
    const [settings, numbers] = await Promise.all([apiVoip.get(), apiVoip.listNumbers()]);
    config.value = settings;
    callerIdInput.value = settings.caller_id ? `+${settings.caller_id}` : "";
    objects.value = numbers;
  } catch (e) {
    loadError.value = errorText(e, "Nie udało się wczytać ustawień");
  } finally {
    loading.value = false;
  }
}

onMounted(load);

async function saveConfig() {
  savingConfig.value = true;
  configMessage.value = null;
  try {
    const update: { api_token?: string; caller_id: string } = { caller_id: callerIdInput.value.trim() };
    if (tokenInput.value.trim()) update.api_token = tokenInput.value.trim();
    config.value = await apiVoip.update(update);
    callerIdInput.value = config.value.caller_id ? `+${config.value.caller_id}` : "";
    tokenInput.value = "";
    configMessage.value = { ok: true, detail: "Zapisano" };
  } catch (e) {
    configMessage.value = { ok: false, detail: errorText(e, "Nie udało się zapisać") };
  } finally {
    savingConfig.value = false;
  }
}

async function removeToken() {
  if (!confirm("Usunąć klucz API? Połączenia alarmowe przestaną działać.")) return;
  savingConfig.value = true;
  configMessage.value = null;
  try {
    config.value = await apiVoip.update({ api_token: "" });
  } catch (e) {
    configMessage.value = { ok: false, detail: errorText(e, "Nie udało się usunąć klucza") };
  } finally {
    savingConfig.value = false;
  }
}

async function testConnection() {
  testing.value = true;
  testMessage.value = null;
  try {
    testMessage.value = await apiVoip.test();
  } catch (e) {
    testMessage.value = { ok: false, detail: errorText(e, "Test nie powiódł się") };
  } finally {
    testing.value = false;
  }
}

async function testCall() {
  calling.value = true;
  testMessage.value = null;
  try {
    testMessage.value = await apiVoip.testCall(testPhone.value.trim());
  } catch (e) {
    testMessage.value = { ok: false, detail: errorText(e, "Nie udało się zadzwonić") };
  } finally {
    calling.value = false;
  }
}

async function addNumber(entry: ObjectVoiceNumbers) {
  const draft = draftFor(entry.object_id);
  numbersError[entry.object_id] = "";
  busy.value = true;
  try {
    const created = await apiVoip.addNumber(entry.object_id, draft.phone.trim(), draft.label.trim());
    entry.numbers.push(created);
    draft.phone = "";
    draft.label = "";
  } catch (e) {
    numbersError[entry.object_id] = errorText(e, "Nie udało się dodać numeru");
  } finally {
    busy.value = false;
  }
}

async function toggleNumber(entry: ObjectVoiceNumbers, number: VoiceNumber) {
  numbersError[entry.object_id] = "";
  busy.value = true;
  try {
    Object.assign(number, await apiVoip.updateNumber(number.id, { is_enabled: !number.is_enabled }));
  } catch (e) {
    numbersError[entry.object_id] = errorText(e, "Nie udało się zmienić numeru");
  } finally {
    busy.value = false;
  }
}

async function removeNumber(entry: ObjectVoiceNumbers, number: VoiceNumber) {
  if (!confirm(`Usunąć numer ${formatPhone(number.phone_number)} z obiektu ${entry.object_name}?`)) return;
  numbersError[entry.object_id] = "";
  busy.value = true;
  try {
    await apiVoip.deleteNumber(number.id);
    entry.numbers = entry.numbers.filter((n) => n.id !== number.id);
  } catch (e) {
    numbersError[entry.object_id] = errorText(e, "Nie udało się usunąć numeru");
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="voice-settings">
    <p v-if="loading" class="muted">Ładowanie…</p>
    <p v-else-if="loadError" class="error">{{ loadError }}</p>

    <template v-else-if="config">
      <!-- ── Integration ─────────────────────────────────────────── -->
      <section class="card">
        <header>
          <h2>Integracja VoIPstudio</h2>
          <span :class="['badge', config.token_configured ? 'on' : 'off']">
            {{ config.token_configured ? "Aktywna" : "Nieskonfigurowana" }}
          </span>
        </header>

        <p v-if="config.token_unreadable" class="error">
          Zapisanego klucza nie da się odczytać (zmieniono SECRET_KEY serwera). Wpisz klucz ponownie.
        </p>
        <p v-else-if="config.token_configured" class="muted">
          Klucz API: <code>••••{{ config.token_hint }}</code> · zapisany {{ formatDate(config.token_updated_at) }}
        </p>
        <p v-else class="muted">
          Wygeneruj klucz w panelu VoIPstudio: Administracja → Użytkownicy → API Keys, i wklej go poniżej.
        </p>

        <div class="form-grid">
          <label class="field">
            <span>{{ config.token_configured ? "Nowy klucz API (zostaw puste, aby nie zmieniać)" : "Klucz API" }}</span>
            <input
              v-model="tokenInput"
              type="password"
              autocomplete="off"
              maxlength="256"
              placeholder="wklej klucz z VoIPstudio"
            />
          </label>
          <label class="field">
            <span>Numer prezentowany (puste = numer ukryty)</span>
            <input v-model="callerIdInput" maxlength="32" placeholder="np. +48 22 123 45 67" />
          </label>
        </div>

        <div class="actions">
          <button type="button" class="primary" :disabled="savingConfig" @click="saveConfig">
            {{ savingConfig ? "Zapisywanie…" : "Zapisz" }}
          </button>
          <button
            v-if="config.token_configured"
            type="button"
            class="link-danger"
            :disabled="savingConfig"
            @click="removeToken"
          >
            Usuń klucz
          </button>
          <span v-if="configMessage" :class="configMessage.ok ? 'ok' : 'error'">{{ configMessage.detail }}</span>
        </div>

        <div class="divider"></div>

        <h3>Test</h3>
        <div class="actions wrap">
          <button
            type="button"
            class="secondary"
            :disabled="testing || !config.token_configured"
            @click="testConnection"
          >
            {{ testing ? "Sprawdzanie…" : "Sprawdź połączenie" }}
          </button>
          <input v-model="testPhone" class="phone" maxlength="32" placeholder="Twój numer, np. 600 100 200" />
          <button
            type="button"
            class="secondary"
            :disabled="calling || !config.token_configured || !testPhone.trim()"
            @click="testCall"
          >
            {{ calling ? "Dzwonię…" : "Zadzwoń testowo" }}
          </button>
        </div>
        <p v-if="testMessage" :class="testMessage.ok ? 'ok' : 'error'">{{ testMessage.detail }}</p>
      </section>

      <!-- ── Per-object numbers ──────────────────────────────────── -->
      <section class="card">
        <header>
          <h2>Numery alarmowe obiektów</h2>
        </header>
        <p class="muted">
          Gdy w obiekcie wystąpi alarm, system dzwoni na każdy włączony numer tego obiektu
          i odczytuje komunikat o alarmie.
        </p>

        <p v-if="!objects.length" class="muted">Brak obiektów.</p>

        <div v-for="entry in objects" :key="entry.object_id" class="object-block">
          <h4>
            {{ entry.object_name }}
            <small>{{ entry.numbers.length ? `${entry.numbers.length} nr` : "brak numerów" }}</small>
          </h4>

          <table v-if="entry.numbers.length" class="grid">
            <tbody>
              <tr v-for="number in entry.numbers" :key="number.id">
                <td>
                  <strong>{{ formatPhone(number.phone_number) }}</strong>
                  <small v-if="number.label">{{ number.label }}</small>
                </td>
                <td class="right">
                  <button
                    type="button"
                    :class="['pill', number.is_enabled ? 'on' : 'off']"
                    :disabled="busy"
                    @click="toggleNumber(entry, number)"
                  >
                    {{ number.is_enabled ? "Włączony" : "Wyłączony" }}
                  </button>
                  <button type="button" class="link-danger" :disabled="busy" @click="removeNumber(entry, number)">
                    Usuń
                  </button>
                </td>
              </tr>
            </tbody>
          </table>

          <div class="actions wrap">
            <input
              v-model="draftFor(entry.object_id).label"
              class="label"
              maxlength="256"
              placeholder="Opis, np. Serwis / Klient"
            />
            <input
              v-model="draftFor(entry.object_id).phone"
              class="phone"
              maxlength="32"
              placeholder="Numer telefonu"
              @keyup.enter="draftFor(entry.object_id).phone.trim() && addNumber(entry)"
            />
            <button
              type="button"
              class="secondary"
              :disabled="busy || !draftFor(entry.object_id).phone.trim()"
              @click="addNumber(entry)"
            >
              + Dodaj numer
            </button>
          </div>
          <p v-if="numbersError[entry.object_id]" class="error">{{ numbersError[entry.object_id] }}</p>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.voice-settings {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.card {
  background: #08151f;
  border: 1px solid #1d3b53;
  border-radius: 10px;
  padding: 18px 20px;
}

.card header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
}

.card h2 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
  color: #e9f2ff;
}

.card h3 {
  font-size: 13px;
  font-weight: 600;
  margin: 0 0 10px;
  color: #b9cbe2;
}

.badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 20px;
  border: 1px solid;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.badge.on {
  color: #00e08a;
  border-color: #0b6b48;
}

.badge.off {
  color: #e0b36b;
  border-color: #6b5220;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
  margin: 14px 0;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: #90a7c4;
}

input {
  padding: 8px 10px;
  background: #061220;
  border: 1px solid #234662;
  border-radius: 6px;
  color: #e9f2ff;
  font: inherit;
  font-size: 13px;
  min-width: 0;
}

input:focus {
  outline: none;
  border-color: #06c7f3;
}

input.phone {
  width: 200px;
}

input.label {
  width: 200px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.actions.wrap {
  flex-wrap: wrap;
}

.divider {
  border-top: 1px solid #16324a;
  margin: 18px 0 14px;
}

.primary,
.secondary {
  padding: 8px 16px;
  border-radius: 6px;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.primary {
  background: linear-gradient(115deg, #06c7f3, #078de4);
  border: 1px solid #139de5;
  color: #02141f;
}

.secondary {
  background: #0c2233;
  border: 1px solid #234662;
  color: #cfe0f5;
}

button:disabled {
  opacity: 0.5;
  cursor: default;
}

.link-danger {
  background: none;
  border: 0;
  color: #ff8497;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  padding: 0 0 0 10px;
}

.object-block {
  border-top: 1px solid #16324a;
  padding: 14px 0 4px;
}

.object-block h4 {
  margin: 0 0 10px;
  font-size: 14px;
  font-weight: 600;
  color: #e9f2ff;
}

.object-block h4 small {
  margin-left: 8px;
  font-weight: 400;
  font-size: 12px;
  color: #7d93af;
}

.grid {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-bottom: 10px;
}

.grid td {
  padding: 8px 10px;
  border-bottom: 1px solid #102638;
  color: #dbe6f4;
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

.grid .right {
  text-align: right;
  white-space: nowrap;
}

.pill {
  padding: 3px 10px;
  border-radius: 20px;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
  background: none;
  border: 1px solid;
}

.pill.on {
  color: #00e08a;
  border-color: #0b6b48;
}

.pill.off {
  color: #8ea6c4;
  border-color: #234662;
}

code {
  color: #cfe0f5;
}

.muted {
  color: #8ea6c4;
  font-size: 13px;
  margin: 0 0 6px;
}

.ok {
  color: #00e08a;
  font-size: 13px;
}

.error {
  color: #ff8497;
  font-size: 13px;
  margin: 8px 0 0;
}

@media (max-width: 600px) {
  .card {
    padding: 14px;
  }

  input.phone,
  input.label {
    width: 100%;
  }
}
</style>
