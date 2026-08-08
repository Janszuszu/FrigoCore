<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useObjectsStore } from "@/stores/objects";
import { useSensorsStore } from "@/stores/sensors";
import { useAlarmsStore } from "@/stores/alarms";
import { apiAlarmConfigs } from "@/api";
import type { AlarmConfigItem, ChartRange, MeasurementItem, SensorItem } from "@/types";
import TemperatureChart from "@/components/TemperatureChart.vue";

const objectsStore=useObjectsStore(), sensorsStore=useSensorsStore(), alarmsStore=useAlarmsStore();
const selectedObjectId=ref(""), range=ref<ChartRange>("24H");
const alarmConfigs=ref<AlarmConfigItem[]>([]);
// The chart is a full-viewport panel that mounts when a sensor's
// temperature is tapped and unmounts on close — no slide/transition, just
// plain v-if. Real Fullscreen is requested on open (see openChartFor); the
// panel itself is still a full-viewport overlay even if that's denied
// (Permissions Policy, unsupported, etc.) so it never becomes unusable.
const showChart=ref(false);
const fullscreenRoot=ref<HTMLElement|null>(null);
const isChartFullscreen=ref(false);

type OrientationLock = { lock?: (o: string) => Promise<void>; unlock?: () => void };
function getOrientation(): OrientationLock | undefined {
  return (screen as unknown as { orientation?: OrientationLock }).orientation;
}
async function requestLandscape() {
  try { await getOrientation()?.lock?.("landscape"); }
  catch { /* Not supported (e.g. iPhone Safari) or rejected — ignore, fullscreen itself still works. */ }
}
function releaseOrientation() {
  try { getOrientation()?.unlock?.(); } catch { /* ignore */ }
}

function onFullscreenChange() {
  isChartFullscreen.value = document.fullscreenElement === fullscreenRoot.value;
  if (isChartFullscreen.value) {
    requestLandscape();
  } else {
    releaseOrientation();
    // Exiting fullscreen (Escape, swiping away on mobile, ...) is also how
    // the chart panel closes — there's no other embedded position for it
    // to fall back into.
    showChart.value = false;
  }
}

async function requestChartFullscreen(){
  try{ await fullscreenRoot.value?.requestFullscreen?.(); }
  catch{ /* Permissions Policy denial, unsupported, etc. — fail silently, the
            chart is still fully usable as a large in-page panel instead of
            becoming unreachable. */ }
}
async function exitChartFullscreen(){
  if(document.fullscreenElement){
    try{ await document.exitFullscreen(); } catch{ /* ignore */ }
  }
}

const sensor=computed(()=>sensorsStore.selectedSensor);
const readings=computed(()=>[...sensorsStore.measurements].reverse());
const validTemps=computed(()=>readings.value.filter((x): x is MeasurementItem & {temperature:number}=>typeof x.temperature==='number'&&!isNaN(x.temperature)));
const stats=computed(()=>{const temps=validTemps.value.map(x=>x.temperature);return temps.length?{min:Math.min(...temps),max:Math.max(...temps),avg:temps.reduce((a,b)=>a+b,0)/temps.length}:{min:null,max:null,avg:null}});

const highThreshold=computed(()=>{const c=alarmConfigs.value.find(c=>c.alarm_type==='high_temperature');return c?.is_enabled?c.threshold_value:null});
const lowThreshold=computed(()=>{const c=alarmConfigs.value.find(c=>c.alarm_type==='low_temperature');return c?.is_enabled?c.threshold_value:null});
function alarmsFor(sensorId:string|undefined){return alarmsStore.alarms.filter(a=>a.sensor_id===sensorId)}
const sensorAlarms=computed(()=>alarmsFor(sensor.value?.id));
const activeAlarm=computed(()=>sensorAlarms.value.find(a=>a.status==='triggered'||a.status==='pending')||null);
const activeAlarmLabel=computed(()=>{
  if(!activeAlarm.value) return null;
  return ({high_temperature:"HIGH TEMPERATURE",low_temperature:"LOW TEMPERATURE",offline:"DEVICE OFFLINE"} as Record<string,string>)[activeAlarm.value.alarm_type]||activeAlarm.value.alarm_type;
});

function temperature(value:number|null|undefined){return value==null?"—":`${value.toFixed(1)} °C`}
function temperatureValue(value:number|null|undefined){return value==null?"—":value.toFixed(1)}
// The API's timestamps are UTC but sometimes serialize without an
// offset/"Z" suffix — plain `new Date(iso)` would then parse them as local
// time and throw every online/offline comparison off by the local UTC
// offset (e.g. reading a sensor that reported 1 minute ago as OFFLINE).
function parseUtc(iso:string){return new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(iso)?iso:`${iso}Z`).getTime()}
function isOnline(item:SensorItem|null){const last=item?.last_message_at;if(!last||!item)return false;return Date.now()-parseUtc(last)<item.offline_timeout_seconds*1000}
function online(){return isOnline(sensor.value)}

// ---------- Sensor card display helpers ----------
// A sensor only has a `name` — no separate type/description/status field —
// so the icon and subtitle line the reference card wants are derived from
// that name (normalized to strip Polish diacritics for matching), and the
// status dot is derived from the same online/alarm data already loaded for
// the whole object. All client-side, all reusable for every object/sensor.
function normalizeSensorName(name:string){
  return name.toLowerCase()
    .replaceAll('ł','l').replaceAll('ą','a').replaceAll('ę','e').replaceAll('ó','o')
    .replaceAll('ś','s').replaceAll('ż','z').replaceAll('ź','z').replaceAll('ć','c').replaceAll('ń','n');
}
type SensorIconKind='fan'|'cylinder'|'snowflake'|'room'|'sun'|'thermometer';
function sensorIconKind(name:string):SensorIconKind{
  const n=normalizeSensorName(name);
  if(n.includes('skraplacz')) return 'fan';
  if(n.includes('tlocz')) return 'cylinder';
  if(n.includes('parownik')) return 'snowflake';
  if(n.includes('pomieszcz')||n.includes('komora')||n.includes('chlodni')||n.includes('mroz')) return 'room';
  if(n.includes('zewnetrz')||n.includes('otoczeni')||n.includes('ambient')||n.includes('outdoor')) return 'sun';
  return 'thermometer';
}
function sensorDescription(name:string){
  const parts=name.split(' - ');
  const last=(parts.length>1?parts[parts.length-1]:name.trim().split(/\s+/).pop())||name;
  return last.charAt(0).toUpperCase()+last.slice(1).toLowerCase();
}
const ALARM_SHORT_LABEL:Record<string,string>={high_temperature:"HIGH TEMP",low_temperature:"LOW TEMP",offline:"OFFLINE"};
function cardStatus(item:SensorItem){
  const active=alarmsFor(item.id).find(a=>a.status==='triggered');
  if(active) return {text:ALARM_SHORT_LABEL[active.alarm_type]||"ALARM",cls:'alarm'};
  if(!isOnline(item)) return {text:'OFFLINE',cls:'offline'};
  const pending=alarmsFor(item.id).find(a=>a.status==='pending'||a.status==='acknowledged');
  if(pending) return {text:'PENDING',cls:'pending'};
  return {text:'OK',cls:'ok'};
}

async function loadAlarmConfigs(sensorId:string){
  try{alarmConfigs.value=await apiAlarmConfigs.list(sensorId)}catch{alarmConfigs.value=[]}
}

function applyRange(r:ChartRange){
  range.value=r;
  sensorsStore.fetchMeasurementsForRange(r);
}

function onTargetColumns(n:number){
  sensorsStore.setTargetColumns(n);
}

// Entry point is the whole sensor row now — tap anywhere on it — there's
// no separate "Chart" button and no sensor dropdown to pick from first,
// every sensor for the object is already on the page.
async function openChartFor(item:SensorItem){
  range.value="24H";
  sensorsStore.selectSensor(item,"24H");
  await loadAlarmConfigs(item.id);
  showChart.value=true;
  await nextTick();
  await requestChartFullscreen();
}
async function closeChart(){
  showChart.value=false;
  await exitChartFullscreen();
}

async function pickObject(){
  closeChart();
  sensorsStore.selectSensor(null);
  if(selectedObjectId.value){
    await sensorsStore.fetchSensors(selectedObjectId.value);
    await alarmsStore.fetchAlarms(selectedObjectId.value);
  }
}

onMounted(async()=>{
  await objectsStore.fetchObjects();
  if(objectsStore.activeObjects[0]){selectedObjectId.value=objectsStore.activeObjects[0].id;pickObject()}
  document.addEventListener("fullscreenchange", onFullscreenChange);
});
onUnmounted(()=>{
  document.removeEventListener("fullscreenchange", onFullscreenChange);
});
watch(selectedObjectId,pickObject);
</script>
<template>
 <section class="dashboard">
  <div class="selectors"><label>OBIEKT<select v-model="selectedObjectId"><option value="">Wybierz obiekt</option><option v-for="object in objectsStore.activeObjects" :key="object.id" :value="object.id">{{object.name}}</option></select></label></div>

  <div v-if="selectedObjectId && sensorsStore.sensors.length" class="sensor-grid">
   <article v-for="item in sensorsStore.sensors" :key="item.id" class="temperature-panel">
    <button class="sensor-row" type="button" :aria-label="`Otwórz wykres — ${item.name}, ${temperature(item.current_temperature)}`" @click="openChartFor(item)">
     <span class="card-icon">
      <svg v-if="sensorIconKind(item.name)==='fan'" viewBox="0 0 24 24">
       <path d="M12 12C10 9 9 5 12 2C15 5 14 9 12 12Z"/>
       <path d="M12 12C10 9 9 5 12 2C15 5 14 9 12 12Z" transform="rotate(120 12 12)"/>
       <path d="M12 12C10 9 9 5 12 2C15 5 14 9 12 12Z" transform="rotate(240 12 12)"/>
       <circle cx="12" cy="12" r="1.6"/>
      </svg>
      <svg v-else-if="sensorIconKind(item.name)==='cylinder'" viewBox="0 0 24 24">
       <ellipse cx="12" cy="5.5" rx="6" ry="2.3"/>
       <path d="M6 5.5v12c0 1.27 2.69 2.3 6 2.3s6-1.03 6-2.3v-12"/>
       <path d="M6 11.5c0 1.27 2.69 2.3 6 2.3s6-1.03 6-2.3"/>
      </svg>
      <svg v-else-if="sensorIconKind(item.name)==='snowflake'" viewBox="0 0 24 24">
       <path d="M12 2v20M4.5 6.5l15 11M19.5 6.5l-15 11"/>
      </svg>
      <svg v-else-if="sensorIconKind(item.name)==='room'" viewBox="0 0 24 24">
       <path d="M4 11.5 12 4l8 7.5"/>
       <path d="M6 10v9h12v-9"/>
      </svg>
      <svg v-else-if="sensorIconKind(item.name)==='sun'" viewBox="0 0 24 24">
       <circle cx="12" cy="12" r="4"/>
       <path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>
      </svg>
      <svg v-else viewBox="0 0 24 24">
       <path d="M10 14.2V4.5a2 2 0 0 1 4 0v9.7a4 4 0 1 1-4 0Z"/>
       <path d="M12 7h2M12 10h2"/>
      </svg>
     </span>
     <span class="card-body">
      <span class="card-name">{{item.name}}</span>
      <span class="card-desc">{{sensorDescription(item.name)}}</span>
      <span :class="['card-status', cardStatus(item).cls]"><i></i>{{cardStatus(item).text}}</span>
     </span>
     <span class="card-value"><b>{{temperatureValue(item.current_temperature)}}</b><small v-if="item.current_temperature!=null">°C</small></span>
    </button>
   </article>
  </div>
  <div v-else-if="selectedObjectId" class="empty">Brak sensorów dla wybranego obiektu.</div>
  <div v-else class="empty">Wybierz obiekt, aby zobaczyć dane.</div>

  <div v-if="showChart && sensor" ref="fullscreenRoot" class="chart-overlay">
   <div class="ranges">
    <button class="back-btn" type="button" aria-label="Wróć" @click="closeChart">
     <svg viewBox="0 0 24 24"><path d="M15 18l-6-6 6-6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
     <span>Wróć</span>
    </button>
    <div class="chart-stats">
     <span class="chart-stat"><b>MIN</b> {{temperature(stats.min)}}</span>
     <span class="chart-stat-sep" aria-hidden="true">|</span>
     <span class="chart-stat"><b>AVG</b> {{temperature(stats.avg)}}</span>
     <span class="chart-stat-sep" aria-hidden="true">|</span>
     <span class="chart-stat"><b>MAX</b> {{temperature(stats.max)}}</span>
    </div>
    <div class="range-buttons">
     <button v-for="item in (['LIVE','1H','24H','7D'] as ChartRange[])" :key="item" :class="{active:range===item}" @click="applyRange(item)">{{item}}</button>
    </div>
   </div>
   <TemperatureChart
     :sensor="sensor"
     :readings="readings"
     :range="range"
     :high-threshold="highThreshold"
     :low-threshold="lowThreshold"
     :alarms="sensorAlarms"
     :active-alarm-label="activeAlarmLabel"
     :online="online()"
     :loading="sensorsStore.rangeLoading"
     @target-columns="onTargetColumns"
   />
  </div>
 </section>
</template>
<style scoped>
.dashboard{padding:21px 25px 10px;max-width:1280px;margin:auto}.selectors{display:grid;grid-template-columns:405px 1fr;gap:25px;align-items:end;margin-bottom:21px}.selectors label{font-size:14px;color:#aab9cf;display:grid;gap:8px}.selectors select{appearance:none;height:48px;border:1px solid #2b4b67;border-radius:7px;background:#081421 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath d='m1 1 5 5 5-5' fill='none' stroke='%23b8c9e8' stroke-width='2'/%3E%3C/svg%3E") no-repeat calc(100% - 17px) center;color:#e8effa;font-size:17px;padding:0 48px 0 18px}.temperature-panel{background:radial-gradient(circle at 45% 30%,#0d1d2d,#07121e 70%);border:1px solid #172d42}

/* ---------- Sensor tiles ----------
   Every sensor for the selected object is on the page at once, each its
   own tile: a single full-width row (icon, name/subtitle/status, value) —
   never two tiles sharing a row, however many columns the grid below
   happens to lay out at the current viewport width.

   auto-fit, not auto-fill: auto-fill reserves a full grid track for every
   column that COULD fit at the minimum size, even empty ones — with 1-2
   real sensors on a wide screen that left 3-4 invisible empty tracks
   eating most of the row, squeezing the real card down near its 360px
   floor and reading as "tiny widget in a sea of blank space". auto-fit
   collapses those empty tracks to zero, so real cards expand via 1fr to
   actually use the available width — a lone sensor now reads as a proper
   full-width row, and several sensors settle into a multi-column overview
   instead of a cramped strip. */
.sensor-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:20px}
.temperature-panel{padding:0;border-radius:12px;overflow:hidden;display:flex;flex-direction:column}

/* The whole row is the tap target that opens the chart — icon + name +
   subtitle + status on the left (all derived from the sensor's name and
   its live online/alarm state, since that's all a sensor actually has),
   value + unit pinned to the right via margin-left:auto. One row per
   sensor, full width, in every grid cell — the grid itself (below)
   decides how many cells sit per line at a given viewport. */
.sensor-row{
  width:100%;background:none;border:0;margin:0;padding:20px 22px;
  display:flex;align-items:center;gap:16px;
  font:inherit;color:inherit;text-align:left;cursor:pointer;
}
.sensor-row:hover{background:rgba(7,201,243,0.06)}
.sensor-row:active{background:rgba(7,201,243,0.12)}

.card-icon{
  flex:none;width:46px;height:46px;border-radius:50%;
  display:grid;place-items:center;
  background:rgba(7,201,243,0.08);border:1px solid rgba(7,201,243,0.35);color:#07c9f3;
}
.card-icon svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:1.7;stroke-linecap:round;stroke-linejoin:round}

.card-body{flex:1;min-width:0;display:flex;flex-direction:column;gap:5px}
.card-name{color:#e8effa;font-size:15px;font-weight:700;letter-spacing:.02em;overflow-wrap:anywhere;text-transform:uppercase}
.card-desc{color:#8fa1ba;font-size:13px}
.card-status{display:flex;align-items:center;gap:6px;font-size:12px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:#00e77b}
.card-status i{width:7px;height:7px;border-radius:50%;background:currentColor;flex:none}
.card-status.alarm{color:#ff717a}
.card-status.offline,.card-status.pending{color:#ffb020}

/* nowrap: the reading ("22.3" + "°C") must stay one line — without this a
   narrow row can wrap the unit onto its own line. */
.card-value{flex:none;margin-left:auto;padding-left:12px;display:flex;align-items:baseline;gap:4px;white-space:nowrap}
.card-value b{font-size:clamp(26px,6vw,34px);font-weight:700;letter-spacing:-1px;color:#07c9f3;line-height:1}
.card-value small{font-size:14px;font-weight:600;color:#07c9f3}

.empty{text-align:center;padding:100px;color:#8fa1ba}

/* ---------- Chart overlay ----------
   A plain full-viewport panel — mounted with v-if (no transition/animation
   component) when a sensor's temperature is tapped, unmounted the same way
   on close. Real Fullscreen is requested on open (requestChartFullscreen)
   and released on close; if that's denied by the browser the panel still
   renders at full-viewport size via this CSS, so it's never unusable. */
.chart-overlay{
  position:fixed;inset:0;z-index:40;background:#07121e;overflow:hidden;
  padding:4px;display:flex;flex-direction:column;
}

/* Floating toolbar: back button, MIN/AVG/MAX, range buttons — pinned along
   the top edge so the chart underneath still occupies almost the entire
   screen. Semi-transparent + blurred so it stays legible without hiding
   the plot; the chart's own axis sits at the bottom, so this never covers it. */
.ranges{
  position:absolute;top:14px;left:14px;right:14px;z-index:41;
  display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;
  padding:8px 14px;
  background:rgba(7,18,30,0.85);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);
  border:1px solid rgba(38,62,86,0.7);border-radius:12px;
  box-shadow:0 8px 24px rgba(0,0,0,0.35);
}
.back-btn,.range-buttons button{
  display:flex;align-items:center;justify-content:center;gap:7px;
  height:40px;padding:0 18px;flex:none;white-space:nowrap;
  background:#091725;border:1px solid #263e56;border-radius:8px;
  color:#afc0dc;font-size:13px;font-weight:600;letter-spacing:.02em;cursor:pointer;
}
.back-btn svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.back-btn:hover{border-color:#00cce3;color:#00e5ef}
.range-buttons{display:flex;gap:10px}
.range-buttons .active{border-color:#00cce3;color:#00e5ef;background:#063142}

/* MIN/AVG/MAX for the currently selected range. */
.chart-stats{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;font-size:13px;color:#afc0dc;font-variant-numeric:tabular-nums}
.chart-stat b{color:#e8effa;font-weight:700;letter-spacing:.04em;margin-right:4px}
.chart-stat-sep{color:#3a5470}

@media(max-width:1100px){.dashboard{max-width:100%}}

/* ---------- Mobile dashboard ----------
   A deliberately different composition, not the desktop one scaled down:
   near-full-bleed width (small fixed padding instead of the desktop
   grid's gutters), one tile per row (always — never the 2-column squeeze
   auto-fit would otherwise produce once two-plus sensors fit 360px-wide
   tracks side by side), and a temperature sized as a genuine vw-driven
   hero number (clamped for very narrow/wide phones) rather than
   inheriting the desktop clamp's proportions.
   Breakpoint matches the header's own mobile switch (700px) so both
   never disagree about what "mobile" means on the same screen. */
@media(max-width:700px){
 .dashboard{padding:10px}
 .selectors{grid-template-columns:1fr;gap:12px}
 .sensor-grid{grid-template-columns:1fr;gap:12px}
 .sensor-row{padding:16px 14px;gap:12px}
 .card-icon{width:42px;height:42px}
 .card-icon svg{width:19px;height:19px}
 .card-name{font-size:14px}
 .card-desc{font-size:12px}
 .card-value b{font-size:clamp(22px,8vw,30px)}
 .card-value small{font-size:13px}
}

@media(max-width:800px){
 .back-btn span{display:none}
 .back-btn{width:40px;padding:0}
 .ranges{top:8px;left:8px;right:8px;gap:6px;padding:6px 10px}
 .range-buttons{gap:6px}
 .chart-stats{font-size:11px;gap:6px}
}

/* Short landscape (~375-430px tall once rotated): trim the floating
   toolbar further to keep the chart close to the 90-95% target without
   shrinking tap targets past comfortable thumb use. */
@media(max-height:430px){
 .chart-overlay{padding:2px}
 .ranges{top:6px;left:6px;right:6px;padding:5px 8px}
 .ranges button,.back-btn{height:36px}
}
</style>
