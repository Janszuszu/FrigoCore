<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useAlarmsStore } from "@/stores/alarms";
import { useObjectsStore } from "@/stores/objects";
import { apiSensors } from "@/api";
import type { AlarmItem, SensorItem } from "@/types";
const alarmsStore=useAlarmsStore(),objectsStore=useObjectsStore(),tab=ref<"active"|"history">("active");
const activeAlarms=computed(()=>alarmsStore.alarms.filter(a=>["triggered","pending"].includes(a.status)));
const historyAlarms=computed(()=>alarmsStore.alarms.filter(a=>["acknowledged","resolved"].includes(a.status)));
const alarms=computed(()=>tab.value==="active"?activeAlarms.value:historyAlarms.value);
const activeCount=computed(()=>activeAlarms.value.length);
const acknowledgeCount=computed(()=>alarmsStore.alarms.filter(a=>a.status==="triggered").length);
function object(id:string){return objectsStore.objects.find(x=>x.id===id)?.name||id.slice(0,8)} function type(x:string){return ({offline:"DEVICE OFFLINE",high_temperature:"HIGH TEMPERATURE",low_temperature:"LOW TEMPERATURE"} as Record<string,string>)[x]||x.replaceAll("_"," ").toUpperCase()} function date(x:string|null){return x?new Date(x).toLocaleString("pl-PL"):"N/A"} function duration(x:string){const h=Math.max(0,Math.floor((Date.now()-new Date(x).getTime())/3600000));return `${h}h ${Math.floor((Date.now()-new Date(x).getTime())/60000)%60}m`}
async function resetAll(){for(const a of activeAlarms.value.filter(x=>x.status==="triggered"))await alarmsStore.acknowledgeAlarm(a.id)}
onMounted(()=>{alarmsStore.fetchAlarms();objectsStore.fetchObjects();});

// ── Mobile card redesign — additions below, desktop logic above is untouched ──

// Alarms only carry sensor_id; sensors are scoped per-object in this API, so
// resolving a friendly sensor name means fanning out across every object.
const sensorsById = ref<Record<string, SensorItem>>({});
async function loadAllSensors() {
  const lists = await Promise.all(
    objectsStore.objects.map((o) => apiSensors.list(o.id).catch(() => [] as SensorItem[]))
  );
  const map: Record<string, SensorItem> = {};
  for (const list of lists) for (const s of list) map[s.id] = s;
  sensorsById.value = map;
}

const now = ref(Date.now());
let clock: ReturnType<typeof setInterval> | null = null;
onMounted(async () => {
  await objectsStore.fetchObjects();
  await loadAllSensors();
  clock = setInterval(() => { now.value = Date.now(); }, 1000);
});
onUnmounted(() => {
  if (clock !== null) { clearInterval(clock); clock = null; }
});

const ALARM_COLORS: Record<string, { dot: string; label: string; cls: string }> = {
  high_temperature: { dot: "🔴", label: "HIGH TEMPERATURE", cls: "high" },
  low_temperature: { dot: "🔵", label: "LOW TEMPERATURE", cls: "low" },
  offline: { dot: "🟠", label: "DEVICE OFFLINE", cls: "offline" },
};
function alarmColor(alarmType: string) {
  return ALARM_COLORS[alarmType] ?? { dot: "⚪", label: type(alarmType), cls: "unknown" };
}

function objectName(id: string) {
  return objectsStore.objects.find((x) => x.id === id)?.name || "Unknown object";
}
function sensorName(id: string | null) {
  if (!id) return "Unknown sensor";
  return sensorsById.value[id]?.name || "Unknown sensor";
}

function startDate(x: string) {
  const ts = new Date(x);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(ts.getDate())}.${pad(ts.getMonth() + 1)}.${ts.getFullYear()} ${pad(ts.getHours())}:${pad(ts.getMinutes())}`;
}

function liveDuration(alarm: AlarmItem) {
  const start = new Date(alarm.triggered_at ?? alarm.detected_at).getTime();
  const endIso = alarm.resolved_at ?? alarm.acknowledged_at;
  const end = endIso ? new Date(endIso).getTime() : now.value;
  const totalSec = Math.max(0, Math.floor((end - start) / 1000));
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

// Per the redesign spec: history cards reuse the exact same layout as
// active cards — only the status badge text changes, not per literal
// alarm.status but per which tab is being viewed.
const mobileBadge = computed(() => (tab.value === "active" ? "ACTIVE" : "ACKNOWLEDGED"));

async function acknowledgeOne(alarm: AlarmItem) {
  await alarmsStore.acknowledgeAlarm(alarm.id);
}

// Reset-all — always confirm before touching every active alarm.
const showResetConfirm = ref(false);
async function confirmResetAll() {
  showResetConfirm.value = false;
  await resetAll();
}

// Details bottom-sheet.
const detailsAlarm = ref<AlarmItem | null>(null);
const detailsView = computed(() => {
  const a = detailsAlarm.value;
  if (!a) return null;
  const color = alarmColor(a.alarm_type);
  return {
    dot: color.dot,
    label: color.label,
    object: objectName(a.object_id),
    sensor: sensorName(a.sensor_id),
    status: a.status.toUpperCase(),
    detected: startDate(a.detected_at),
    triggered: a.triggered_at ? startDate(a.triggered_at) : null,
    acknowledged: a.acknowledged_at ? startDate(a.acknowledged_at) : null,
    resolved: a.resolved_at ? startDate(a.resolved_at) : null,
    triggerValue: a.trigger_value != null ? a.trigger_value.toFixed(1) : null,
    description: a.description,
  };
});
function openDetails(alarm: AlarmItem) { detailsAlarm.value = alarm; }
function closeDetails() { detailsAlarm.value = null; }
</script>
<template>
<section class="alarms-page"><header><h1>ALARMY</h1><p>Aktywne alarmy i historia.</p><div class="tabs"><button :class="{active:tab==='active'}" @click="tab='active'">AKTYWNE <i>{{activeCount}}</i></button><button :class="{active:tab==='history'}" @click="tab='history'">HISTORIA</button></div></header><div class="table-toolbar"><button v-if="tab==='active'" @click="resetAll">POTWIERDŹ WSZYSTKIE ({{activeCount}})</button></div><div v-if="alarmsStore.loading" class="empty">Ładowanie…</div><div v-else-if="!alarms.length" class="empty">Brak alarmów</div><div v-else class="alarm-table"><div class="tr th"><span>OBIEKT</span><span>SENSOR</span><span>TYP ALARMU</span><span>OD KIEDY</span><span>CZAS</span><span>STATUS</span><span>AKCJE</span></div><div v-for="alarm in alarms" :key="alarm.id" class="tr"><strong>{{object(alarm.object_id)}}</strong><b>{{alarm.sensor_id||'N/A'}}</b><span><i class="type">{{type(alarm.alarm_type)}}</i></span><time>{{date(alarm.triggered_at||alarm.detected_at)}}</time><time>{{duration(alarm.triggered_at||alarm.detected_at)}}</time><span><i :class="['status',alarm.status]">{{alarm.status==='triggered'?'AKTYWNY':alarm.status.toUpperCase()}}</i></span><span><button v-if="alarm.status==='triggered'" class="reset" @click="alarmsStore.acknowledgeAlarm(alarm.id)">POTWIERDŹ</button></span></div></div></section>

<section class="alarms-mobile">
  <div class="m-sticky">
    <header class="m-header">
      <div class="m-title">
        <h1>ALARMY</h1>
      </div>
      <button v-if="tab==='active' && acknowledgeCount" class="m-confirm-all" @click="showResetConfirm = true">POTWIERDŹ {{ acknowledgeCount }} ALARMY</button>
    </header>
    <div class="m-segmented">
      <button :class="{active: tab==='active'}" @click="tab='active'">AKTYWNE <i>{{ activeCount }}</i></button>
      <button :class="{active: tab==='history'}" @click="tab='history'">HISTORIA <i>{{ historyAlarms.length }}</i></button>
    </div>
  </div>

  <div class="m-list">
    <div v-if="alarmsStore.loading" class="m-empty">Loading…</div>
    <div v-else-if="!alarms.length && tab==='active'" class="m-empty m-empty-ok">
      <span class="m-empty-icon">😇</span>
      <p>Brak aktywnych alarmów</p>
      <small>Wszystko działa prawidłowo.</small>
    </div>
    <div v-else-if="!alarms.length" class="m-empty">No alarm history</div>
    <article v-for="alarm in alarms" :key="alarm.id" :class="['m-card', alarmColor(alarm.alarm_type).cls]">
      <div class="m-card-type">
        <span class="m-dot">{{ alarmColor(alarm.alarm_type).dot }}</span>
        <span>{{ alarmColor(alarm.alarm_type).label }}</span>
      </div>
      <div class="m-card-meta">
        <p><span class="m-icon">📍</span>{{ objectName(alarm.object_id) }}</p>
        <p><span class="m-icon">🌡</span>Sensor: {{ sensorName(alarm.sensor_id) }}</p>
      </div>
      <dl class="m-card-grid">
        <div><dt>Started</dt><dd>{{ startDate(alarm.triggered_at ?? alarm.detected_at) }}</dd></div>
        <div><dt>Duration</dt><dd>{{ liveDuration(alarm) }}</dd></div>
      </dl>
      <div class="m-card-status">
        <span>Status</span>
        <b :class="['m-badge', tab]">{{ mobileBadge }}</b>
      </div>
      <div class="m-card-actions">
        <button class="m-btn m-btn-ghost" @click="openDetails(alarm)">Details</button>
        <button v-if="tab==='active' && alarm.status==='triggered'" class="m-btn m-btn-primary" @click="acknowledgeOne(alarm)">Acknowledge</button>
      </div>
    </article>
  </div>

  <div v-if="showResetConfirm" class="m-modal-backdrop" @click.self="showResetConfirm = false">
    <div class="m-modal" role="alertdialog" aria-modal="true" aria-label="Confirm reset all alarms">
      <h2>Reset all alarms?</h2>
      <p>This will acknowledge {{ activeCount }} active alarm{{ activeCount === 1 ? '' : 's' }}. This cannot be undone.</p>
      <div class="m-modal-actions">
        <button class="m-btn m-btn-ghost" @click="showResetConfirm = false">Cancel</button>
        <button class="m-btn m-btn-danger" @click="confirmResetAll">Reset All</button>
      </div>
    </div>
  </div>

  <div v-if="detailsView" class="m-modal-backdrop" @click.self="closeDetails">
    <div class="m-modal m-details" role="dialog" aria-modal="true" aria-label="Alarm details">
      <div class="m-card-type">
        <span class="m-dot">{{ detailsView.dot }}</span>
        <span>{{ detailsView.label }}</span>
      </div>
      <dl class="m-details-grid">
        <div><dt>Object</dt><dd>{{ detailsView.object }}</dd></div>
        <div><dt>Sensor</dt><dd>{{ detailsView.sensor }}</dd></div>
        <div><dt>Status</dt><dd>{{ detailsView.status }}</dd></div>
        <div><dt>Detected</dt><dd>{{ detailsView.detected }}</dd></div>
        <div v-if="detailsView.triggered"><dt>Triggered</dt><dd>{{ detailsView.triggered }}</dd></div>
        <div v-if="detailsView.acknowledged"><dt>Acknowledged</dt><dd>{{ detailsView.acknowledged }}</dd></div>
        <div v-if="detailsView.resolved"><dt>Resolved</dt><dd>{{ detailsView.resolved }}</dd></div>
        <div v-if="detailsView.triggerValue"><dt>Trigger value</dt><dd>{{ detailsView.triggerValue }}</dd></div>
      </dl>
      <p v-if="detailsView.description" class="m-details-desc">{{ detailsView.description }}</p>
      <button class="m-btn m-btn-primary m-full" @click="closeDetails">Close</button>
    </div>
  </div>
</section>
</template>
<style scoped>
.alarms-page{min-height:calc(100vh - 157px);padding:18px 14px;background:#030509;color:#e4e9f2}.alarms-page header{border-bottom:1px solid #1d2530;padding-bottom:6px}.alarms-page h1{font-size:21px;margin:0 0 3px}.alarms-page p{margin:0;color:#9da9ba;font-size:13px}.tabs{display:flex;gap:10px;margin-top:23px}.tabs button{border:0;background:transparent;color:#99a5b5;font-size:13px;padding:9px 14px;border-radius:7px}.tabs .active{background:#42c9da;border:1px solid #b2e7eb;color:#07111c}.tabs i{font-style:normal;color:#b86a78;background:#e6a3ad88;border-radius:8px;padding:1px 6px;margin-left:8px}.table-toolbar{height:66px;display:flex;align-items:center;justify-content:flex-end}.table-toolbar button,.reset{background:#2b2210;color:#e2ae3f;border:1px solid #6d5422;border-radius:8px;padding:9px 15px;font-size:12px}.alarm-table{border:1px solid #1a2735;border-radius:10px;overflow:hidden;background:#171f2a}.tr{display:grid;grid-template-columns:14% 25% 17% 16% 10% 9% 9%;align-items:center;min-height:45px;padding:0 21px;color:#cbd3e0;font-size:13px;border-top:1px solid #1d2a38}.th{min-height:37px;border-top:0;color:#aeb8c9;font-size:11px;font-weight:600}.tr strong{font-size:14px;color:#fff}.tr b{font-size:13px}.tr time{color:#aab6c9}.type{font-style:normal;color:#ff717a;background:#5b2b34;border:1px solid #95505b;border-radius:12px;padding:5px 9px;font-size:10px;white-space:nowrap}.status{font-style:normal;color:#aebbd1;border:1px solid #354354;border-radius:12px;padding:5px 9px;font-size:10px}.status.triggered{color:#ff787f;border-color:#94404a;background:#4d2930}.reset{padding:5px 12px;font-size:10px}.empty{text-align:center;color:#8fa0b6;padding:50px}@media(max-width:800px){.tr{min-width:800px}.alarm-table{overflow:auto}.alarms-page{padding:15px}.table-toolbar{height:55px}}

/* ── Mobile card redesign ─────────────────────────────────────────── */
.alarms-mobile{display:none}
@media(max-width:900px){
  .alarms-page{display:none}
  .alarms-mobile{display:block;min-height:calc(100vh - 157px);background:#030509;color:#e4e9f2}
}

.m-sticky{position:sticky;top:0;z-index:5;background:#030509;padding:16px 16px 12px;border-bottom:1px solid #1a2735}
.m-header{display:flex;align-items:center;justify-content:space-between;gap:12px}
.m-title{display:flex;align-items:baseline;gap:10px;min-width:0}
.m-title h1{margin:0;font-size:22px;font-weight:800;letter-spacing:1px;color:#fff}
.m-confirm-all{min-height:42px;padding:0 13px;flex:none;background:linear-gradient(135deg,#e72537,#ab0719);border:1px solid #ff5a67;border-radius:10px;color:#fff;font-size:12px;font-weight:800;letter-spacing:.25px;cursor:pointer;box-shadow:0 0 16px rgba(232,35,52,.24)}
.m-segmented{display:flex;gap:8px;margin-top:14px;background:#0b121a;border:1px solid #1a2735;border-radius:14px;padding:5px}
.m-segmented button{flex:1;min-height:44px;border:0;border-radius:10px;background:transparent;color:#9aa7ba;font-size:14px;font-weight:700;cursor:pointer}.m-segmented button i{font-style:normal;margin-left:6px;color:#78a4cf}.m-segmented button.active{background:#112332;color:#40d8e5;border:1px solid #1b7f92}.m-segmented button.active i{color:#ff5d68}

.m-list{position:relative;padding:18px 16px 16px 38px}.m-list::before{content:"";position:absolute;top:22px;bottom:22px;left:27px;width:1px;background:linear-gradient(#ff3445,#ffb020 55%,#60738d)}
.m-empty{text-align:center;color:#8fa0b6;padding:60px 20px;font-size:15px}
.m-empty-ok{display:flex;flex-direction:column;align-items:center;gap:8px}
.m-empty-icon{font-size:44px;filter:drop-shadow(0 0 10px rgba(126,192,255,.34))}
.m-empty-ok p{margin:0;color:#e4e9f2;font-size:18px;font-weight:700}
.m-empty-ok small{color:#8fa0b6;font-size:14px}

.m-card{position:relative;background:#0d151f;border:1px solid #1c2938;border-radius:18px;padding:18px;margin-bottom:16px;box-shadow:0 6px 18px #0007}.m-card::before{content:"";position:absolute;width:14px;height:14px;border-radius:50%;left:-19px;top:29px;background:#8ca0ba;border:3px solid #030509}.m-card.high{border-color:#5a2530}.m-card.high::before{background:#ff3547;box-shadow:0 0 12px #ff3547}.m-card.low{border-color:#664617}.m-card.low::before{background:#ffb020;box-shadow:0 0 12px #ffb020}.m-card.offline{border-color:#5c421f}.m-card.offline::before{background:#ffb020;box-shadow:0 0 12px #ffb020}
.m-card-type{display:flex;align-items:center;gap:10px;font-size:18px;font-weight:800;letter-spacing:.4px;color:#fff}
.m-dot{font-size:20px;line-height:1}
.m-card-meta{margin-top:14px;display:flex;flex-direction:column;gap:8px}
.m-card-meta p{margin:0;display:flex;align-items:center;gap:9px;font-size:16px;color:#cbd3e0}
.m-icon{font-size:17px}
.m-card-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin:18px 0 0;padding-top:16px;border-top:1px solid #1a2735}
.m-card-grid dt{margin:0;font-size:12px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:#7e8ea3}
.m-card-grid dd{margin:5px 0 0;font-size:18px;font-weight:700;color:#fff}
.m-card-status{display:flex;align-items:center;justify-content:space-between;margin-top:16px;padding-top:16px;border-top:1px solid #1a2735;font-size:14px;color:#9aa7ba}
.m-badge{font-style:normal;font-size:13px;font-weight:800;letter-spacing:.5px;border-radius:20px;padding:7px 14px}
.m-badge.active{color:#ff8087;background:#4d2930;border:1px solid #94404a}
.m-badge.history{color:#7be7a8;background:#12351f;border:1px solid #245c37}
.m-card-actions{display:flex;gap:12px;margin-top:18px}
.m-btn{flex:1;min-height:48px;border-radius:14px;font-size:15px;font-weight:700;cursor:pointer;border:1px solid transparent}
.m-btn-ghost{background:#131b26;color:#c7d1e0;border-color:#28374a}
.m-btn-primary{background:#42c9da;color:#07111c}
.m-btn-danger{background:#e2544f;color:#1a0605}
.m-full{flex:none;width:100%}

.m-modal-backdrop{position:fixed;inset:0;background:#000a;z-index:20;display:flex;align-items:flex-end;justify-content:center}
.m-modal{width:100%;max-width:520px;background:#0d151f;border:1px solid #1c2938;border-radius:24px 24px 0 0;padding:24px 20px calc(24px + env(safe-area-inset-bottom));box-shadow:0 -12px 30px #000a}
.m-modal h2{margin:0 0 10px;font-size:19px;color:#fff}
.m-modal p{margin:0 0 20px;font-size:15px;color:#aab6c9;line-height:1.5}
.m-modal-actions{display:flex;gap:12px}
.m-details-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin:18px 0}
.m-details-grid dt{margin:0;font-size:12px;font-weight:700;letter-spacing:.6px;text-transform:uppercase;color:#7e8ea3}
.m-details-grid dd{margin:5px 0 0;font-size:16px;font-weight:600;color:#fff}
.m-details-desc{font-size:14px;color:#aab6c9;background:#0b121a;border:1px solid #1a2735;border-radius:12px;padding:12px 14px;margin:0 0 20px;line-height:1.5}

@media(min-width:480px){
  .m-modal{max-width:420px;border-radius:24px;margin-bottom:24px}
  .m-modal-backdrop{align-items:center}
}
</style>
