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
const selectedObject=computed(()=>objectsStore.objects.find(x=>x.id===selectedObjectId.value));

const highThreshold=computed(()=>{const c=alarmConfigs.value.find(c=>c.alarm_type==='high_temperature');return c?.is_enabled?c.threshold_value:null});
const lowThreshold=computed(()=>{const c=alarmConfigs.value.find(c=>c.alarm_type==='low_temperature');return c?.is_enabled?c.threshold_value:null});
const sensorAlarms=computed(()=>alarmsStore.alarms.filter(a=>a.sensor_id===sensor.value?.id));
const activeAlarm=computed(()=>sensorAlarms.value.find(a=>a.status==='triggered'||a.status==='pending')||null);
const activeAlarmLabel=computed(()=>{
  if(!activeAlarm.value) return null;
  return ({high_temperature:"HIGH TEMPERATURE",low_temperature:"LOW TEMPERATURE",offline:"DEVICE OFFLINE"} as Record<string,string>)[activeAlarm.value.alarm_type]||activeAlarm.value.alarm_type;
});

function temperature(value:number|null|undefined){return value==null?"—":`${value.toFixed(1)} °C`}
function online(){const last=sensor.value?.last_message_at;if(!last||!sensor.value)return false;return Date.now()-new Date(last).getTime()<sensor.value.offline_timeout_seconds*1000}

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

// Entry point is now the temperature itself, on whichever sensor card the
// user taps — there's no separate "Chart" button and no sensor dropdown to
// pick from first, every sensor for the object is already on the page.
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
    <div class="hero">
     <span class="object-name-top">{{selectedObject?.name}}</span>
     <button class="temp-cta" type="button" :aria-label="`Otwórz wykres — ${item.name}`" @click="openChartFor(item)">
      <span class="temp-value">{{temperature(item.current_temperature)}}</span>
      <span class="temp-delta">↓ 0.3°</span>
     </button>
     <span class="sensor-name-bottom">{{item.name}}</span>
    </div>
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
   own tile: object name on top (small, muted), the temperature itself
   large and center (and the ONLY way into that sensor's chart — no
   separate button anymore), sensor name below it.

   auto-fit, not auto-fill: auto-fill reserves a full grid track for every
   column that COULD fit at the minimum size, even empty ones — with 1-2
   real sensors on a wide screen that left 3-4 invisible empty tracks
   eating most of the row, squeezing the real card down near its 240px
   floor and reading as "tiny widget in a sea of blank space". auto-fit
   collapses those empty tracks to zero, so real cards expand via 1fr to
   actually use the available width — a lone sensor now reads as the
   dominant hero tile the design always intended, and several sensors
   settle into a proper multi-column overview instead of a cramped strip. */
.sensor-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:20px}
.temperature-panel{padding:0;border-radius:12px;overflow:hidden;display:flex;flex-direction:column}

.hero{padding:34px 28px;display:flex;flex-direction:column;align-items:center;gap:10px}

.object-name-top{color:#9aabc5;font-size:14px;letter-spacing:.02em}

/* The temperature is the tap target now — styled to invite a tap (subtle
   hover/active feedback) without looking like a boxed button; it should
   still read first and foremost as "the current reading". Sized to
   dominate the tile (a SCADA-style hero readout), not just sit in it. */
.temp-cta{
  background:none;border:none;padding:6px 14px;margin:2px 0;border-radius:12px;cursor:pointer;
  display:flex;align-items:baseline;justify-content:center;gap:12px;flex-wrap:wrap;
}
.temp-cta:hover{background:rgba(7,201,243,0.08)}
.temp-cta:active{background:rgba(7,201,243,0.16)}
.temp-value{font-size:clamp(56px,8vw,92px);font-weight:700;letter-spacing:-2px;color:#07c9f3;line-height:1}
.temp-delta{font-size:clamp(14px,2.2vw,17px);color:#00d6ee;font-weight:600}

.sensor-name-bottom{color:#00dcea;font-size:14px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}

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
   grid's gutters), one tile per row, and a temperature sized as a genuine
   vw-driven hero number (clamped for very narrow/wide phones) rather than
   inheriting the desktop clamp's proportions. */
@media(max-width:640px){
 .dashboard{padding:10px}
 .selectors{grid-template-columns:1fr;gap:12px}
 .sensor-grid{grid-template-columns:1fr;gap:12px}
 .hero{padding:36px 16px}
 .temp-value{font-size:clamp(58px,17vw,84px)}
 .temp-delta{font-size:15px}
 .object-name-top,.sensor-name-bottom{font-size:15px}
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
