<script setup lang="ts">
/**
 * Administrator Objects panel.
 *
 * Desktop-first: a compact object list that expands into a dense sensor
 * table. Every per-row action lives behind a settings icon (Object →
 * Sensor → Settings) instead of the old selection-checkbox workflow.
 */
import { formatSensorValue } from "@/utils/units";
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useObjectsStore } from "@/stores/objects";
import { useSensorsStore } from "@/stores/sensors";
import { apiAggregates, apiMeters, apiReceivers, apiSensors } from "@/api";
import type { AggregateInput, AggregateItem, MeterInput, MeterItem, ObjectItem, ReceiverInput, ReceiverItem, ReceiverState, SensorItem } from "@/types";
import SensorIcon from "@/components/SensorIcon.vue";
import SensorSettingsModal from "@/components/SensorSettingsModal.vue";
import ObjectSettingsModal from "@/components/ObjectSettingsModal.vue";
import { suggestIconFromName } from "@/utils/sensorIcons";
import { onWsEvent } from "@/composables/useWebSocket";
import { useLiveRefresh } from "@/composables/useLiveRefresh";

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
  await Promise.all([loadReceivers(objectId), loadAggregates(objectId), loadMeters(objectId)]);
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

// ─── Receivers (odbiorniki) ───────────────────────────────────────
// A receiver ties a chamber sensor (and optionally its evaporator) to the
// controller's working temperatures; the clients show its inferred state.
const objectReceivers = ref<Record<string, ReceiverItem[]>>({});
const receiversOf = (id: string) => objectReceivers.value[id] ?? [];

const STATE_LABELS: Record<ReceiverState, string> = {
  cooling: "Chłodzenie",
  idle: "Postój",
  defrost: "Odszranianie",
  unknown: "Nieznany",
};

async function loadReceivers(objectId: string) {
  try {
    objectReceivers.value = { ...objectReceivers.value, [objectId]: await apiReceivers.list(objectId) };
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Nie udało się wczytać odbiorników";
  }
}

const temperatureSensorsOf = (objectId: string) =>
  sensorsOf(objectId).filter((s) => !s.kind || s.kind === "temperature");

function sensorName(objectId: string, sensorId: string | null) {
  if (!sensorId) return "—";
  return sensorsOf(objectId).find((s) => s.id === sensorId)?.name ?? "—";
}

type ReceiverDraft = Omit<ReceiverInput, "cut_in" | "cut_out"> & {
  cut_in: string;
  cut_out: string;
};
const receiverEdit = ref<{ objectId: string; id: string | null; draft: ReceiverDraft } | null>(null);
const receiverError = ref("");
const receiverSaving = ref(false);

function openReceiver(objectId: string, receiver: ReceiverItem | null) {
  const asText = (v: number | null | undefined) => (v == null ? "" : String(v));
  receiverError.value = "";
  receiverEdit.value = {
    objectId,
    id: receiver?.id ?? null,
    draft: {
      name: receiver?.name ?? "",
      chamber_sensor_id: receiver?.chamber_sensor_id ?? null,
      evaporator_sensor_id: receiver?.evaporator_sensor_id ?? null,
      cut_in: asText(receiver?.cut_in),
      cut_out: asText(receiver?.cut_out),
      is_active: receiver?.is_active ?? true,
    },
  };
}

function parseDegrees(text: string): number | null {
  const trimmed = text.trim().replace(",", ".");
  return trimmed === "" ? null : Number(trimmed);
}

async function saveReceiver() {
  const edit = receiverEdit.value;
  if (!edit) return;
  const d = edit.draft;
  const data: ReceiverInput = {
    name: d.name.trim(),
    chamber_sensor_id: d.chamber_sensor_id || null,
    evaporator_sensor_id: d.evaporator_sensor_id || null,
    cut_in: parseDegrees(d.cut_in),
    cut_out: parseDegrees(d.cut_out),
    is_active: d.is_active,
  };
  if ([data.cut_in, data.cut_out].some((v) => v != null && Number.isNaN(v))) {
    receiverError.value = "Temperatury wpisz jako liczby, np. -18 albo 2,5";
    return;
  }
  if (data.cut_in != null && data.cut_out != null && data.cut_out >= data.cut_in) {
    receiverError.value = "Wyłączenie chłodzenia musi być niżej niż jego załączenie";
    return;
  }
  receiverSaving.value = true;
  try {
    if (edit.id) await apiReceivers.update(edit.objectId, edit.id, data);
    else await apiReceivers.create(edit.objectId, data);
    receiverEdit.value = null;
    await loadReceivers(edit.objectId);
  } catch (e) {
    receiverError.value = e instanceof Error ? e.message : "Nie udało się zapisać odbiornika";
  } finally {
    receiverSaving.value = false;
  }
}

async function deleteReceiver() {
  const edit = receiverEdit.value;
  if (!edit?.id || !window.confirm(`Usunąć odbiornik „${edit.draft.name}”? Czujniki zostaną.`)) return;
  try {
    await apiReceivers.delete(edit.objectId, edit.id);
    receiverEdit.value = null;
    await loadReceivers(edit.objectId);
  } catch (e) {
    receiverError.value = e instanceof Error ? e.message : "Nie udało się usunąć odbiornika";
  }
}

// ─── Aggregates (agregaty) ────────────────────────────────────────
// Nameplate data of a condensing unit plus the sensors the clients show
// with it (outdoor temperature, discharge line…), in the order set here.
const objectAggregates = ref<Record<string, AggregateItem[]>>({});
const aggregatesOf = (id: string) => objectAggregates.value[id] ?? [];

const REFRIGERANTS = ["R404A", "R448A", "R449A", "R452A", "R134a", "R407C", "R410A", "R32", "R290", "R744", "R507A", "R22"];

async function loadAggregates(objectId: string) {
  try {
    objectAggregates.value = { ...objectAggregates.value, [objectId]: await apiAggregates.list(objectId) };
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Nie udało się wczytać agregatów";
  }
}

// Form fields stay text until saved, like the receiver form.
type AggregateDraft = Pick<AggregateInput, "name" | "sensor_ids" | "is_active"> & {
  compressor_model: string;
  cooling_capacity_kw: string;
  refrigerant: string;
  refrigerant_charge_kg: string;
  installed_on: string;
};
const aggregateEdit = ref<{ objectId: string; id: string | null; draft: AggregateDraft } | null>(null);
const aggregateError = ref("");
const aggregateSaving = ref(false);
const aggregateSensorToAdd = ref<string | null>(null);

function openAggregate(objectId: string, aggregate: AggregateItem | null) {
  aggregateError.value = "";
  aggregateSensorToAdd.value = null;
  aggregateEdit.value = {
    objectId,
    id: aggregate?.id ?? null,
    draft: {
      name: aggregate?.name ?? "",
      compressor_model: aggregate?.compressor_model ?? "",
      cooling_capacity_kw: aggregate?.cooling_capacity_kw == null ? "" : String(aggregate.cooling_capacity_kw),
      refrigerant: aggregate?.refrigerant ?? "",
      refrigerant_charge_kg: aggregate?.refrigerant_charge_kg == null ? "" : String(aggregate.refrigerant_charge_kg),
      installed_on: aggregate?.installed_on ?? "",
      sensor_ids: [...(aggregate?.sensor_ids ?? [])],
      is_active: aggregate?.is_active ?? true,
    },
  };
}

const aggregateSensorChoices = computed(() => {
  const edit = aggregateEdit.value;
  if (!edit) return [];
  return sensorsOf(edit.objectId).filter((s) => !edit.draft.sensor_ids.includes(s.id));
});

function addAggregateSensor() {
  const id = aggregateSensorToAdd.value;
  if (id && aggregateEdit.value) aggregateEdit.value.draft.sensor_ids.push(id);
  aggregateSensorToAdd.value = null;
}

function moveAggregateSensor(index: number, step: -1 | 1) {
  const ids = aggregateEdit.value?.draft.sensor_ids;
  if (!ids || index + step < 0 || index + step >= ids.length) return;
  [ids[index], ids[index + step]] = [ids[index + step], ids[index]];
}

function removeAggregateSensor(index: number) {
  aggregateEdit.value?.draft.sensor_ids.splice(index, 1);
}

async function saveAggregate() {
  const edit = aggregateEdit.value;
  if (!edit) return;
  const d = edit.draft;
  const charge = parseDegrees(d.refrigerant_charge_kg);
  if (charge != null && (Number.isNaN(charge) || charge < 0)) {
    aggregateError.value = "Ilość czynnika wpisz jako liczbę kilogramów, np. 6,5";
    return;
  }
  const capacity = parseDegrees(d.cooling_capacity_kw);
  if (capacity != null && (Number.isNaN(capacity) || capacity < 0)) {
    aggregateError.value = "Moc chłodniczą wpisz jako liczbę kilowatów, np. 5,8";
    return;
  }
  const data: AggregateInput = {
    name: d.name.trim(),
    compressor_model: d.compressor_model.trim() || null,
    cooling_capacity_kw: capacity,
    refrigerant: d.refrigerant.trim() || null,
    refrigerant_charge_kg: charge,
    installed_on: d.installed_on || null,
    sensor_ids: d.sensor_ids,
    is_active: d.is_active,
  };
  aggregateSaving.value = true;
  try {
    if (edit.id) await apiAggregates.update(edit.objectId, edit.id, data);
    else await apiAggregates.create(edit.objectId, data);
    aggregateEdit.value = null;
    await loadAggregates(edit.objectId);
  } catch (e) {
    aggregateError.value = e instanceof Error ? e.message : "Nie udało się zapisać agregatu";
  } finally {
    aggregateSaving.value = false;
  }
}

async function deleteAggregate() {
  const edit = aggregateEdit.value;
  if (!edit?.id || !window.confirm(`Usunąć agregat „${edit.draft.name}”? Czujniki zostaną.`)) return;
  try {
    await apiAggregates.delete(edit.objectId, edit.id);
    aggregateEdit.value = null;
    await loadAggregates(edit.objectId);
  } catch (e) {
    aggregateError.value = e instanceof Error ? e.message : "Nie udało się usunąć agregatu";
  }
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}.${m}.${y}`;
}

// ─── Meters (liczniki) ────────────────────────────────────────────
// A meter's kWh counter (plus its power, current and voltage); the clients
// show the consumption the backend works out per day, week and month.
const objectMeters = ref<Record<string, MeterItem[]>>({});
const metersOf = (id: string) => objectMeters.value[id] ?? [];

async function loadMeters(objectId: string) {
  try {
    objectMeters.value = { ...objectMeters.value, [objectId]: await apiMeters.list(objectId) };
  } catch (e) {
    error.value = e instanceof Error ? e.message : "Nie udało się wczytać liczników";
  }
}

const sensorsOfKind = (objectId: string, kind: string) => sensorsOf(objectId).filter((s) => s.kind === kind);

const METER_SLOTS = [
  { key: "energy_sensor_id", label: "Licznik energii (kWh)", kind: "energy" },
  { key: "power_sensor_id", label: "Moc (W)", kind: "power" },
  { key: "current_sensor_id", label: "Prąd (A)", kind: "current" },
  { key: "voltage_sensor_id", label: "Napięcie (V)", kind: "voltage" },
] as const;

const meterEdit = ref<{ objectId: string; id: string | null; draft: MeterInput } | null>(null);
const meterError = ref("");
const meterSaving = ref(false);

function openMeter(objectId: string, meter: MeterItem | null) {
  meterError.value = "";
  meterEdit.value = {
    objectId,
    id: meter?.id ?? null,
    draft: {
      name: meter?.name ?? "",
      energy_sensor_id: meter?.energy_sensor_id ?? null,
      power_sensor_id: meter?.power_sensor_id ?? null,
      current_sensor_id: meter?.current_sensor_id ?? null,
      voltage_sensor_id: meter?.voltage_sensor_id ?? null,
      is_active: meter?.is_active ?? true,
    },
  };
}

async function saveMeter() {
  const edit = meterEdit.value;
  if (!edit) return;
  meterSaving.value = true;
  try {
    const data = { ...edit.draft, name: edit.draft.name.trim() };
    if (edit.id) await apiMeters.update(edit.objectId, edit.id, data);
    else await apiMeters.create(edit.objectId, data);
    meterEdit.value = null;
    await loadMeters(edit.objectId);
  } catch (e) {
    meterError.value = e instanceof Error ? e.message : "Nie udało się zapisać licznika";
  } finally {
    meterSaving.value = false;
  }
}

async function deleteMeter() {
  const edit = meterEdit.value;
  if (!edit?.id || !window.confirm(`Usunąć licznik „${edit.draft.name}”? Czujniki zostaną.`)) return;
  try {
    await apiMeters.delete(edit.objectId, edit.id);
    meterEdit.value = null;
    await loadMeters(edit.objectId);
  } catch (e) {
    meterError.value = e instanceof Error ? e.message : "Nie udało się usunąć licznika";
  }
}

function kwh(value: number | null) {
  return value == null ? "—" : `${value.toLocaleString("pl-PL", { maximumFractionDigits: 1 })} kWh`;
}

const totalSensors = computed(() =>
  objectsStore.objects.reduce((sum, o) => sum + (o.sensor_count || 0), 0),
);

// The sensor tables are per-object copies, so live updates must be patched
// into them here — the store only tracks the dashboard's object.
const stopSensorUpdates = onWsEvent("sensor.updated", (data) => {
  const update = data as Partial<SensorItem> & { id: string };
  for (const [objectId, list] of Object.entries(objectSensors.value)) {
    const idx = list.findIndex((s) => s.id === update.id);
    if (idx !== -1) {
      const next = [...list];
      next[idx] = { ...next[idx], ...update };
      objectSensors.value = { ...objectSensors.value, [objectId]: next };
      return;
    }
  }
});
onUnmounted(stopSensorUpdates);

// Fallback for a dropped websocket (mobile browsers freeze background tabs).
useLiveRefresh(async () => {
  for (const objectId of expanded.value) {
    try {
      const fresh = await apiSensors.list(objectId);
      objectSensors.value = { ...objectSensors.value, [objectId]: fresh };
    } catch {
      // keep the last values; the next tick retries
    }
  }
}, 15_000);

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
                  <strong>{{ sensorOnline(sensor) ? formatSensorValue(sensor.current_temperature, sensor) : "—" }}</strong>
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

          <h3 class="sub-head">Odbiorniki</h3>
          <table class="sensor-table">
            <thead>
              <tr>
                <th class="col-name">Odbiornik</th>
                <th>Czujnik komory</th>
                <th>Czujnik parownika</th>
                <th>Załącz. / wyłącz.</th>
                <th>Stan</th>
                <th class="col-settings"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="receiver in receiversOf(object.id)" :key="receiver.id" :class="{ inactive: !receiver.is_active }">
                <td class="col-name"><span>{{ receiver.name }}</span></td>
                <td>{{ sensorName(object.id, receiver.chamber_sensor_id) }}</td>
                <td>{{ sensorName(object.id, receiver.evaporator_sensor_id) }}</td>
                <td>{{ temperature(receiver.cut_in) }} / {{ temperature(receiver.cut_out) }}</td>
                <td><span :class="['state', receiver.state]">{{ STATE_LABELS[receiver.state] }}</span></td>
                <td class="col-settings">
                  <button class="icon-btn" title="Ustawienia odbiornika" aria-label="Ustawienia odbiornika" @click="openReceiver(object.id, receiver)">
                    <svg viewBox="0 0 24 24">
                      <circle cx="12" cy="12" r="3" />
                      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.1 2.1-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56v.1h-3v-.1a1.7 1.7 0 0 0-1.03-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06-2.1-2.1.06-.06A1.7 1.7 0 0 0 7.06 15a1.7 1.7 0 0 0-1.56-1.03h-.1v-3h.1A1.7 1.7 0 0 0 7.06 9.94a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.1-2.1.06.06a1.7 1.7 0 0 0 1.88.34 1.7 1.7 0 0 0 1.03-1.56v-.1h3v.1a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.1 2.1-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.03h.1v3h-.1A1.7 1.7 0 0 0 19.4 15Z" />
                    </svg>
                  </button>
                </td>
              </tr>
              <tr v-if="!receiversOf(object.id).length">
                <td colspan="7" class="no-sensors">Brak odbiorników — dodaj komorę i przypisz jej czujniki</td>
              </tr>
            </tbody>
          </table>
          <div class="panel-foot">
            <button class="secondary" @click="openReceiver(object.id, null)">＋ Dodaj odbiornik</button>
            <span class="muted">Nastawy służą do prezentacji i wykrywania stanu pracy — alarmy zostają przy czujnikach.</span>
          </div>

          <h3 class="sub-head">Agregaty</h3>
          <table class="sensor-table">
            <thead>
              <tr>
                <th class="col-name">Agregat</th>
                <th>Sprężarka</th>
                <th>Moc chł.</th>
                <th>Czynnik</th>
                <th>Instalacja</th>
                <th>Czujniki</th>
                <th class="col-settings"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="aggregate in aggregatesOf(object.id)" :key="aggregate.id" :class="{ inactive: !aggregate.is_active }">
                <td class="col-name"><span>{{ aggregate.name }}</span></td>
                <td>{{ aggregate.compressor_model || "—" }}</td>
                <td>{{ aggregate.cooling_capacity_kw != null ? `${aggregate.cooling_capacity_kw.toLocaleString("pl-PL")} kW` : "—" }}</td>
                <td>
                  {{ aggregate.refrigerant || "—" }}<template v-if="aggregate.refrigerant_charge_kg != null">, {{ aggregate.refrigerant_charge_kg.toLocaleString("pl-PL") }} kg</template>
                </td>
                <td>{{ formatDate(aggregate.installed_on) }}</td>
                <td>{{ aggregate.sensor_ids.map((id) => sensorName(object.id, id)).join(", ") || "—" }}</td>
                <td class="col-settings">
                  <button class="icon-btn" title="Ustawienia agregatu" aria-label="Ustawienia agregatu" @click="openAggregate(object.id, aggregate)">
                    <svg viewBox="0 0 24 24">
                      <circle cx="12" cy="12" r="3" />
                      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.1 2.1-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56v.1h-3v-.1a1.7 1.7 0 0 0-1.03-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06-2.1-2.1.06-.06A1.7 1.7 0 0 0 7.06 15a1.7 1.7 0 0 0-1.56-1.03h-.1v-3h.1A1.7 1.7 0 0 0 7.06 9.94a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.1-2.1.06.06a1.7 1.7 0 0 0 1.88.34 1.7 1.7 0 0 0 1.03-1.56v-.1h3v.1a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.1 2.1-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.03h.1v3h-.1A1.7 1.7 0 0 0 19.4 15Z" />
                    </svg>
                  </button>
                </td>
              </tr>
              <tr v-if="!aggregatesOf(object.id).length">
                <td colspan="7" class="no-sensors">Brak agregatów — dodaj agregat i wybierz jego czujniki</td>
              </tr>
            </tbody>
          </table>
          <div class="panel-foot">
            <button class="secondary" @click="openAggregate(object.id, null)">＋ Dodaj agregat</button>
            <span class="muted">Jeden czujnik (np. temperatura zewnętrzna) może należeć do kilku agregatów.</span>
          </div>

          <h3 class="sub-head">Liczniki</h3>
          <table class="sensor-table">
            <thead>
              <tr>
                <th class="col-name">Licznik</th>
                <th>Energia</th>
                <th>Moc / prąd / napięcie</th>
                <th>Dziś</th>
                <th>Ten miesiąc</th>
                <th>Stan licznika</th>
                <th class="col-settings"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="meter in metersOf(object.id)" :key="meter.id" :class="{ inactive: !meter.is_active }">
                <td class="col-name"><span>{{ meter.name }}</span></td>
                <td>{{ sensorName(object.id, meter.energy_sensor_id) }}</td>
                <td>
                  {{ [meter.power_sensor_id, meter.current_sensor_id, meter.voltage_sensor_id].filter(Boolean).map((id) => sensorName(object.id, id)).join(", ") || "—" }}
                </td>
                <td>{{ kwh(meter.consumption.today_kwh) }}</td>
                <td>{{ kwh(meter.consumption.month_kwh) }}</td>
                <td>{{ kwh(meter.total_kwh) }}</td>
                <td class="col-settings">
                  <button class="icon-btn" title="Ustawienia licznika" aria-label="Ustawienia licznika" @click="openMeter(object.id, meter)">
                    <svg viewBox="0 0 24 24">
                      <circle cx="12" cy="12" r="3" />
                      <path d="M19.4 15a1.7 1.7 0 0 0 .34 1.88l.06.06-2.1 2.1-.06-.06a1.7 1.7 0 0 0-1.88-.34 1.7 1.7 0 0 0-1.03 1.56v.1h-3v-.1a1.7 1.7 0 0 0-1.03-1.56 1.7 1.7 0 0 0-1.88.34l-.06.06-2.1-2.1.06-.06A1.7 1.7 0 0 0 7.06 15a1.7 1.7 0 0 0-1.56-1.03h-.1v-3h.1A1.7 1.7 0 0 0 7.06 9.94a1.7 1.7 0 0 0-.34-1.88l-.06-.06 2.1-2.1.06.06a1.7 1.7 0 0 0 1.88.34 1.7 1.7 0 0 0 1.03-1.56v-.1h3v.1a1.7 1.7 0 0 0 1.03 1.56 1.7 1.7 0 0 0 1.88-.34l.06-.06 2.1 2.1-.06.06a1.7 1.7 0 0 0-.34 1.88 1.7 1.7 0 0 0 1.56 1.03h.1v3h-.1A1.7 1.7 0 0 0 19.4 15Z" />
                    </svg>
                  </button>
                </td>
              </tr>
              <tr v-if="!metersOf(object.id).length">
                <td colspan="7" class="no-sensors">Brak liczników — dodaj licznik i wskaż jego czujnik energii</td>
              </tr>
            </tbody>
          </table>
          <div class="panel-foot">
            <button class="secondary" @click="openMeter(object.id, null)">＋ Dodaj licznik</button>
            <span class="muted">Przy kilku licznikach klienci widzą też ich sumę.</span>
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

    <!-- Receiver settings -->
    <div v-if="receiverEdit" class="modal" @click.self="receiverEdit = null">
      <form class="receiver-form" @submit.prevent="saveReceiver">
        <h2>{{ receiverEdit.id ? "Ustawienia odbiornika" : "Dodaj odbiornik" }}</h2>
        <label>
          Nazwa
          <input v-model="receiverEdit.draft.name" placeholder="Mroźnia" required />
        </label>
        <div class="pair">
          <label>
            Czujnik komory
            <select v-model="receiverEdit.draft.chamber_sensor_id">
              <option :value="null">— brak —</option>
              <option v-for="s in temperatureSensorsOf(receiverEdit.objectId)" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </label>
          <label>
            Czujnik parownika
            <select v-model="receiverEdit.draft.evaporator_sensor_id">
              <option :value="null">— brak —</option>
              <option v-for="s in temperatureSensorsOf(receiverEdit.objectId)" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
          </label>
        </div>
        <div class="pair">
          <label>
            Załączenie °C
            <input v-model="receiverEdit.draft.cut_in" inputmode="decimal" placeholder="-18" />
          </label>
          <label>
            Wyłączenie °C
            <input v-model="receiverEdit.draft.cut_out" inputmode="decimal" placeholder="-20" />
          </label>
        </div>
        <p class="hint">Bez czujnika parownika odszranianie nie będzie rozpoznawane — tylko chłodzenie i postój.</p>
        <label class="check">
          <input v-model="receiverEdit.draft.is_active" type="checkbox" />
          Pokazuj klientom
        </label>
        <p v-if="receiverError" class="error">{{ receiverError }}</p>
        <footer>
          <button v-if="receiverEdit.id" type="button" class="danger-link" @click="deleteReceiver">Usuń</button>
          <button type="button" @click="receiverEdit = null">Anuluj</button>
          <button class="primary" :disabled="receiverSaving">Zapisz</button>
        </footer>
      </form>
    </div>

    <!-- Meter settings -->
    <div v-if="meterEdit" class="modal" @click.self="meterEdit = null">
      <form class="receiver-form" @submit.prevent="saveMeter">
        <h2>{{ meterEdit.id ? "Ustawienia licznika" : "Dodaj licznik" }}</h2>
        <label>
          Nazwa
          <input v-model="meterEdit.draft.name" placeholder="Licznik główny" required />
        </label>
        <label v-for="slot in METER_SLOTS" :key="slot.key">
          {{ slot.label }}
          <select v-model="meterEdit.draft[slot.key]">
            <option :value="null">— brak —</option>
            <option v-for="s in sensorsOfKind(meterEdit.objectId, slot.kind)" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </label>
        <p class="hint">Zużycie liczone jest z czujnika energii: dziś, w tym tygodniu i w tym miesiącu.</p>
        <label class="check">
          <input v-model="meterEdit.draft.is_active" type="checkbox" />
          Pokazuj klientom
        </label>
        <p v-if="meterError" class="error">{{ meterError }}</p>
        <footer>
          <button v-if="meterEdit.id" type="button" class="danger-link" @click="deleteMeter">Usuń</button>
          <button type="button" @click="meterEdit = null">Anuluj</button>
          <button class="primary" :disabled="meterSaving">Zapisz</button>
        </footer>
      </form>
    </div>

    <!-- Aggregate settings -->
    <div v-if="aggregateEdit" class="modal" @click.self="aggregateEdit = null">
      <form class="receiver-form" @submit.prevent="saveAggregate">
        <h2>{{ aggregateEdit.id ? "Ustawienia agregatu" : "Dodaj agregat" }}</h2>
        <label>
          Nazwa
          <input v-model="aggregateEdit.draft.name" placeholder="Agregat mroźni" required />
        </label>
        <div class="pair">
          <label>
            Model sprężarki
            <input v-model="aggregateEdit.draft.compressor_model" placeholder="Bitzer 4FES-5Y" />
          </label>
          <label>
            Moc chłodnicza, kW
            <input v-model="aggregateEdit.draft.cooling_capacity_kw" inputmode="decimal" placeholder="5,8" />
          </label>
        </div>
        <div class="pair">
          <label>
            Czynnik
            <input v-model="aggregateEdit.draft.refrigerant" list="refrigerants" placeholder="R404A" />
            <datalist id="refrigerants">
              <option v-for="r in REFRIGERANTS" :key="r" :value="r" />
            </datalist>
          </label>
          <label>
            Ilość czynnika, kg
            <input v-model="aggregateEdit.draft.refrigerant_charge_kg" inputmode="decimal" placeholder="6,5" />
          </label>
        </div>
        <label>
          Data instalacji
          <input v-model="aggregateEdit.draft.installed_on" type="date" />
        </label>
        <div class="aggregate-sensors">
          <span>Czujniki (w kolejności wyświetlania)</span>
          <ol>
            <li v-for="(id, i) in aggregateEdit.draft.sensor_ids" :key="id">
              <span>{{ sensorName(aggregateEdit.objectId, id) }}</span>
              <button type="button" title="W górę" :disabled="i === 0" @click="moveAggregateSensor(i, -1)">↑</button>
              <button type="button" title="W dół" :disabled="i === aggregateEdit.draft.sensor_ids.length - 1" @click="moveAggregateSensor(i, 1)">↓</button>
              <button type="button" title="Usuń z agregatu" @click="removeAggregateSensor(i)">✕</button>
            </li>
          </ol>
          <select v-model="aggregateSensorToAdd" @change="addAggregateSensor">
            <option :value="null">＋ dodaj czujnik…</option>
            <option v-for="s in aggregateSensorChoices" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </div>
        <label class="check">
          <input v-model="aggregateEdit.draft.is_active" type="checkbox" />
          Pokazuj klientom
        </label>
        <p v-if="aggregateError" class="error">{{ aggregateError }}</p>
        <footer>
          <button v-if="aggregateEdit.id" type="button" class="danger-link" @click="deleteAggregate">Usuń</button>
          <button type="button" @click="aggregateEdit = null">Anuluj</button>
          <button class="primary" :disabled="aggregateSaving">Zapisz</button>
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

/* ---------- Receivers ---------- */
.sub-head {
  margin: 0;
  padding: 14px 14px 8px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.07em;
  text-transform: uppercase;
  color: #00d9ed;
  border-top: 1px solid #12293e;
}

.sensor-table tr.inactive td {
  opacity: 0.5;
}

.state {
  display: inline-block;
  padding: 2px 9px;
  border-radius: 10px;
  font-size: 12px;
  border: 1px solid #234662;
  color: #a9bdd8;
}

.state.cooling { color: #2ee6f0; border-color: #0e6f7a; }
.state.idle { color: #c3d2e6; }
.state.defrost { color: #ffb347; border-color: #8a5a1c; }
.state.unknown { color: #6f87a4; }

.modal form.receiver-form {
  width: min(560px, 100%);
}

.modal select {
  background: #050f1a;
  border: 1px solid #234662;
  border-radius: 6px;
  color: #f1f6ff;
  padding: 8px 10px;
  font: inherit;
  font-size: 14px;
}

.pair {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.modal .hint {
  margin: -4px 0 12px;
  font-size: 12px;
  color: #6f87a4;
}

.modal label.check {
  display: flex;
  align-items: center;
  gap: 8px;
}
.aggregate-sensors {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #9fb4cc;
  font-size: 13px;
}
.aggregate-sensors ol {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.aggregate-sensors li {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px 4px 10px;
  border: 1px solid #234662;
  border-radius: 6px;
  color: #f1f6ff;
  font-size: 14px;
}
.aggregate-sensors li span {
  flex: 1;
}
.aggregate-sensors li button {
  width: 28px;
  height: 28px;
  border: 1px solid #234662;
  border-radius: 4px;
  background: #0b1e2d;
  color: #e9f2ff;
  cursor: pointer;
}
.aggregate-sensors li button:disabled {
  opacity: 0.35;
  cursor: default;
}

.modal footer .danger-link {
  margin-right: auto;
  border-color: #5d2c35;
  color: #ff8497;
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
