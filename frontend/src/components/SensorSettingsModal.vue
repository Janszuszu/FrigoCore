<script setup lang="ts">
/**
 * Sensor administration — everything configurable about one sensor in one
 * place: general details, icon, calibration, alarm thresholds, dashboard
 * position and deletion.
 *
 * Alarm thresholds are written through the same /sensors/{id}/alarm-configs
 * endpoint the alarm engine evaluates — this is configuration, and the
 * Alarms page stays a monitoring view.
 */
import { computed, onMounted, ref } from "vue";
import { apiAlarmConfigs, apiSensors } from "@/api";
import type { AlarmConfigItem, SensorItem } from "@/types";
import { SENSOR_ICONS, SENSOR_ICON_IDS, suggestIconFromName } from "@/utils/sensorIcons";
import SensorIcon from "@/components/SensorIcon.vue";

const props = defineProps<{
  sensor: SensorItem;
  /** Every sensor of the object, in current display order. */
  siblings: SensorItem[];
}>();

const emit = defineEmits<{ close: []; saved: []; deleted: [] }>();

type Section = "general" | "icon" | "calibration" | "alarms" | "order" | "danger";
const SECTIONS: { key: Section; label: string }[] = [
  { key: "general", label: "Ogólne" },
  { key: "icon", label: "Ikona" },
  { key: "calibration", label: "Kalibracja" },
  { key: "alarms", label: "Alarmy" },
  { key: "order", label: "Kolejność" },
  { key: "danger", label: "Usuń sensor" },
];
const section = ref<Section>("general");

const loading = ref(true);
const saving = ref(false);
const deleting = ref(false);
const error = ref("");

const form = ref({
  name: props.sensor.name,
  mqtt_topic: props.sensor.mqtt_topic,
  icon: props.sensor.icon || suggestIconFromName(props.sensor.name),
  calibration_offset: props.sensor.calibration_offset ?? 0,
  offline_timeout_seconds: props.sensor.offline_timeout_seconds,
});

// One row per alarm type, mirroring the three AlarmConfig rows on the server.
const existing = ref<Record<AlarmKey, AlarmConfigItem | null>>({
  high_temperature: null,
  low_temperature: null,
  offline: null,
});
type AlarmKey = "high_temperature" | "low_temperature" | "offline";

const alarms = ref({
  high_enabled: false,
  high_temperature: null as number | null,
  high_delay: 300,
  low_enabled: false,
  low_temperature: null as number | null,
  low_delay: 300,
  offline_enabled: false,
  offline_delay: 300,
});

// Position is 1-based for the administrator; display_order is 0-based.
const position = ref(props.siblings.findIndex((s) => s.id === props.sensor.id) + 1 || 1);
const siblingCount = computed(() => Math.max(props.siblings.length, 1));

const confirmDelete = ref("");
const deleteArmed = computed(
  () => confirmDelete.value.trim().toLowerCase() === props.sensor.name.trim().toLowerCase(),
);

onMounted(async () => {
  try {
    const rows = await apiAlarmConfigs.list(props.sensor.id);
    for (const row of rows) {
      if (row.alarm_type === "high_temperature") {
        existing.value.high_temperature = row;
        alarms.value.high_enabled = row.is_enabled;
        alarms.value.high_temperature = row.threshold_value;
        alarms.value.high_delay = row.trigger_delay_seconds;
      } else if (row.alarm_type === "low_temperature") {
        existing.value.low_temperature = row;
        alarms.value.low_enabled = row.is_enabled;
        alarms.value.low_temperature = row.threshold_value;
        alarms.value.low_delay = row.trigger_delay_seconds;
      } else if (row.alarm_type === "offline") {
        existing.value.offline = row;
        alarms.value.offline_enabled = row.is_enabled;
        alarms.value.offline_delay = row.trigger_delay_seconds;
      }
    }
  } catch {
    error.value = "Nie udało się pobrać konfiguracji alarmów";
  } finally {
    loading.value = false;
  }
});

function numeric(value: string): number | null {
  const parsed = parseFloat(value);
  return Number.isNaN(parsed) ? null : parsed;
}

const highTempStr = computed({
  get: () => alarms.value.high_temperature?.toString() ?? "",
  set: (v: string) => (alarms.value.high_temperature = numeric(v)),
});
const lowTempStr = computed({
  get: () => alarms.value.low_temperature?.toString() ?? "",
  set: (v: string) => (alarms.value.low_temperature = numeric(v)),
});
const calibrationStr = computed({
  get: () => form.value.calibration_offset.toString(),
  set: (v: string) => (form.value.calibration_offset = numeric(v) ?? 0),
});

function movePosition(delta: number) {
  const next = position.value + delta;
  if (next >= 1 && next <= siblingCount.value) position.value = next;
}

async function upsertAlarm(
  type: AlarmKey,
  payload: { is_enabled: boolean; threshold_value: number | null; trigger_delay_seconds: number },
) {
  const current = existing.value[type];
  if (current) {
    await apiAlarmConfigs.update(props.sensor.id, current.id, payload);
  } else {
    await apiAlarmConfigs.create(props.sensor.id, { alarm_type: type, ...payload });
  }
}

async function save() {
  saving.value = true;
  error.value = "";
  try {
    await apiSensors.update(props.sensor.object_id, props.sensor.id, {
      name: form.value.name,
      mqtt_topic: form.value.mqtt_topic,
      icon: form.value.icon,
      calibration_offset: form.value.calibration_offset,
      offline_timeout_seconds: form.value.offline_timeout_seconds,
    });

    await Promise.all([
      upsertAlarm("high_temperature", {
        is_enabled: alarms.value.high_enabled,
        threshold_value: alarms.value.high_temperature,
        trigger_delay_seconds: alarms.value.high_delay,
      }),
      upsertAlarm("low_temperature", {
        is_enabled: alarms.value.low_enabled,
        threshold_value: alarms.value.low_temperature,
        trigger_delay_seconds: alarms.value.low_delay,
      }),
      upsertAlarm("offline", {
        is_enabled: alarms.value.offline_enabled,
        threshold_value: null,
        trigger_delay_seconds: alarms.value.offline_delay,
      }),
    ]);

    // Ordering is stored for the whole object, so a position change is sent
    // as the object's full sensor order rather than a lone index.
    const currentIndex = props.siblings.findIndex((s) => s.id === props.sensor.id);
    const targetIndex = position.value - 1;
    if (currentIndex !== -1 && targetIndex !== currentIndex) {
      const ids = props.siblings.map((s) => s.id);
      ids.splice(currentIndex, 1);
      ids.splice(targetIndex, 0, props.sensor.id);
      await apiSensors.reorder(props.sensor.object_id, ids);
    }

    emit("saved");
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Nie udało się zapisać ustawień";
  } finally {
    saving.value = false;
  }
}

async function remove() {
  if (!deleteArmed.value) return;
  deleting.value = true;
  error.value = "";
  try {
    await apiSensors.delete(props.sensor.object_id, props.sensor.id);
    emit("deleted");
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Nie udało się usunąć sensora";
    deleting.value = false;
  }
}
</script>

<template>
  <div class="modal-overlay" @click.self="emit('close')">
    <div class="settings-modal" role="dialog" aria-label="Ustawienia sensora">
      <header>
        <SensorIcon :icon="form.icon" :size="22" />
        <div>
          <h2>Ustawienia sensora</h2>
          <p>{{ sensor.name }}</p>
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
          <p v-if="loading" class="muted">Ładowanie…</p>

          <!-- GENERAL -->
          <section v-else-if="section === 'general'">
            <label class="field">
              <span>Nazwa sensora</span>
              <input v-model="form.name" maxlength="256" />
            </label>
            <label class="field">
              <span>MQTT Topic</span>
              <input v-model="form.mqtt_topic" spellcheck="false" maxlength="512" />
              <small>Musi dokładnie odpowiadać tematowi publikowanemu przez bramkę.</small>
            </label>
          </section>

          <!-- ICON -->
          <section v-else-if="section === 'icon'">
            <p class="pane-hint">
              Wybrana ikona jest zapisywana przy sensorze i widoczna dla wszystkich
              klientów tego obiektu.
            </p>
            <div class="icon-grid">
              <button
                v-for="id in SENSOR_ICON_IDS"
                :key="id"
                type="button"
                :class="['icon-choice', { active: form.icon === id }]"
                :title="SENSOR_ICONS[id].label"
                @click="form.icon = id"
              >
                <SensorIcon :icon="id" :size="26" />
                <span>{{ SENSOR_ICONS[id].label }}</span>
              </button>
            </div>
          </section>

          <!-- CALIBRATION -->
          <section v-else-if="section === 'calibration'">
            <label class="field narrow">
              <span>Korekta temperatury [°C]</span>
              <input v-model="calibrationStr" type="number" step="0.1" min="-20" max="20" />
              <small>
                Wartość dodawana do każdego odczytu, np. -0,5 lub +1,0. Stosowana
                przy zapisie pomiaru, więc obowiązuje też dla progów alarmowych.
              </small>
            </label>
          </section>

          <!-- ALARMS -->
          <section v-else-if="section === 'alarms'" class="alarm-sections">
            <fieldset>
              <legend>Wysoka temperatura</legend>
              <label class="toggle">
                <input v-model="alarms.high_enabled" type="checkbox" class="switch" />
                <span>Włączony</span>
              </label>
              <label class="field narrow">
                <span>Próg [°C]</span>
                <input v-model="highTempStr" type="number" step="0.1" :disabled="!alarms.high_enabled" />
              </label>
              <label class="field narrow">
                <span>Opóźnienie [s]</span>
                <input v-model.number="alarms.high_delay" type="number" step="1" min="0" :disabled="!alarms.high_enabled" />
              </label>
            </fieldset>

            <fieldset>
              <legend>Niska temperatura</legend>
              <label class="toggle">
                <input v-model="alarms.low_enabled" type="checkbox" class="switch" />
                <span>Włączony</span>
              </label>
              <label class="field narrow">
                <span>Próg [°C]</span>
                <input v-model="lowTempStr" type="number" step="0.1" :disabled="!alarms.low_enabled" />
              </label>
              <label class="field narrow">
                <span>Opóźnienie [s]</span>
                <input v-model.number="alarms.low_delay" type="number" step="1" min="0" :disabled="!alarms.low_enabled" />
              </label>
            </fieldset>

            <fieldset>
              <legend>Brak komunikacji (OFFLINE)</legend>
              <label class="toggle">
                <input v-model="alarms.offline_enabled" type="checkbox" class="switch" />
                <span>Włączony</span>
              </label>
              <label class="field narrow">
                <span>Timeout komunikacji [s]</span>
                <input v-model.number="form.offline_timeout_seconds" type="number" step="10" min="10" max="3600" :disabled="!alarms.offline_enabled" />
              </label>
              <label class="field narrow">
                <span>Opóźnienie [s]</span>
                <input v-model.number="alarms.offline_delay" type="number" step="1" min="0" :disabled="!alarms.offline_enabled" />
              </label>
            </fieldset>
          </section>

          <!-- ORDER -->
          <section v-else-if="section === 'order'">
            <p class="pane-hint">
              Kolejność wyświetlania na pulpicie klienta. Ustawienie jest wspólne
              dla wszystkich osób oglądających ten obiekt.
            </p>
            <div class="position-row">
              <label class="field narrow">
                <span>Pozycja</span>
                <input v-model.number="position" type="number" min="1" :max="siblingCount" />
              </label>
              <div class="position-buttons">
                <button type="button" class="icon-btn" aria-label="W górę" :disabled="position <= 1" @click="movePosition(-1)">↑</button>
                <button type="button" class="icon-btn" aria-label="W dół" :disabled="position >= siblingCount" @click="movePosition(1)">↓</button>
              </div>
              <span class="muted">z {{ siblingCount }}</span>
            </div>
          </section>

          <!-- DANGER -->
          <section v-else>
            <p class="pane-hint danger-hint">
              Usunięcie sensora kasuje również jego historię pomiarów i konfigurację
              alarmów. Operacji nie można cofnąć.
            </p>
            <label class="field">
              <span>Wpisz nazwę sensora, aby potwierdzić</span>
              <input v-model="confirmDelete" :placeholder="sensor.name" />
            </label>
            <button
              type="button"
              class="delete-btn"
              :disabled="!deleteArmed || deleting"
              @click="remove"
            >
              {{ deleting ? "Usuwanie…" : "Usuń sensor" }}
            </button>
          </section>
        </div>
      </div>

      <p v-if="error" class="error">{{ error }}</p>

      <footer>
        <button type="button" @click="emit('close')" :disabled="saving">Anuluj</button>
        <button type="button" class="primary" :disabled="saving || loading" @click="save">
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
  color: #00d9ed;
}

header h2 {
  margin: 0;
  font-size: 17px;
  color: #e9f2ff;
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
  max-width: 60ch;
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

.field input {
  width: 100%;
  background: #050f1a;
  border: 1px solid #234662;
  border-radius: 6px;
  color: #f1f6ff;
  padding: 8px 10px;
  font: inherit;
  font-size: 14px;
}

.field.narrow input {
  max-width: 200px;
}

.field input:focus {
  outline: none;
  border-color: #00b6d6;
}

.field input:disabled {
  opacity: 0.4;
}

.field small {
  display: block;
  margin-top: 6px;
  font-size: 12px;
  color: #7d93af;
  line-height: 1.5;
  max-width: 58ch;
}

.icon-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(132px, 1fr));
  gap: 8px;
}

.icon-choice {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 12px 6px;
  background: #061220;
  border: 1px solid #1b3549;
  border-radius: 7px;
  color: #9fb6d2;
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  text-align: center;
}

.icon-choice:hover {
  border-color: #2c5c7d;
  color: #d7e6fa;
}

.icon-choice.active {
  border-color: #00c8dd;
  background: #072a37;
  color: #00dde1;
}

.alarm-sections {
  display: grid;
  gap: 14px;
}

fieldset {
  border: 1px solid #16324a;
  border-radius: 7px;
  padding: 12px 16px 4px;
  margin: 0;
}

legend {
  padding: 0 6px;
  font-size: 13px;
  color: #00dde1;
}

.toggle {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  font-size: 14px;
  cursor: pointer;
}

.switch {
  width: 38px;
  height: 21px;
  appearance: none;
  background: #17303f;
  border-radius: 11px;
  position: relative;
  cursor: pointer;
  transition: background 0.18s;
  flex: none;
}

.switch::before {
  content: "";
  position: absolute;
  top: 3px;
  left: 3px;
  width: 15px;
  height: 15px;
  background: #7a8aa5;
  border-radius: 50%;
  transition: transform 0.18s, background 0.18s;
}

.switch:checked {
  background: #06b6c9;
}

.switch:checked::before {
  transform: translateX(17px);
  background: #fff;
}

.position-row {
  display: flex;
  align-items: flex-end;
  gap: 12px;
}

.position-row .field {
  margin-bottom: 0;
}

.position-buttons {
  display: flex;
  gap: 6px;
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
  font-size: 15px;
}

.icon-btn:hover:not(:disabled) {
  border-color: #00b6d6;
  color: #00dde1;
}

.icon-btn:disabled {
  opacity: 0.35;
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

.error {
  margin: 0;
  padding: 10px 20px;
  color: #ff8497;
  font-size: 13px;
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
