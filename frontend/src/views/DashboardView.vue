<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useObjectsStore } from "@/stores/objects";
import { useSensorsStore } from "@/stores/sensors";
import { useAlarmsStore } from "@/stores/alarms";
import { apiAlarmConfigs } from "@/api";
import type { AlarmConfigItem, ChartRange, MeasurementItem } from "@/types";
import TemperatureChart from "@/components/TemperatureChart.vue";

const objectsStore=useObjectsStore(), sensorsStore=useSensorsStore(), alarmsStore=useAlarmsStore();
const selectedObjectId=ref(""), selectedSensorId=ref(""), range=ref<ChartRange>("24H");
const alarmConfigs=ref<AlarmConfigItem[]>([]);
const isChartFullscreen=ref(false);
// The chart no longer lives on the Dashboard itself — it only exists in the
// DOM while the fullscreen view is open (see openChart/onFullscreenChange).
// Separate from isChartFullscreen (which mirrors the real Fullscreen API
// state): showChart mounts the chart panel BEFORE requestFullscreen() is
// called, since that call needs an already-rendered element to target.
const showChart=ref(false);

// Fullscreen wraps the chart + range selector together (not just the
// TemperatureChart component) because the range selector must stay
// visible while fullscreen, per spec.
const fullscreenRoot=ref<HTMLElement | null>(null);

type OrientationLock = { lock?: (o: string) => Promise<void>; unlock?: () => void };
function getOrientation(): OrientationLock | undefined {
  return (screen as unknown as { orientation?: OrientationLock }).orientation;
}
async function requestLandscape() {
  try {
    await getOrientation()?.lock?.("landscape");
  } catch {
    // Not supported (e.g. iPhone Safari) or rejected by the browser — the
    // spec calls for ignoring this gracefully, fullscreen itself still works.
  }
}
function releaseOrientation() {
  try {
    getOrientation()?.unlock?.();
  } catch {
    /* ignore */
  }
}

function onFullscreenChange() {
  isChartFullscreen.value = document.fullscreenElement === fullscreenRoot.value;
  if (isChartFullscreen.value) {
    requestLandscape();
  } else {
    releaseOrientation();
    // Exiting fullscreen (Escape, the Exit Fullscreen button, swiping away
    // on mobile, ...) is also how the chart leaves the Dashboard again —
    // there's no other embedded position for it to fall back into.
    showChart.value = false;
  }
}

async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) {
      await document.exitFullscreen();
    } else {
      await fullscreenRoot.value?.requestFullscreen();
    }
  } catch {
    // Fullscreen can be denied by a Permissions Policy (embedding context,
    // browser/enterprise policy) — fail silently rather than surface an
    // unhandled rejection; isChartFullscreen just stays in sync with
    // reality via the fullscreenchange listener either way. showChart stays
    // true in that case, so the chart is still usable as a large in-page
    // panel instead of becoming completely unreachable.
  }
}

// Entry point for the "Chart" icon button next to the temperature card:
// mount the chart (still selected object/sensor, default 24H per spec),
// wait for it to actually exist in the DOM, then request fullscreen on it.
async function openChart() {
  applyRange("24H");
  showChart.value = true;
  await nextTick();
  await toggleFullscreen();
}

const sensor=computed(()=>sensorsStore.selectedSensor);
const readings=computed(()=>[...sensorsStore.measurements].reverse());
const validTemps=computed(()=>readings.value.filter((x): x is MeasurementItem & {temperature:number}=>typeof x.temperature==='number'&&!isNaN(x.temperature)));
const stats=computed(()=>{const temps=validTemps.value.map(x=>x.temperature);return temps.length?{min:Math.min(...temps),max:Math.max(...temps),avg:temps.reduce((a,b)=>a+b,0)/temps.length}:{min:null,max:null,avg:null}});
const selectedObject=computed(()=>objectsStore.objects.find(x=>x.id===selectedObjectId.value));

const highThreshold=computed(()=>{const c=alarmConfigs.value.find(c=>c.alarm_type==='high_temperature');return c?.is_enabled?c.threshold_value:null});
const lowThreshold=computed(()=>{const c=alarmConfigs.value.find(c=>c.alarm_type==='low_temperature');return c?.is_enabled?c.threshold_value:null});
const sensorAlarms=computed(()=>alarmsStore.alarms.filter(a=>a.sensor_id===selectedSensorId.value));
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

async function pickObject(){
  selectedSensorId.value="";
  sensorsStore.selectSensor(null);
  if(selectedObjectId.value){
    await sensorsStore.fetchSensors(selectedObjectId.value);
    await alarmsStore.fetchAlarms(selectedObjectId.value);
  }
  if(sensorsStore.sensors[0]){selectedSensorId.value=sensorsStore.sensors[0].id;pickSensor()}
}
function pickSensor(){
  range.value="24H";
  sensorsStore.selectSensor(sensorsStore.sensors.find(x=>x.id===selectedSensorId.value)||null,"24H");
  if(selectedSensorId.value) loadAlarmConfigs(selectedSensorId.value);
}

onMounted(async()=>{
  await objectsStore.fetchObjects();
  if(objectsStore.activeObjects[0]){selectedObjectId.value=objectsStore.activeObjects[0].id;pickObject()}
  document.addEventListener("fullscreenchange", onFullscreenChange);
});
onUnmounted(()=>{document.removeEventListener("fullscreenchange", onFullscreenChange)});
watch(selectedObjectId,pickObject);
</script>
<template>
 <section class="dashboard">
  <div class="selectors"><label>OBIEKT<select v-model="selectedObjectId"><option value="">Wybierz obiekt</option><option v-for="object in objectsStore.activeObjects" :key="object.id" :value="object.id">{{object.name}}</option></select></label><label>SENSOR<select v-model="selectedSensorId" @change="pickSensor" :disabled="!selectedObjectId"><option value="">Wybierz sensor</option><option v-for="item in sensorsStore.sensors" :key="item.id" :value="item.id">{{item.name}}</option></select></label></div>
  <template v-if="sensor">
   <article class="temperature-panel">
    <div class="hero">
     <button class="chart-cta" type="button" aria-label="Otwórz wykres" @click="openChart">
      <svg class="chart-cta-icon" viewBox="0 0 24 24"><path d="M4 20V13M11 20V8M18 20V4" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <span class="chart-cta-label">CHART</span>
     </button>
     <div class="hero-readout">
      <div class="hero-temp"><span class="temp-value">{{temperature(sensor.current_temperature)}}</span><span class="temp-delta">↓ 0.3°</span></div>
      <div class="hero-meta"><span class="sensor-name">{{sensor.name}}</span><span class="object-name">{{selectedObject?.name}}</span></div>
     </div>
    </div>
   </article>
   <article v-if="showChart" class="chart-panel">
    <div ref="fullscreenRoot" class="chart-fullscreen-root" :class="{fullscreen:isChartFullscreen}">
     <TemperatureChart
       v-if="sensor"
       :sensor="sensor"
       :readings="readings"
       :range="range"
       :high-threshold="highThreshold"
       :low-threshold="lowThreshold"
       :alarms="sensorAlarms"
       :active-alarm-label="activeAlarmLabel"
       :online="online()"
       :loading="sensorsStore.rangeLoading"
     />
     <div class="ranges">
      <div class="chart-stats">
       <span class="chart-stat"><b>MIN</b> {{temperature(stats.min)}}</span>
       <span class="chart-stat-sep" aria-hidden="true">|</span>
       <span class="chart-stat"><b>AVG</b> {{temperature(stats.avg)}}</span>
       <span class="chart-stat-sep" aria-hidden="true">|</span>
       <span class="chart-stat"><b>MAX</b> {{temperature(stats.max)}}</span>
      </div>
      <div class="range-controls">
       <div class="range-buttons">
        <button v-for="item in (['LIVE','1H','24H','7D'] as ChartRange[])" :key="item" :class="{active:range===item}" @click="applyRange(item)">{{item}}</button>
       </div>
       <button v-if="!isChartFullscreen" class="fullscreen-btn" type="button" aria-label="Fullscreen" @click="toggleFullscreen">
        <svg viewBox="0 0 24 24"><path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5" /></svg>
        <span>Fullscreen</span>
       </button>
       <button v-else class="exit-fullscreen-btn" type="button" aria-label="Exit fullscreen" @click="toggleFullscreen">
        <svg viewBox="0 0 24 24"><path d="M3 8V3h5M21 8V3h-5M3 16v5h5M21 16v5h-5" /></svg>
        <span>Exit Fullscreen</span>
       </button>
      </div>
     </div>
    </div>
   </article>
  </template><div v-else class="empty">Wybierz obiekt i sensor, aby zobaczyć dane.</div>
 </section>
</template>
<style scoped>
.dashboard{padding:21px 25px 10px;max-width:1280px;margin:auto}.selectors{display:grid;grid-template-columns:405px 388px 1fr;gap:25px;align-items:end;margin-bottom:21px}.selectors label{font-size:14px;color:#aab9cf;display:grid;gap:8px}.selectors select{appearance:none;height:48px;border:1px solid #2b4b67;border-radius:7px;background:#081421 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath d='m1 1 5 5 5-5' fill='none' stroke='%23b8c9e8' stroke-width='2'/%3E%3C/svg%3E") no-repeat calc(100% - 17px) center;color:#e8effa;font-size:17px;padding:0 48px 0 18px}.temperature-panel,.chart-panel{background:radial-gradient(circle at 45% 30%,#0d1d2d,#07121e 70%);border:1px solid #172d42}

/* ---------- Summary card (Current temp + the one way into the chart) ----------
   Dashboard philosophy: only "what's happening right now" — no MIN/AVG/MAX,
   no last-update panel, those moved into the fullscreen chart toolbar. Just
   the big Chart button and the current reading, side by side. */
.temperature-panel{padding:0;border-radius:12px;overflow:hidden;display:flex;flex-direction:column}

.hero{padding:20px 18px;display:flex;align-items:center;gap:16px}
.hero-readout{flex:1;min-width:0;display:flex;flex-direction:column;align-items:center;gap:8px}

/* The Chart button: always visible, roughly the same visual weight as the
   temperature reading next to it (same cyan accent, comparably large) —
   the one and only way to reach historical data now that it no longer
   sits embedded on the page. */
.chart-cta{
  flex:none;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;
  width:clamp(76px,20vw,100px);padding:14px 8px;
  background:rgba(7,201,243,0.08);border:1.5px solid #07c9f3;border-radius:14px;
  color:#07c9f3;cursor:pointer;
}
.chart-cta-icon{width:clamp(26px,7vw,34px);height:clamp(26px,7vw,34px);flex:none;fill:none;stroke:currentColor}
.chart-cta-label{font-size:11px;font-weight:700;letter-spacing:.08em}
.chart-cta:hover{background:rgba(7,201,243,0.16)}
.chart-cta:active{background:rgba(7,201,243,0.24)}

.hero-temp{display:flex;align-items:baseline;justify-content:center;gap:10px;flex-wrap:wrap}
.temp-value{font-size:clamp(40px,11vw,64px);font-weight:700;letter-spacing:-2px;color:#07c9f3;line-height:1}
.temp-delta{font-size:clamp(13px,3vw,15px);color:#00d6ee;font-weight:600}
.hero-meta{display:flex;align-items:center;justify-content:center;gap:8px;flex-wrap:wrap}
.sensor-name{color:#00dcea;font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.object-name{color:#9aabc5;font-size:13px;position:relative;padding-left:12px}
.object-name::before{content:"";position:absolute;left:0;top:50%;translate:0 -50%;width:3px;height:3px;border-radius:50%;background:#3a5470}

/* Tablet/desktop >=600px: a bit more breathing room */
@media(min-width:600px){
 .hero{padding:26px 28px}
}

.chart-panel{height:clamp(460px,66vh,640px);margin-top:8px;border-radius:12px;padding:22px;display:flex;flex-direction:column}

/* Normally just a pass-through flex column matching the chart-panel's own
   layout; becomes the actual Fullscreen API target on demand, at which
   point the chart + range selector go fullscreen together (the range
   selector must stay usable/visible while fullscreen). */
.chart-fullscreen-root{display:flex;flex-direction:column;flex:1;min-height:0;position:relative}
.chart-fullscreen-root.fullscreen{position:fixed;inset:0;flex:none;width:100vw;height:100vh;height:100dvh;padding:4px;background:#07121e;z-index:40}

/* Control strip lives BELOW the chart now — chart is the dominant element,
   this is a secondary, thumb-reachable row underneath it. MIN/AVG/MAX (for
   the currently selected range) sit on the left, range buttons + the
   fullscreen toggle are grouped on the right — the only two groups, so
   space-between keeps them apart regardless of how wide the row is. */
.ranges{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-top:14px;flex:none;flex-wrap:wrap}
.range-controls{display:flex;align-items:center;gap:10px;flex:none}
.range-buttons{display:flex;gap:10px}
.ranges button,.fullscreen-btn,.exit-fullscreen-btn{
  display:flex;align-items:center;justify-content:center;gap:7px;
  height:40px;padding:0 18px;flex:none;white-space:nowrap;
  background:#091725;border:1px solid #263e56;border-radius:8px;
  color:#afc0dc;font-size:13px;font-weight:600;letter-spacing:.02em;cursor:pointer;
}
.ranges .active{border-color:#00cce3;color:#00e5ef;background:#063142}
.fullscreen-btn,.exit-fullscreen-btn{color:#b9c9e6}
.fullscreen-btn svg,.exit-fullscreen-btn svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.fullscreen-btn:hover{border-color:#00cce3;color:#00e5ef}
.exit-fullscreen-btn:hover{border-color:#ff6875;color:#ff8b93}
.empty{text-align:center;padding:100px;color:#8fa1ba}

/* MIN/AVG/MAX for the currently selected range — lives only here, in the
   chart toolbar, never on the bare Dashboard. */
.chart-stats{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;font-size:13px;color:#afc0dc;font-variant-numeric:tabular-nums}
.chart-stat b{color:#e8effa;font-weight:700;letter-spacing:.04em;margin-right:4px}
.chart-stat-sep{color:#3a5470}

/* Fullscreen: SCADA-style floating toolbar. It overlays the chart itself,
   pinned along the top edge, so the chart underneath can still occupy
   almost the entire screen. Semi-transparent + blurred so it stays
   legible without fully hiding the plot behind it; the Y axis is gone and
   X axis labels sit at the bottom, so a top strip never covers either. */
.chart-fullscreen-root.fullscreen .ranges{
  position:absolute;top:14px;left:14px;right:14px;z-index:41;
  margin-top:0;padding:8px 14px;flex:none;
  background:rgba(7,18,30,0.85);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);
  border:1px solid rgba(38,62,86,0.7);border-radius:12px;
  box-shadow:0 8px 24px rgba(0,0,0,0.35);
}

@media(max-width:1100px){.dashboard{max-width:100%}.chart-panel{height:clamp(420px,58vh,560px)}}
@media(max-width:800px){
 .dashboard{padding:16px}.selectors{grid-template-columns:1fr;gap:12px}.chart-panel{height:clamp(260px,64vw,340px);padding:16px}
 /* Narrow screens: collapse the toggle button to icon-only, and shrink the
    stats text, so the row degrades to wrapping instead of overflowing. */
 .fullscreen-btn span,.exit-fullscreen-btn span{display:none}
 .fullscreen-btn,.exit-fullscreen-btn{width:40px;padding:0}
 .ranges{gap:8px}
 .range-buttons{gap:6px}
 .chart-stats{font-size:11px;gap:6px}
 .chart-fullscreen-root.fullscreen .ranges{top:8px;left:8px;right:8px;gap:6px;padding:6px 10px}
}

/* Short landscape phones (~375-430px tall once rotated): trim the floating
   toolbar further to keep the chart close to the 90-95% target without
   shrinking tap targets past comfortable thumb use. */
@media(max-height:430px){
 .chart-fullscreen-root.fullscreen{padding:2px}
 .chart-fullscreen-root.fullscreen .ranges{top:6px;left:6px;right:6px;padding:5px 8px}
 .chart-fullscreen-root.fullscreen .ranges button,
 .chart-fullscreen-root.fullscreen .fullscreen-btn,
 .chart-fullscreen-root.fullscreen .exit-fullscreen-btn{height:36px}
}
</style>
