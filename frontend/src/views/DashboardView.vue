<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
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

// Alternative chart theme toggle — lets the two chart looks be compared
// side by side before picking a default. Persisted so a reload doesn't
// silently reset a tester's choice back to classic.
type ChartTheme = "classic" | "scada";
const CHART_THEME_KEY = "frigocore-chart-theme";
const chartTheme = ref<ChartTheme>(
  (localStorage.getItem(CHART_THEME_KEY) as ChartTheme | null) === "scada" ? "scada" : "classic"
);
function toggleChartTheme() {
  chartTheme.value = chartTheme.value === "classic" ? "scada" : "classic";
  localStorage.setItem(CHART_THEME_KEY, chartTheme.value);
}

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
  if (isChartFullscreen.value) requestLandscape();
  else releaseOrientation();
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
    // reality via the fullscreenchange listener either way.
  }
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
function date(value:string|null|undefined){return value?new Date(value).toLocaleString("pl-PL"):"—"}
function time(value:string|null|undefined){return value?new Date(value).toLocaleTimeString("pl-PL",{hour:"2-digit",minute:"2-digit"}):"—"}
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
     <div class="hero-temp"><span class="temp-value">{{temperature(sensor.current_temperature)}}</span><span class="temp-delta">↓ 0.3°</span></div>
     <div class="hero-meta"><span class="sensor-name">{{sensor.name}}</span><span class="object-name">{{selectedObject?.name}}</span></div>
    </div>
    <div class="stats-row">
     <div class="stat">
      <svg class="stat-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M6 13l6 6 6-6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <div class="stat-body">
       <span class="stat-label">MIN</span>
       <span class="stat-value">{{temperature(stats.min)}}</span>
       <span class="stat-time">{{time(readings[0]?.received_at)}}</span>
      </div>
     </div>
     <span class="stat-sep" aria-hidden="true"></span>
     <div class="stat">
      <svg class="stat-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12c2-4 4 4 6 0s4-4 6 0 4 4 4 0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <div class="stat-body">
       <span class="stat-label">AVG</span>
       <span class="stat-value">{{temperature(stats.avg)}}</span>
      </div>
     </div>
     <span class="stat-sep" aria-hidden="true"></span>
     <div class="stat">
      <svg class="stat-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M6 11l6-6 6 6" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      <div class="stat-body">
       <span class="stat-label">MAX</span>
       <span class="stat-value">{{temperature(stats.max)}}</span>
       <span class="stat-time">{{time(readings[readings.length-1]?.received_at)}}</span>
      </div>
     </div>
    </div>
    <div class="status-bar">
     <svg class="clock-icon" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><path d="M12 7v5l3 3" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
     <span class="status-label">Ostatnia aktualizacja</span>
     <span class="status-value">{{date(sensor.last_message_at)}}</span>
    </div>
   </article>
   <article class="chart-panel">
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
       :theme="chartTheme"
     />
     <div class="ranges">
      <div class="range-buttons">
       <button v-for="item in (['LIVE','1H','24H','7D'] as ChartRange[])" :key="item" :class="{active:range===item}" @click="applyRange(item)">{{item}}</button>
      </div>
      <button
        class="theme-toggle-btn"
        type="button"
        :aria-label="chartTheme==='scada' ? 'Switch to classic chart theme' : 'Switch to SCADA chart theme'"
        :title="chartTheme==='scada' ? 'Classic theme' : 'SCADA theme'"
        @click="toggleChartTheme"
      >
       <svg viewBox="0 0 24 24"><path d="M12 3v2m0 14v2M5 12H3m18 0h-2m-1.6-6.4-1.4 1.4M7 17l-1.4 1.4M18.4 18.4 17 17M7 7 5.6 5.6" /><circle cx="12" cy="12" r="4" /></svg>
       <span>{{chartTheme==='scada' ? 'SCADA' : 'Classic'}}</span>
      </button>
      <button v-if="!isChartFullscreen" class="fullscreen-btn" type="button" aria-label="Fullscreen" @click="toggleFullscreen">
       <svg viewBox="0 0 24 24"><path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5" /></svg>
       <span>Fullscreen</span>
      </button>
      <template v-else>
       <span class="toolbar-spacer" aria-hidden="true"></span>
       <button class="exit-fullscreen-btn" type="button" aria-label="Exit fullscreen" @click="toggleFullscreen">
        <svg viewBox="0 0 24 24"><path d="M3 8V3h5M21 8V3h-5M3 16v5h5M21 16v5h-5" /></svg>
        <span>Exit Fullscreen</span>
       </button>
      </template>
     </div>
    </div>
   </article>
  </template><div v-else class="empty">Wybierz obiekt i sensor, aby zobaczyć dane.</div>
 </section>
</template>
<style scoped>
.dashboard{padding:21px 25px 10px;max-width:1280px;margin:auto}.selectors{display:grid;grid-template-columns:405px 388px 1fr;gap:25px;align-items:end;margin-bottom:21px}.selectors label{font-size:14px;color:#aab9cf;display:grid;gap:8px}.selectors select{appearance:none;height:48px;border:1px solid #2b4b67;border-radius:7px;background:#081421 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath d='m1 1 5 5 5-5' fill='none' stroke='%23b8c9e8' stroke-width='2'/%3E%3C/svg%3E") no-repeat calc(100% - 17px) center;color:#e8effa;font-size:17px;padding:0 48px 0 18px}.temperature-panel,.chart-panel{background:radial-gradient(circle at 45% 30%,#0d1d2d,#07121e 70%);border:1px solid #172d42}

/* ---------- Summary card (Current temp / Min-Avg-Max / Last update) ----------
   Mobile-first: one card, three sections (hero, stats row, status bar), no
   nested cards — sections are separated by spacing/background, not borders,
   and stat items are divided by a single hairline rather than boxed. Sizes
   scale up via clamp() and two min-width breakpoints reuse the same markup. */
.temperature-panel{padding:0;border-radius:12px;overflow:hidden;display:flex;flex-direction:column}

.hero{padding:20px 20px 16px;text-align:center;display:flex;flex-direction:column;align-items:center;gap:8px}
.hero-temp{display:flex;align-items:baseline;justify-content:center;gap:10px;flex-wrap:wrap}
.temp-value{font-size:clamp(40px,11vw,64px);font-weight:700;letter-spacing:-2px;color:#07c9f3;line-height:1}
.temp-delta{font-size:clamp(13px,3vw,15px);color:#00d6ee;font-weight:600}
.hero-meta{display:flex;align-items:center;justify-content:center;gap:8px;flex-wrap:wrap}
.sensor-name{color:#00dcea;font-size:13px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.object-name{color:#9aabc5;font-size:13px;position:relative;padding-left:12px}
.object-name::before{content:"";position:absolute;left:0;top:50%;translate:0 -50%;width:3px;height:3px;border-radius:50%;background:#3a5470}

.stats-row{display:flex;align-items:stretch;justify-content:space-between;gap:4px;padding:14px 16px;margin:0 12px;border-top:1px solid #172d42}
.stat{display:flex;align-items:center;gap:8px;min-width:0;flex:1;justify-content:center}
.stat-icon{width:18px;height:18px;color:#4f7396;flex:none}
.stat-body{display:flex;flex-direction:column;gap:1px;min-width:0}
.stat-label{font-size:10px;color:#7d90ac;text-transform:uppercase;letter-spacing:.05em}
.stat-value{font-size:clamp(14px,4vw,16px);color:#e8effa;font-weight:600;white-space:nowrap}
.stat-time{font-size:11px;color:#7d90ac}
.stat-sep{width:1px;flex:none;background:#172d42;align-self:stretch;margin:2px 0}

.status-bar{display:flex;align-items:center;gap:8px;padding:10px 20px;background:#0a1826;font-size:12px;color:#9aabc5;flex-wrap:wrap}
.clock-icon{width:14px;height:14px;color:#4f7396;flex:none}
.status-value{color:#c6d3e8;font-weight:600}

/* Tablet/desktop >=600px: a bit more breathing room, hero and stats slightly larger */
@media(min-width:600px){
 .hero{padding:26px 28px 20px;gap:10px}
 .stats-row{padding:16px 24px;margin:0 16px}
 .stat{gap:10px}
 .stat-icon{width:20px;height:20px}
 .status-bar{padding:12px 28px}
}

.chart-panel{height:clamp(460px,66vh,640px);margin-top:8px;border-radius:12px;padding:22px;display:flex;flex-direction:column}

/* Normally just a pass-through flex column matching the chart-panel's own
   layout; becomes the actual Fullscreen API target on demand, at which
   point the chart + range selector go fullscreen together (the range
   selector must stay usable/visible while fullscreen). */
.chart-fullscreen-root{display:flex;flex-direction:column;flex:1;min-height:0;position:relative}
.chart-fullscreen-root.fullscreen{position:fixed;inset:0;flex:none;width:100vw;height:100vh;height:100dvh;padding:4px;background:#07121e;z-index:40}

/* Control strip lives BELOW the chart now — chart is the dominant element,
   controls are a secondary, thumb-reachable row underneath it. One shared
   pill style for range buttons and the fullscreen/exit toggle keeps them
   visually identical; only alignment changes between normal (centered)
   and fullscreen (right-aligned) mode. */
.ranges{display:flex;align-items:center;justify-content:center;gap:10px;margin-top:14px;flex:none}
.range-buttons{display:flex;gap:10px}
.ranges button,.fullscreen-btn,.exit-fullscreen-btn{
  display:flex;align-items:center;justify-content:center;gap:7px;
  height:40px;padding:0 18px;flex:none;white-space:nowrap;
  background:#091725;border:1px solid #263e56;border-radius:8px;
  color:#afc0dc;font-size:13px;font-weight:600;letter-spacing:.02em;cursor:pointer;
}
.ranges .active{border-color:#00cce3;color:#00e5ef;background:#063142}
.fullscreen-btn,.exit-fullscreen-btn,.theme-toggle-btn{color:#b9c9e6}
.fullscreen-btn svg,.exit-fullscreen-btn svg,.theme-toggle-btn svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.fullscreen-btn:hover{border-color:#00cce3;color:#00e5ef}
.exit-fullscreen-btn:hover{border-color:#ff6875;color:#ff8b93}
.theme-toggle-btn:hover{border-color:#00cce3;color:#00e5ef}
.empty{text-align:center;padding:100px;color:#8fa1ba}

/* Fullscreen: SCADA-style floating toolbar. It overlays the chart itself,
   pinned to the top-right corner, so the chart underneath can occupy
   almost the entire screen. Semi-transparent + blurred so it stays
   legible without fully hiding the plot behind it; the Y axis lives on
   the left and X axis labels sit at the bottom, so a top-right pill
   never covers either. */
.chart-fullscreen-root.fullscreen .ranges{
  position:absolute;top:14px;right:14px;z-index:41;
  margin-top:0;padding:6px 8px;flex:none;justify-content:flex-end;
  background:rgba(7,18,30,0.8);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);
  border:1px solid rgba(38,62,86,0.7);border-radius:12px;
  box-shadow:0 8px 24px rgba(0,0,0,0.35);
}
.chart-fullscreen-root.fullscreen .toolbar-spacer{display:none}

@media(max-width:1100px){.dashboard{max-width:100%}.chart-panel{height:clamp(420px,58vh,560px)}}
@media(max-width:800px){
 .dashboard{padding:16px}.selectors{grid-template-columns:1fr;gap:12px}.chart-panel{height:clamp(260px,64vw,340px);padding:16px}
 /* Narrow screens: collapse the toggle button to icon-only so the row
    never wraps or scrolls, in both normal and fullscreen mode. */
 .fullscreen-btn span,.exit-fullscreen-btn span,.theme-toggle-btn span{display:none}
 .fullscreen-btn,.exit-fullscreen-btn,.theme-toggle-btn{width:40px;padding:0}
 .ranges{gap:6px}
 .range-buttons{gap:6px}
 .chart-fullscreen-root.fullscreen .ranges{top:8px;right:8px;gap:6px;padding:5px 6px}
}

/* Short landscape phones (~375-430px tall once rotated): trim the floating
   toolbar further to keep the chart close to the 90-95% target without
   shrinking tap targets past comfortable thumb use. */
@media(max-height:430px){
 .chart-fullscreen-root.fullscreen{padding:2px}
 .chart-fullscreen-root.fullscreen .ranges{top:6px;right:6px;padding:4px 5px}
 .chart-fullscreen-root.fullscreen .ranges button,
 .chart-fullscreen-root.fullscreen .fullscreen-btn,
 .chart-fullscreen-root.fullscreen .exit-fullscreen-btn{height:36px}
}
</style>
