<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useObjectsStore } from "@/stores/objects";
import { useSensorsStore } from "@/stores/sensors";
import { useAlarmsStore } from "@/stores/alarms";
import { apiAlarmConfigs } from "@/api";
import type { AlarmConfigItem, ChartRange, MeasurementItem } from "@/types";
import TemperatureChart from "@/components/TemperatureChart.vue";

const objectsStore=useObjectsStore(), sensorsStore=useSensorsStore(), alarmsStore=useAlarmsStore();
const selectedObjectId=ref(""), selectedSensorId=ref(""), range=ref<ChartRange>("LIVE");
const alarmConfigs=ref<AlarmConfigItem[]>([]);
const isChartFullscreen=ref(false);

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
  range.value="LIVE";
  sensorsStore.selectSensor(sensorsStore.sensors.find(x=>x.id===selectedSensorId.value)||null);
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
  <div class="selectors"><label>Obiekt:<select v-model="selectedObjectId"><option value="">Wybierz obiekt</option><option v-for="object in objectsStore.activeObjects" :key="object.id" :value="object.id">{{object.name}}</option></select></label><label>Czujnik:<select v-model="selectedSensorId" @change="pickSensor" :disabled="!selectedObjectId"><option value="">Wybierz sensor</option><option v-for="item in sensorsStore.sensors" :key="item.id" :value="item.id">{{item.name}}</option></select></label></div>
  <template v-if="sensor">
   <article class="temperature-panel">
    <div class="panel-grid">
     <div class="stat-card stat-primary">
      <div class="sensor-name"><span>{{sensor.name}}</span><strong>{{selectedObject?.name}}</strong></div>
      <div class="temp-row"><span class="temp-value">{{temperature(sensor.current_temperature)}}</span><small class="temp-delta">↓ 0.3°</small></div>
     </div>
     <div class="stat-trio">
      <div class="stat-card stat-min"><label>MIN</label><b>{{temperature(stats.min)}}</b><span>{{date(readings[0]?.received_at)}}</span></div>
      <div class="stat-card stat-max"><label>MAX</label><b>{{temperature(stats.max)}}</b><span>{{date(readings[readings.length-1]?.received_at)}}</span></div>
      <div class="stat-card stat-avg"><label>AVERAGE</label><b>{{temperature(stats.avg)}}</b></div>
     </div>
     <div class="stat-card stat-updated"><label>OSTATNIA AKTUALIZACJA</label><b>{{date(sensor.last_message_at)}}</b></div>
    </div>
   </article>
   <article class="chart-panel">
    <div ref="fullscreenRoot" class="chart-fullscreen-root" :class="{fullscreen:isChartFullscreen}">
     <TemperatureChart
       v-if="sensor"
       :sensor="sensor"
       :readings="readings"
       :high-threshold="highThreshold"
       :low-threshold="lowThreshold"
       :alarms="sensorAlarms"
       :active-alarm-label="activeAlarmLabel"
       :online="online()"
       :loading="sensorsStore.rangeLoading"
     />
     <div class="ranges">
      <div class="range-buttons">
       <button v-for="item in (['LIVE','1H','24H','7D'] as ChartRange[])" :key="item" :class="{active:range===item}" @click="applyRange(item)">{{item}}</button>
      </div>
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

/* ---------- Summary panel (Current temp | Min | Max | Average | Last update) ---------- */
.temperature-panel{padding:26px 28px}
.panel-grid{display:grid;gap:26px;align-items:stretch}
.stat-card{display:flex;flex-direction:column;justify-content:center;gap:6px;min-width:0}
.stat-card label{font-size:clamp(11px,.95vw,13px);color:#99aac3;text-transform:uppercase;letter-spacing:.04em}
.stat-card b{font-size:clamp(17px,1.6vw,20px);color:#e8effa;font-weight:600;overflow-wrap:break-word}
.stat-card>span{font-size:clamp(12px,1vw,14px);color:#9aabc5}
.stat-min,.stat-max{border-right:1px solid #1d344a;padding-right:20px}

.stat-primary{gap:12px}
.sensor-name{display:flex;flex-direction:column;gap:6px}
.sensor-name span{color:#00dcea;font-size:clamp(12px,1vw,14px);font-weight:600;text-transform:uppercase}
.sensor-name strong{font-size:clamp(15px,1.3vw,18px);color:#e8effa;font-weight:600}
.temp-row{display:flex;align-items:baseline;gap:14px;flex-wrap:wrap}
.temp-value{font-size:clamp(46px,6vw,92px);font-weight:700;letter-spacing:-3px;color:#07c9f3;line-height:1}
.temp-delta{font-size:clamp(14px,1.3vw,20px);color:#00d6ee}

.stat-trio{display:contents}

/* Desktop >=1280px: one row, Current Temp is the wide/dominant column, the rest equal */
@media(min-width:1280px){
 .panel-grid{grid-template-columns:minmax(280px,1.6fr) repeat(4,minmax(0,1fr));grid-template-areas:"temp min max avg updated"}
}
.stat-primary{grid-area:temp}
.stat-min{grid-area:min}
.stat-max{grid-area:max}
.stat-avg{grid-area:avg}
.stat-updated{grid-area:updated}

/* Tablet 768-1279px: temp full width, min/max/avg as an auto-fit row, update below */
@media(min-width:768px) and (max-width:1279px){
 .panel-grid{grid-template-columns:1fr;grid-template-areas:"temp" "trio" "updated"}
 .stat-trio{display:grid;grid-area:trio;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:22px}
 .stat-trio>.stat-card{grid-area:auto}
 .stat-primary{flex-direction:row;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:16px 28px}
 .sensor-name,.temp-row{flex:none}
}

/* Mobile <768px: full card redesign, nothing overlaps, nothing truncates */
@media(max-width:767px){
 .temperature-panel{padding:18px}
 .panel-grid{grid-template-columns:1fr;grid-template-areas:"temp" "trio" "updated";gap:16px}
 .stat-trio{display:grid;grid-area:trio;grid-template-columns:repeat(auto-fit,minmax(84px,1fr));gap:10px}
 .stat-trio>.stat-card{grid-area:auto}
 .stat-card{background:#0b1c2c;border:1px solid #1d344a;border-radius:10px;padding:12px 12px}
 .stat-min,.stat-max{border-right:0}
 .stat-primary{align-items:center;text-align:center;padding:22px 16px}
 .temp-row{justify-content:center}
}

.chart-panel{height:clamp(460px,66vh,640px);margin-top:8px;border-radius:12px;padding:22px;display:flex;flex-direction:column}

/* Normally just a pass-through flex column matching the chart-panel's own
   layout; becomes the actual Fullscreen API target on demand, at which
   point the chart + range selector go fullscreen together (the range
   selector must stay usable/visible while fullscreen). */
.chart-fullscreen-root{display:flex;flex-direction:column;flex:1;min-height:0;position:relative}
.chart-fullscreen-root.fullscreen{position:fixed;inset:0;flex:none;width:100vw;height:100vh;height:100dvh;padding:6px 10px 6px;background:#07121e;z-index:40}

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
.fullscreen-btn,.exit-fullscreen-btn{color:#b9c9e6}
.fullscreen-btn svg,.exit-fullscreen-btn svg{width:15px;height:15px;fill:none;stroke:currentColor;stroke-width:2;stroke-linecap:round;stroke-linejoin:round}
.fullscreen-btn:hover{border-color:#00cce3;color:#00e5ef}
.exit-fullscreen-btn:hover{border-color:#ff6875;color:#ff8b93}
.empty{text-align:center;padding:100px;color:#8fa1ba}

/* Fullscreen toolbar: ONE row pinned to the bottom, right-aligned — range
   buttons, a fixed spacer, then Exit Fullscreen at the far right. */
.chart-fullscreen-root.fullscreen .ranges{margin-top:0;padding:4px 0;justify-content:flex-end;flex:none}
.chart-fullscreen-root.fullscreen .toolbar-spacer{width:18px;flex:none}

@media(max-width:1100px){.dashboard{max-width:100%}.chart-panel{height:clamp(420px,58vh,560px)}}
@media(max-width:800px){
 .dashboard{padding:16px}.selectors{grid-template-columns:1fr;gap:12px}.chart-panel{height:480px;padding:16px}
 /* Narrow screens: collapse the toggle button to icon-only so the row
    never wraps or scrolls, in both normal and fullscreen mode. */
 .fullscreen-btn span,.exit-fullscreen-btn span{display:none}
 .fullscreen-btn,.exit-fullscreen-btn{width:40px;padding:0}
 .ranges{gap:6px}
 .range-buttons{gap:6px}
 .chart-fullscreen-root.fullscreen .toolbar-spacer{width:14px}
}

/* Short landscape phones (~375-430px tall once rotated): trim the toolbar
   further to keep the chart close to the 90-95% target without shrinking
   tap targets past comfortable thumb use. */
@media(max-height:430px){
 .chart-fullscreen-root.fullscreen{padding:4px 8px 4px}
 .chart-fullscreen-root.fullscreen .ranges{padding:2px 0}
 .chart-fullscreen-root.fullscreen .ranges button,
 .chart-fullscreen-root.fullscreen .fullscreen-btn,
 .chart-fullscreen-root.fullscreen .exit-fullscreen-btn{height:36px}
}
</style>
