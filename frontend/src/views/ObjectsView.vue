<script setup lang="ts">
/**
 * Administrator Objects panel.
 *
 * Desktop-first: a compact object list that expands into a dense sensor
 * table. Every per-row action lives behind a settings icon (Object →
 * Sensor → Settings) instead of the old selection-checkbox workflow.
 */
import { computed, onMounted, ref } from "vue";
import { useObjectsStore } from "@/stores/objects";
import { useSensorsStore } from "@/stores/sensors";
import { apiSensors } from "@/api";
import type { ObjectItem, SensorItem } from "@/types";
import SensorIcon from "@/components/SensorIcon.vue";
import SensorSettingsModal from "@/components/SensorSettingsModal.vue";
import ObjectSettingsModal from "@/components/ObjectSettingsModal.vue";
import { suggestIconFromName } from "@/utils/sensorIcons";

const objectsStore = useObjectsStore();
const sensorsStore = useSensorsStore();

const expanded = ref<Set<string>>(new Set());
const objectSensors = ref<Record<string, SensorItem[]>>({});
const error = ref("");

async function loadSensors(objectId: string) {
  await sensorsStore.fetchSensors(objectId);
  objectSensors.value = {
    ...objectSensors.value,
    [objectId]: [...sensorsStore.sensors],
  };
}

async function toggle(object: ObjectItem) {
  const next = new Set(expanded.value);
  if (next.has(object.id)) {
    next.delete(object.id);
  } else {
    next.add(object.id);
    await loadSensors(object.id);
  }
  expanded.value = next;
}

const isExpanded = (id: string) => expanded.value.has(id);
const sensorsOf = (id: string) => objectSensors.value[id] ?? [];

// ─── Status ───────────────────────────────────────────────────────
// Timestamps from the API are UTC but not always suffixed, so a plain
// new Date() would read them as local time and misjudge every timeout.
function parseUtc(iso: string) {
  return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`).getTime();
}

function sensorOnline(sensor: SensorItem) {
  if (!sensor.last_message_at) return false;
  return Date.now() - parseUtc(sensor.last_message_at) < sensor.offline_timeout_seconds * 1000;
}

function objectStatus(object: ObjectItem) {
  if (!object.sensor_count) return { text: "BRAK SENSORÓW", cls: "idle" };
  if (object.online_sensor_count === 0) return { text: "OFFLINE", cls: "offline" };
  if (object.online_sensor_count < object.sensor_count)
    return { text: "CZĘŚCIOWO ONLINE", cls: "partial" };
  return { text: "ONLINE", cls: "online" };
}

function temperature(value: number | null) {
  return value == null ? "—" : `${value.toFixed(1)} °C`;
}

function timestamp(value: string | null) {
  return value ? new Date(parseUtc(value)).toLocaleString("pl-PL") : "—";
}

// ─── Add object / add sensor ──────────────────────────────────────
const showAddObject = ref(false);
const showAddSensor = ref(false);
const draft = ref({ name: "", description: "", mqtt_topic: "", objectId: "" });

function openAddObject() {
  draft.value = { name: "", description: "", mqtt_topic: "", objectId: "" };
  error.value = "";
  showAddObject.value = true;
}

function openAddSensor(objectId: string) {
  draft.value = { name: "", description: "", mqtt_topic: "", objectId };
  error.value = "";
  showAddSensor.value = true;
}

async function createObject() {
  try {
    await objectsStore.createObject({
      name: draft.value.name,
      description: draft.value.description,
    });
    showAddObject.value = false;
    await objectsStore.fetchObjects();
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Nie udało się dodać obiektu";
  }
}

async function createSensor() {
  try {
    await sensorsStore.createSensor(draft.value.objectId, {
      name: draft.value.name,
      mqtt_topic: draft.value.mqtt_topic,
      // Pre-select a sensible icon from the name; the administrator can
      // change it in sensor settings at any time.
      icon: suggestIconFromName(draft.value.name),
    });
    showAddSensor.value = false;
    await Promise.all([loadSensors(draft.value.objectId), objectsStore.fetchObjects()]);
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Nie udało się dodać sensora";
  }
}

// ─── Settings modals ──────────────────────────────────────────────
const objectSettings = ref<ObjectItem | null>(null);
const sensorSettings = ref<SensorItem | null>(null);

async function onObjectSaved() {
  const target = objectSettings.value;
  objectSettings.value = null;
  await objectsStore.fetchObjects();
  if (target && isExpanded(target.id)) await loadSensors(target.id);
}

async function onObjectDeleted() {
  const target = objectSettings.value;
  objectSettings.value = null;
  if (target) {
    const next = new Set(expanded.value);
    next.delete(target.id);
    expanded.value = next;
  }
  await objectsStore.fetchObjects();
}

async function onSensorSaved() {
  const objectId = sensorSettings.value?.object_id;
  sensorSettings.value = null;
  if (objectId) await Promise.all([loadSensors(objectId), objectsStore.fetchObjects()]);
}

async function onSensorDeleted() {
  const objectId = sensorSettings.value?.object_id;
  sensorSettings.value = null;
  if (objectId) await Promise.all([loadSensors(objectId), objectsStore.fetchObjects()]);
}

// ─── Drag and drop ordering ───────────────────────────────────────
// The order is object configuration, so a drop writes the object's whole
// sensor order back to the server; every client then sees the same one.
const dragging = ref<{ objectId: string; sensorId: string } | null>(null);
const dragOverId = ref<string | null>(null);
const reordering = ref(false);

function onDragStart(objectId: string, sensor: SensorItem) {
  dragging.value = { objectId, sensorId: sensor.id };
}

function onDragOver(sensor: SensorItem) {
  if (dragging.value) dragOverId.value = sensor.id;
}

function onDragEnd() {
  dragging.value = null;
  dragOverId.value = null;
}

async function onDrop(objectId: string, target: SensorItem) {
  const source = dragging.value;
  onDragEnd();
  if (!source || source.objectId !== objectId || source.sensorId === target.id) return;

  const ids = sensorsOf(objectId).map((s) => s.id);
  const from = ids.indexOf(source.sensorId);
  const to = ids.indexOf(target.id);
  if (from === -1 || to === -1) return;
  ids.splice(from, 1);
  ids.splice(to, 0, source.sensorId);

  reordering.value = true;
  try {
    objectSensors.value = {
      ...objectSensors.value,
      [objectId]: await apiSensors.reorder(objectId, ids),
    };
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Nie udało się zapisać kolejności";
    await loadSensors(objectId);
  } finally {
    reordering.value = false;
  }
}

const totalSensors = computed(() =>
  objectsStore.objects.reduce((sum, o) => sum + (o.sensor_count || 0), 0),
);

onMounted(async () => {
  await objectsStore.fetchObjects();
  const first = objectsStore.objects[0];
  if (first) {
    expanded.value = new Set([first.id]);
    await loadSensors(first.id);
  }
});
</script>

<template>
  <section class="objects-page">
    <header class="page-head">
      <div>
        <h1>Obiekty</h1>
        <p>
          {{ objectsStore.objects.length }} obiektów · {{ totalSensors }} sensorów
        </p>
      </div>
      <button class="primary" @click="openAddObject">＋ Dodaj obiekt</button>
    </header>

    <p v-if="error" class="page-error">{{ error }}</p>

    <div class="object-list">
      <article
        v-for="object in objectsStore.objects"
        :key="object.id"
        class="object-card"
        :class="{ open: isExpanded(object.id) }"
      >
        <div class="object-row">
          <button
            class="expander"
            :aria-expanded="isExpanded(object.id)"
            :aria-label="`Rozwiń ${object.name}`"
            @click="toggle(object)"
          >
            <svg viewBox="0 0 24 24" class="object-icon">
              <path d="M4 21V4h16v17M8 8h2m4 0h2M8 12h2m4 0h2M8 16h2m4 0h2" />
            </svg>
            <span class="object-name">{{ object.name }}</span>
          </button>

          <span :class="['status', objectStatus(object).cls]">
            <i></i>{{ objectStatus(object).text }}
          </span>

          <span class="sensor-count">
            {{ object.online_sensor_count }}/{{ object.sensor_count }} sensorów
          </span>

          <div class="row-actions">
            <button
              class="icon-btn"
              title="Ustawienia obiektu"
              aria-label="Ustawienia obiektu"
              @click="objectSettings = object"
            >
              <svg viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.1 2.1-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56v.1h-3v-.1a1.7 1.7 0 0 0-1.03-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06-2.1-2.1.06-.06A1.7 1.7 0 0 0 7.06 15a1.7 1.7 0 0 0-1.56-1.03h-.1v-3h.1A1.7 1.7 0 0 0 7.06 9.94a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.1-2.1.06.06a1.7 1.7 0 0 0 1.88.34 1.7 1.7 0 0 0 1.03-1.56v-.1h3v.1a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.1 2.1-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.03h.1v3h-.1A1.7 1.7 0 0 0 19.4 15Z" />
              </svg>
            </button>
            <button
              class="icon-btn chevron"
              :aria-label="isExpanded(object.id) ? 'Zwiń' : 'Rozwiń'"
              @click="toggle(object)"
            >
              <svg viewBox="0 0 24 24">
                <path :d="isExpanded(object.id) ? 'M6 15l6-6 6 6' : 'M9 6l6 6-6 6'" />
              </svg>
            </button>
          </div>
        </div>

        <div v-if="isExpanded(object.id)" class="sensor-panel">
          <table class="sensor-table">
            <thead>
              <tr>
                <th class="col-drag"></th>
                <th class="col-name">Sensor</th>
                <th class="col-topic">MQTT Topic</th>
                <th class="col-value">Wartość</th>
                <th class="col-time">Ostatnia aktualizacja</th>
                <th class="col-settings"></th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="sensor in sensorsOf(object.id)"
                :key="sensor.id"
                draggable="true"
                :class="{
                  'drop-target': dragOverId === sensor.id,
                  dragging: dragging?.sensorId === sensor.id,
                }"
                @dragstart="onDragStart(object.id, sensor)"
                @dragover.prevent="onDragOver(sensor)"
                @drop.prevent="onDrop(object.id, sensor)"
                @dragend="onDragEnd"
              >
                <td class="col-drag">
                  <span class="drag-handle" title="Przeciągnij, aby zmienić kolejność">⣿</span>
                </td>
                <td class="col-name">
                  <SensorIcon :icon="sensor.icon" :size="18" />
                  <span>{{ sensor.name }}</span>
                  <i v-if="!sensorOnline(sensor)" class="dot offline" title="Offline"></i>
                  <i v-else class="dot online" title="Online"></i>
                </td>
                <td class="col-topic"><code>{{ sensor.mqtt_topic }}</code></td>
                <td class="col-value">
                  <strong>{{ sensorOnline(sensor) ? temperature(sensor.current_temperature) : "—" }}</strong>
                  <em v-if="sensor.calibration_offset" class="calib">
                    {{ sensor.calibration_offset > 0 ? "+" : "" }}{{ sensor.calibration_offset }}°
                  </em>
                </td>
                <td class="col-time">{{ timestamp(sensor.last_message_at) }}</td>
                <td class="col-settings">
                  <button
                    class="icon-btn"
                    title="Ustawienia sensora"
                    aria-label="Ustawienia sensora"
                    @click="sensorSettings = sensor"
                  >
                    <svg viewBox="0 0 24 24">
                      <circle cx="12" cy="12" r="3" />
                      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.1 2.1-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56v.1h-3v-.1a1.7 1.7 0 0 0-1.03-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06-2.1-2.1.06-.06A1.7 1.7 0 0 0 7.06 15a1.7 1.7 0 0 0-1.56-1.03h-.1v-3h.1A1.7 1.7 0 0 0 7.06 9.94a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.1-2.1.06.06a1.7 1.7 0 0 0 1.88.34 1.7 1.7 0 0 0 1.03-1.56v-.1h3v.1a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.1 2.1-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.03h.1v3h-.1A1.7 1.7 0 0 0 19.4 15Z" />
                    </svg>
                  </button>
                </td>
              </tr>
              <tr v-if="!sensorsOf(object.id).length">
                <td colspan="6" class="no-sensors">Brak sensorów w tym obiekcie</td>
              </tr>
            </tbody>
          </table>

          <div class="panel-foot">
            <button class="secondary" @click="openAddSensor(object.id)">＋ Dodaj sensor</button>
            <span v-if="reordering" class="muted">Zapisywanie kolejności…</span>
            <span v-else-if="sensorsOf(object.id).length > 1" class="muted">
              Przeciągnij wiersz, aby zmienić kolejność na pulpicie klienta.
            </span>
          </div>
        </div>
      </article>

      <p v-if="!objectsStore.objects.length" class="no-objects">
        Brak obiektów. Dodaj pierwszy obiekt, aby rozpocząć konfigurację.
      </p>
    </div>

    <!-- Add object / add sensor -->
    <div
      v-if="showAddObject || showAddSensor"
      class="modal"
      @click.self="showAddObject = false; showAddSensor = false"
    >
      <form @submit.prevent="showAddObject ? createObject() : createSensor()">
        <h2>{{ showAddObject ? "Dodaj obiekt" : "Dodaj sensor" }}</h2>
        <label>
          Nazwa
          <input v-model="draft.name" required />
        </label>
        <label v-if="showAddObject">
          Opis
          <textarea v-model="draft.description"></textarea>
        </label>
        <label v-else>
          MQTT Topic
          <input v-model="draft.mqtt_topic" spellcheck="false" required />
        </label>
        <p v-if="error" class="error">{{ error }}</p>
        <footer>
          <button type="button" @click="showAddObject = false; showAddSensor = false">
            Anuluj
          </button>
          <button class="primary">Zapisz</button>
        </footer>
      </form>
    </div>

    <ObjectSettingsModal
      v-if="objectSettings"
      :object="objectSettings"
      @close="objectSettings = null"
      @saved="onObjectSaved"
      @deleted="onObjectDeleted"
    />

    <SensorSettingsModal
      v-if="sensorSettings"
      :sensor="sensorSettings"
      :siblings="sensorsOf(sensorSettings.object_id)"
      @close="sensorSettings = null"
      @saved="onSensorSaved"
      @deleted="onSensorDeleted"
    />
  </section>
</template>

<style scoped>
.objects-page {
  padding: 20px 28px 36px;
  max-width: 1680px;
  margin: 0 auto;
}

.page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 18px;
}

.page-head h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
}

.page-head p {
  margin: 3px 0 0;
  font-size: 13px;
  color: #8ea6c4;
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
}

.secondary {
  padding: 7px 14px;
  background: #072a37;
  border: 1px solid #00aee2;
  border-radius: 6px;
  color: #00d9ed;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.page-error {
  margin: 0 0 14px;
  padding: 9px 12px;
  border: 1px solid #7c1122;
  border-radius: 6px;
  background: #1d0810;
  color: #ff8497;
  font-size: 13px;
}

.object-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.object-card {
  background: #081420;
  border: 1px solid #15304a;
  border-radius: 8px;
  overflow: hidden;
}

.object-card.open {
  border-color: #1d476a;
}

.object-row {
  display: flex;
  align-items: center;
  gap: 18px;
  height: 52px;
  padding: 0 14px;
}

.expander {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 280px;
  background: none;
  border: 0;
  padding: 0;
  color: #e9f2ff;
  font: inherit;
  cursor: pointer;
  text-align: left;
}

.object-icon {
  width: 20px;
  height: 20px;
  fill: none;
  stroke: #00d9ed;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
  flex: none;
}

.object-name {
  font-size: 15px;
  font-weight: 500;
}

.status {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 3px 10px;
  border-radius: 20px;
  border: 1px solid #234662;
  font-size: 11px;
  letter-spacing: 0.05em;
  color: #9fb6d2;
  white-space: nowrap;
}

.status i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}

.status.online {
  color: #00e08a;
  border-color: #0a6a48;
}

.status.partial {
  color: #ffb547;
  border-color: #6d4a11;
}

.status.offline {
  color: #ff7380;
  border-color: #6d2530;
}

.status.idle {
  color: #7d93af;
}

.sensor-count {
  font-size: 13px;
  color: #8ea6c4;
  white-space: nowrap;
}

.row-actions {
  margin-left: auto;
  display: flex;
  gap: 6px;
}

.icon-btn {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  color: #8ea6c4;
  cursor: pointer;
  padding: 0;
}

.icon-btn svg {
  width: 17px;
  height: 17px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.icon-btn:hover {
  border-color: #234662;
  background: #0d2334;
  color: #00dde1;
}

/* ---------- Sensor table ---------- */
.sensor-panel {
  border-top: 1px solid #12293e;
  background: #061119;
}

.sensor-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.sensor-table th {
  text-align: left;
  padding: 9px 14px;
  font-weight: 500;
  font-size: 11px;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: #6f87a4;
  border-bottom: 1px solid #12293e;
  background: #050e17;
}

.sensor-table td {
  padding: 8px 14px;
  border-bottom: 1px solid #0e2233;
  color: #cddcef;
  vertical-align: middle;
}

.sensor-table tbody tr:last-child td {
  border-bottom: 0;
}

.sensor-table tbody tr:hover {
  background: #091a27;
}

.sensor-table tr.dragging {
  opacity: 0.4;
}

.sensor-table tr.drop-target td {
  box-shadow: inset 0 2px 0 #00c8dd;
}

.col-drag {
  width: 28px;
}

.drag-handle {
  color: #3d5871;
  cursor: grab;
  font-size: 11px;
  letter-spacing: -2px;
  user-select: none;
}

.col-name {
  width: 24%;
}

.col-name > * {
  vertical-align: middle;
}

.col-name span {
  margin: 0 8px 0 9px;
  color: #e9f2ff;
}

.dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.dot.online {
  background: #00e08a;
}

.dot.offline {
  background: #ff7380;
}

.col-topic {
  width: 30%;
}

.col-topic code {
  color: #82b6d6;
  font-size: 12px;
  word-break: break-all;
}

.col-value {
  width: 12%;
  white-space: nowrap;
}

.col-value strong {
  color: #00baf2;
  font-weight: 600;
  font-size: 14px;
}

.calib {
  margin-left: 6px;
  font-style: normal;
  font-size: 11px;
  color: #7d93af;
}

.col-time {
  width: 20%;
  color: #92a9c5;
  white-space: nowrap;
}

.col-settings {
  text-align: right;
  width: 46px;
}

.no-sensors,
.no-objects {
  text-align: center;
  padding: 20px;
  color: #7d93af;
  font-size: 13px;
}

.panel-foot {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 11px 14px;
  border-top: 1px solid #0e2233;
}

.muted {
  font-size: 12px;
  color: #6f87a4;
}

/* ---------- Add modal ---------- */
.modal {
  position: fixed;
  inset: 0;
  background: rgba(2, 8, 15, 0.78);
  display: grid;
  place-items: center;
  z-index: 20;
  padding: 24px;
}

.modal form {
  width: min(440px, 100%);
  padding: 22px;
  background: #08151f;
  border: 1px solid #1d3b53;
  border-radius: 10px;
}

.modal h2 {
  margin: 0 0 18px;
  font-size: 17px;
  font-weight: 600;
}

.modal label {
  display: grid;
  gap: 6px;
  color: #a9bdd8;
  font-size: 13px;
  margin-bottom: 14px;
}

.modal input,
.modal textarea {
  background: #050f1a;
  border: 1px solid #234662;
  border-radius: 6px;
  color: #f1f6ff;
  padding: 8px 10px;
  font: inherit;
  font-size: 14px;
}

.modal textarea {
  min-height: 70px;
  resize: vertical;
}

.modal .error {
  color: #ff8497;
  font-size: 13px;
}

.modal footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}

.modal footer button {
  padding: 8px 18px;
  border: 1px solid #234662;
  border-radius: 6px;
  background: #0b1e2d;
  color: #e9f2ff;
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

/* Narrow screens: this is a desktop administration panel, so it degrades
   to a horizontally scrollable table rather than restacking into cards. */
@media (max-width: 900px) {
  .objects-page {
    padding: 16px 12px 28px;
  }
  .object-row {
    gap: 10px;
  }
  .expander {
    min-width: 0;
  }
  .sensor-count {
    display: none;
  }
  .sensor-panel {
    overflow-x: auto;
  }
  .sensor-table {
    min-width: 780px;
  }
}
</style>
