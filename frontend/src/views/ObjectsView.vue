<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useObjectsStore } from "@/stores/objects";
import { useSensorsStore } from "@/stores/sensors";
import type { ObjectItem, SensorItem } from "@/types";
import FrigoCheckbox from "@/components/FrigoCheckbox.vue";
import AlarmConfigModal from "@/components/AlarmConfigModal.vue";

const objectsStore = useObjectsStore();
const sensorsStore = useSensorsStore();

// ─── Expand / collapse ────────────────────────────────────────────
const expanded = ref<string | null>(null);
const objectSensors = ref<Record<string, SensorItem[]>>({});

async function loadSensors(id: string) {
  await sensorsStore.fetchSensors(id);
  objectSensors.value[id] = [...sensorsStore.sensors];
}

async function toggle(obj: ObjectItem) {
  expanded.value = expanded.value === obj.id ? null : obj.id;
  if (expanded.value) await loadSensors(obj.id);
}

// ─── Object selection (checkbox) ──────────────────────────────────
const selectedObjects = ref<Set<string>>(new Set());
const selectedSensors = ref<Set<string>>(new Set());

/** Compute a given object's checkbox state */
function objectCheckState(objId: string): boolean | 'indeterminate' {
  const sens = objectSensors.value[objId] || [];
  if (!sens.length) return selectedObjects.value.has(objId);
  const checkedCount = sens.filter(s => selectedSensors.value.has(s.id)).length;
  if (checkedCount === 0) return selectedObjects.value.has(objId);
  if (checkedCount === sens.length) return true;
  return 'indeterminate';
}

function toggleObject(objId: string) {
  const sens = objectSensors.value[objId] || [];
  const currentlyChecked = objectCheckState(objId);
  const willCheck = currentlyChecked === true ? false : true;

  if (willCheck) {
    selectedObjects.value.add(objId);
    sens.forEach(s => selectedSensors.value.add(s.id));
  } else {
    selectedObjects.value.delete(objId);
    sens.forEach(s => selectedSensors.value.delete(s.id));
  }
  // Force reactivity
  selectedObjects.value = new Set(selectedObjects.value);
  selectedSensors.value = new Set(selectedSensors.value);
}

function toggleSensor(sensorId: string, objId: string) {
  if (selectedSensors.value.has(sensorId)) {
    selectedSensors.value.delete(sensorId);
  } else {
    selectedSensors.value.add(sensorId);
  }
  // Re-evaluate object checkbox – if all sensors are checked, check the object
  const sens = objectSensors.value[objId] || [];
  const allChecked = sens.every(s => selectedSensors.value.has(s.id));
  if (allChecked) {
    selectedObjects.value.add(objId);
  } else {
    selectedObjects.value.delete(objId);
  }
  selectedSensors.value = new Set(selectedSensors.value);
  selectedObjects.value = new Set(selectedObjects.value);
}

// ─── Object CRUD ──────────────────────────────────────────────────
const showObjectModal = ref(false);
const editing = ref<ObjectItem | null>(null);
const name = ref("");
const description = ref("");
const error = ref("");

function openObject(obj?: ObjectItem) {
  editing.value = obj || null;
  name.value = obj?.name || "";
  description.value = obj?.description || "";
  error.value = "";
  showObjectModal.value = true;
}

async function saveObject() {
  try {
    if (editing.value) {
      await objectsStore.updateObject(editing.value.id, {
        name: name.value,
        description: description.value,
      });
    } else {
      await objectsStore.createObject({
        name: name.value,
        description: description.value,
      });
    }
    showObjectModal.value = false;
    await objectsStore.fetchObjects();
  } catch (e) {
    error.value =
      e instanceof Error ? e.message : "Nie udało się zapisać";
  }
}

async function removeObjects() {
  if (selectedObjects.value.size === 0) return;
  const count = selectedObjects.value.size;
  if (!confirm(`Usunąć ${count} zaznaczonych obiektów?`)) return;
  for (const id of selectedObjects.value) {
    await objectsStore.deleteObject(id);
  }
  selectedObjects.value = new Set();
  selectedSensors.value = new Set();
}

// ─── Sensor CRUD ──────────────────────────────────────────────────
const showSensorModal = ref(false);
const targetObject = ref("");
const mqttTopic = ref("");

function openSensor(id: string) {
  targetObject.value = id;
  name.value = "";
  mqttTopic.value = "";
  error.value = "";
  showSensorModal.value = true;
}

async function saveSensor() {
  try {
    await sensorsStore.createSensor(targetObject.value, {
      name: name.value,
      mqtt_topic: mqttTopic.value,
    });
    showSensorModal.value = false;
    await loadSensors(targetObject.value);
  } catch (e) {
    error.value =
      e instanceof Error ? e.message : "Nie udało się dodać sensora";
  }
}

async function removeSensors() {
  if (selectedSensors.value.size === 0) return;
  if (!confirm(`Usunąć ${selectedSensors.value.size} zaznaczonych sensorów?`)) return;
  // Group by object
  const byObject = new Map<string, string[]>();
  for (const sId of selectedSensors.value) {
    // Find which object this sensor belongs to
    for (const [objId, sens] of Object.entries(objectSensors.value)) {
      if (sens.some(s => s.id === sId)) {
        if (!byObject.has(objId)) byObject.set(objId, []);
        byObject.get(objId)!.push(sId);
        break;
      }
    }
  }
  for (const [objId, sIds] of byObject) {
    for (const sId of sIds) {
      await sensorsStore.deleteSensor(objId, sId);
    }
    await loadSensors(objId);
  }
  selectedSensors.value = new Set();
}

// ─── Alarm config modal ───────────────────────────────────────────
const alarmConfigTarget = ref<{ id: string; name: string } | null>(null);

function openAlarmConfig(sensor: SensorItem) {
  alarmConfigTarget.value = { id: sensor.id, name: sensor.name };
}

// ─── Helpers ──────────────────────────────────────────────────────
function temp(v: number | null) {
  return v == null ? "—" : `${v.toFixed(1)} °C`;
}

function date(v: string | null) {
  return v ? new Date(v).toLocaleString("pl-PL") : "—";
}

// ─── Init ─────────────────────────────────────────────────────────
onMounted(async () => {
  await objectsStore.fetchObjects();
  if (objectsStore.objects[0]) {
    expanded.value = objectsStore.objects[0].id;
    await loadSensors(expanded.value);
  }
});
</script>

<template>
  <section class="objects-page">
    <header class="page-head">
      <div>
        <h1>Obiekty</h1>
        <p>Zarządzaj swoimi obiektami i sensorami.</p>
      </div>
      <div class="actions">
        <button class="primary" @click="openObject()">＋　Dodaj obiekt</button>
        <button
          @click="selectedObjects.size === 1 && openObject(objectsStore.objects.find(x => x.id === [...selectedObjects][0]))"
          :disabled="selectedObjects.size !== 1"
        >
          ⌑　 Edytuj obiekt
        </button>
        <button class="danger" @click="removeObjects" :disabled="selectedObjects.size === 0">
          ♜　 Usuń obiekt
        </button>
        <button
          class="danger"
          @click="removeSensors"
          :disabled="selectedSensors.size === 0"
        >
          ♜　 Usuń sensor
        </button>
      </div>
    </header>

    <div class="object-list">
      <article
        v-for="object in objectsStore.objects"
        :key="object.id"
        class="object-panel"
        :class="{ open: expanded === object.id }"
      >
        <header class="object-row">
          <FrigoCheckbox
            :modelValue="objectCheckState(object.id)"
            @update:modelValue="toggleObject(object.id)"
          />
          <button class="object-toggle" @click="toggle(object)">
            <svg viewBox="0 0 24 24">
              <path d="M4 21V4h16v17M8 8h2m4 0h2M8 12h2m4 0h2M8 16h2m4 0h2" />
            </svg>
            <span>
              <b>{{ object.name }}</b>
              <small v-if="expanded === object.id">{{
                (objectSensors[object.id] || []).length
              }}
                sensory</small>
            </span>
          </button>
          <em>{{ object.is_active ? "Online" : "Offline" }}</em>
          <div v-if="expanded === object.id" class="sensor-actions">
            <button @click="openSensor(object.id)">＋　Dodaj sensor</button>
          </div>
          <button class="chevron" @click="toggle(object)">
            {{ expanded === object.id ? "⌃" : "›" }}
          </button>
        </header>

        <div v-if="expanded === object.id" class="sensor-table">
          <div class="sensor-head">
            <span></span>
            <span>NAZWA SENSORA</span>
            <span>MQTT TOPIC</span>
            <span>AKTUALNA WARTOŚĆ</span>
            <span>OSTATNIA AKTUALIZACJA</span>
            <span></span>
          </div>
          <div
            v-for="sensor in objectSensors[object.id] || []"
            :key="sensor.id"
            class="sensor-row"
          >
            <FrigoCheckbox
              :modelValue="selectedSensors.has(sensor.id)"
              @update:modelValue="toggleSensor(sensor.id, object.id)"
            />
            <span>
              <svg viewBox="0 0 24 24">
                <path d="M14 14.5V5a2 2 0 0 0-4 0v9.5a5 5 0 1 0 4 0Z" />
                <path d="M12 11v6" />
              </svg>
              {{ sensor.name }}
            </span>
            <code>{{ sensor.mqtt_topic }}</code>
            <strong>{{ temp(sensor.current_temperature) }}</strong>
            <time>{{ date(sensor.last_message_at) }}</time>
            <div class="sensor-row-actions">
              <button
                class="alarm-btn"
                title="Konfiguracja alarmów"
                @click="openAlarmConfig(sensor)"
              >
                ⚙ Alarmy
              </button>
            </div>
          </div>
          <div
            v-if="!(objectSensors[object.id] || []).length"
            class="no-sensors"
          >
            Brak sensorów
          </div>
        </div>
      </article>
    </div>

    <p class="count">
      Wyświetlanie 1–{{ objectsStore.objects.length }} z
      {{ objectsStore.objects.length }} obiektów
    </p>

    <!-- Object / Sensor modal -->
    <div
      v-if="showObjectModal || showSensorModal"
      class="modal"
      @click.self="showObjectModal = false; showSensorModal = false"
    >
      <form @submit.prevent="showObjectModal ? saveObject() : saveSensor()">
        <h2>{{
          showObjectModal
            ? (editing ? "Edytuj obiekt" : "Dodaj obiekt")
            : "Dodaj sensor"
        }}</h2>
        <label>
          Nazwa
          <input v-model="name" required />
        </label>
        <label v-if="showObjectModal">
          Opis
          <textarea v-model="description"></textarea>
        </label>
        <label v-if="showSensorModal">
          MQTT Topic
          <input v-model="mqttTopic" required />
        </label>
        <p v-if="error" class="error">{{ error }}</p>
        <footer>
          <button
            type="button"
            @click="showObjectModal = false; showSensorModal = false"
          >
            Anuluj
          </button>
          <button class="primary">Zapisz</button>
        </footer>
      </form>
    </div>

    <!-- Alarm Config Modal -->
    <AlarmConfigModal
      v-if="alarmConfigTarget"
      :sensorId="alarmConfigTarget.id"
      :sensorName="alarmConfigTarget.name"
      @close="alarmConfigTarget = null"
      @saved="alarmConfigTarget = null"
    />
  </section>
</template>

<style scoped>
.objects-page {
  padding: 20px 31px;
  max-width: 1680px;
  margin: auto;
}

.page-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.page-head h1 {
  font-size: 31px;
  margin: 0 0 4px;
}

.page-head p {
  margin: 0;
  color: #afbfda;
  font-size: 17px;
}

.actions {
  display: flex;
  gap: 30px;
}

.actions button,
.sensor-actions button {
  height: 57px;
  min-width: 224px;
  background: #061424;
  border: 1px solid #2a4d6d;
  border-radius: 7px;
  color: #f1f5ff;
  font-size: 17px;
  cursor: pointer;
}

.actions button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.actions .primary,
.primary {
  background: linear-gradient(115deg, #06c7f3, #078de4);
  border-color: #139de5;
}

.actions .danger {
  background: linear-gradient(110deg, #ec173d, #be0922);
  border-color: #ee2944;
}

.object-list {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.object-panel {
  background: linear-gradient(105deg, #0b1e2d, #0a1928);
  border: 1px solid #162e43;
  border-radius: 7px;
}

.object-row {
  height: 68px;
  display: flex;
  align-items: center;
  padding: 0 22px;
  gap: 20px;
}

.object-toggle {
  border: 0;
  background: transparent;
  color: #ecf3ff;
  display: flex;
  align-items: center;
  gap: 24px;
  text-align: left;
  min-width: 215px;
  cursor: pointer;
}

.object-toggle svg {
  width: 42px;
  height: 42px;
  color: #00dde1;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.4;
}

.object-toggle b {
  display: block;
  font-size: 19px;
}

.object-toggle small {
  display: block;
  color: #b3c3dd;
  font-size: 16px;
  margin-top: 4px;
}

.object-row em {
  font-style: normal;
  color: #00dff1;
  background: #063049;
  border: 1px solid #084363;
  border-radius: 7px;
  padding: 7px 11px;
}

.sensor-actions {
  display: flex;
  gap: 11px;
}

.sensor-actions button {
  height: 42px;
  min-width: 156px;
  color: #00d9ed;
  font-size: 15px;
  background: #062235;
  border-color: #00aee2;
}

.sensor-actions button:disabled {
  opacity: 0.35;
}

.chevron {
  margin-left: auto;
  background: transparent;
  border: 0;
  color: #a8c6f2;
  font-size: 35px;
  cursor: pointer;
}

.sensor-table {
  margin: 17px 14px 8px;
  border: 1px solid #173044;
  border-radius: 7px;
  overflow: hidden;
}

.sensor-head,
.sensor-row {
  display: grid;
  grid-template-columns: 40px 20% 20% 18% 20% 1fr;
  align-items: center;
}

.sensor-head {
  height: 73px;
  color: #b3c7e6;
  font-size: 14px;
  padding: 0 12px;
  border-bottom: 1px solid #163044;
}

.sensor-row {
  min-height: 45px;
  border-bottom: 1px solid #163044;
  padding: 0 12px;
  font-size: 18px;
}

.sensor-row span {
  display: flex;
  align-items: center;
  gap: 10px;
}

.sensor-row svg {
  width: 19px;
  color: #00cef5;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
}

.sensor-row code {
  color: #8abbd7;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sensor-row strong {
  color: #00baf2;
  font-weight: 500;
}

.sensor-row time {
  color: #a9c0de;
}

.sensor-row-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}

.alarm-btn {
  background: transparent;
  border: 1px solid #06d8e4;
  color: #06d8e4;
  border-radius: 5px;
  padding: 4px 10px;
  font-size: 13px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}

.alarm-btn:hover {
  background: rgba(6, 216, 228, 0.12);
}

.no-sensors {
  padding: 18px;
  text-align: center;
  color: #9fb0c8;
}

.count {
  color: #b3c3dd;
  margin: 20px 14px;
}

.modal {
  position: fixed;
  inset: 0;
  background: #000a;
  display: grid;
  place-items: center;
  z-index: 5;
}

.modal form {
  width: min(430px, calc(100vw - 32px));
  padding: 25px;
  background: #0a1827;
  border: 1px solid #26516b;
  border-radius: 9px;
}

.modal h2 {
  margin: 0 0 20px;
}

.modal label {
  display: grid;
  gap: 6px;
  color: #b3c7e6;
  margin: 12px 0;
}

.modal input,
.modal textarea {
  background: #07121f;
  border: 1px solid #294b68;
  border-radius: 5px;
  color: white;
  padding: 9px;
  font: inherit;
}

.modal textarea {
  min-height: 70px;
}

.modal .error {
  color: #ff3151;
}

.modal footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

.modal footer button {
  padding: 9px 17px;
  color: white;
  border: 1px solid #294b68;
  border-radius: 5px;
  background: #102133;
  cursor: pointer;
}

.modal footer .primary {
  border: 0;
}

@media (max-width: 850px) {
  .objects-page {
    padding: 18px 14px;
  }
  .page-head {
    align-items: flex-start;
    gap: 16px;
    flex-direction: column;
  }
  .actions {
    gap: 8px;
    width: 100%;
    overflow: auto;
  }
  .actions button {
    min-width: 155px;
    height: 44px;
    font-size: 14px;
  }
  .object-row {
    padding: 0 10px;
    gap: 10px;
  }
  .object-toggle {
    min-width: 0;
    gap: 10px;
  }
  .object-toggle svg {
    width: 30px;
  }
  .object-toggle b {
    font-size: 16px;
  }
  .sensor-actions {
    display: none;
  }
  .sensor-head,
  .sensor-row {
    grid-template-columns: 30px 22% 18% 14% 20% 1fr;
    padding: 0 6px;
    font-size: 12px;
  }
  .sensor-head {
    padding: 0 6px;
  }
  .sensor-row span {
    gap: 5px;
  }
  .sensor-row code {
    font-size: 11px;
  }
  .sensor-row time {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .object-row em {
    font-size: 12px;
  }
  .sensor-table {
    margin: 10px 4px;
  }
  .alarm-btn {
    font-size: 11px;
    padding: 2px 6px;
  }
}
</style>
