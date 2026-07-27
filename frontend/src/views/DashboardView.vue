<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useObjectsStore } from "@/stores/objects";
import { useSensorsStore } from "@/stores/sensors";
import { useAlarmsStore } from "@/stores/alarms";
import { apiAlarmConfigs } from "@/api";
import type { AlarmConfigItem, ChartRange, MeasurementItem } from "@/types";
import TemperatureChart from "@/components/TemperatureChart.vue";

const objectsStore=useObjectsStore(), sensorsStore=useSensorsStore(), alarmsStore=useAlarmsStore();
const selectedObjectId=ref(""), selectedSensorId=ref(""), range=ref<ChartRange>("LIVE");
const customStart=ref(""), customEnd=ref("");
const alarmConfigs=ref<AlarmConfigItem[]>([]);

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
  if(r!=="CUSTOM") sensorsStore.fetchMeasurementsForRange(r);
}
function applyCustomRange(){
  if(!customStart.value||!customEnd.value) return;
  sensorsStore.fetchMeasurementsForRange("CUSTOM", new Date(customStart.value), new Date(customEnd.value));
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

onMounted(async()=>{await objectsStore.fetchObjects();if(objectsStore.activeObjects[0]){selectedObjectId.value=objectsStore.activeObjects[0].id;pickObject()}});
watch(selectedObjectId,pickObject);
</script>
<template>
 <section class="dashboard">
  <div class="selectors"><label>WYBÓR OBIEKTU<select v-model="selectedObjectId"><option value="">Wybierz obiekt</option><option v-for="object in objectsStore.activeObjects" :key="object.id" :value="object.id">{{object.name}}</option></select></label><label>WYBÓR SENSORĄ<select v-model="selectedSensorId" @change="pickSensor" :disabled="!selectedObjectId"><option value="">Wybierz sensor</option><option v-for="item in sensorsStore.sensors" :key="item.id" :value="item.id">{{item.name}}</option></select></label><button class="expand" aria-label="Powiększ">↗</button></div>
  <template v-if="sensor">
   <article class="temperature-panel">
    <div class="panel-grid">
     <div class="stat-card stat-primary">
      <div class="sensor-name"><span>{{sensor.name}}</span><strong>{{selectedObject?.name}}</strong></div>
      <div class="temp-row"><span class="temp-value">{{temperature(sensor.current_temperature)}}</span><small class="temp-delta">↓ 0.3°</small></div>
      <em class="status-badge" :class="{off:!online()}">{{online()?"ONLINE":"OFFLINE"}}</em>
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
    <div class="chart-title">HISTORICAL RANGE <span>{{sensor.name}} ({{selectedObject?.name}})</span><button>↗</button></div>
    <div class="ranges">
     <button v-for="item in (['LIVE','1H','6H','24H','7D','CUSTOM'] as ChartRange[])" :key="item" :class="{active:range===item}" @click="applyRange(item)">{{item}}</button>
    </div>
    <div v-if="range==='CUSTOM'" class="custom-range">
     <input type="datetime-local" v-model="customStart" />
     <span>—</span>
     <input type="datetime-local" v-model="customEnd" />
     <button class="apply" @click="applyCustomRange" :disabled="!customStart||!customEnd">Zastosuj</button>
    </div>
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
   </article>
  </template><div v-else class="empty">Wybierz obiekt i sensor, aby zobaczyć dane.</div>
 </section>
</template>
<style scoped>
.dashboard{padding:21px 25px 10px;max-width:1280px;margin:auto}.selectors{display:grid;grid-template-columns:405px 388px 1fr;gap:25px;align-items:end;margin-bottom:21px}.selectors label{font-size:14px;color:#aab9cf;display:grid;gap:8px}.selectors select{appearance:none;height:48px;border:1px solid #2b4b67;border-radius:7px;background:#081421 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8'%3E%3Cpath d='m1 1 5 5 5-5' fill='none' stroke='%23b8c9e8' stroke-width='2'/%3E%3C/svg%3E") no-repeat calc(100% - 17px) center;color:#e8effa;font-size:17px;padding:0 48px 0 18px}.expand{justify-self:end;width:50px;height:48px;background:#081421;border:1px solid #29455e;border-radius:8px;color:#b9c9e6;font-size:24px}.temperature-panel,.chart-panel{background:radial-gradient(circle at 45% 30%,#0d1d2d,#07121e 70%);border:1px solid #172d42}

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
.status-badge{align-self:flex-start;font-style:normal;color:#00f184;border:1px solid #007c47;border-radius:4px;padding:4px 12px;font-size:12px}
.status-badge.off{color:#ff6875;border-color:#8d2637}

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
 .stat-trio{display:grid;grid-area:trio;grid-template-columns:repeat(auto-fit,minmax(96px,1fr));gap:12px}
 .stat-trio>.stat-card{grid-area:auto}
 .stat-card{background:#0b1c2c;border:1px solid #1d344a;border-radius:10px;padding:14px 16px}
 .stat-min,.stat-max{border-right:0}
 .stat-primary{align-items:center;text-align:center;padding:22px 16px}
 .temp-row{justify-content:center}
}

.chart-panel{height:clamp(460px,66vh,640px);margin-top:8px;border-radius:12px;padding:22px;display:flex;flex-direction:column}
.chart-title{font-size:20px;flex:none}.chart-title span{font-size:14px;color:#8fa1ba;margin-left:28px}.chart-title button{float:right;background:#081421;border:1px solid #29455e;border-radius:7px;color:#b9c9e6;width:34px;height:34px;font-size:17px}
.ranges{display:flex;gap:8px;margin-top:20px;flex:none}.ranges button{background:#091725;border:1px solid #263e56;border-radius:5px;color:#afc0dc;font-size:14px;padding:9px 16px}.ranges .active{border-color:#00cce3;color:#00e5ef;background:#063142}
.custom-range{display:flex;align-items:center;gap:10px;margin-top:12px;flex:none}.custom-range span{color:#8fa1ba}.custom-range input{background:#07121f;border:1px solid #294b68;border-radius:5px;color:#e8effa;padding:7px 10px;font-size:13px}.custom-range .apply{background:#063142;border:1px solid #00cce3;color:#00e5ef;border-radius:5px;padding:7px 14px;font-size:13px}.custom-range .apply:disabled{opacity:.4}
.no-chart,.empty{text-align:center;padding:100px;color:#8fa1ba}
@media(max-width:1100px){.dashboard{max-width:100%}.chart-panel{height:clamp(420px,58vh,560px)}}
@media(max-width:800px){.dashboard{padding:16px}.selectors{grid-template-columns:1fr;gap:12px}.expand{display:none}.chart-panel{height:480px;padding:16px}.chart-title span{display:block;margin:8px 0}.ranges{overflow:auto}.ranges button{padding:7px 10px}.custom-range{flex-wrap:wrap}}
</style>
