<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { apiSensorAlarmConfig } from '@/api'
import type { SensorAlarmConfigItem, SensorAlarmConfigUpdate } from '@/types'

const props = defineProps<{
  sensorId: string
  sensorName: string
}>()

const emit = defineEmits<{
  close: []
  saved: []
}>()

const loading = ref(false)
const saving = ref(false)
const error = ref('')

const config = ref<SensorAlarmConfigItem>({
  id: '',
  sensor_id: '',
  high_enabled: true,
  high_temperature: null,
  high_delay: 300,
  low_enabled: true,
  low_temperature: null,
  low_delay: 300,
  offline_enabled: true,
  offline_timeout: 120,
  offline_delay: 300,
  created_at: '',
  updated_at: '',
})

onMounted(async () => {
  loading.value = true
  try {
    const data = await apiSensorAlarmConfig.get(props.sensorId)
    config.value = data
  } catch (e) {
    error.value = 'Nie udało się pobrać konfiguracji alarmów'
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  error.value = ''
  try {
    const update: SensorAlarmConfigUpdate = {
      high_enabled: config.value.high_enabled,
      high_temperature: config.value.high_temperature,
      high_delay: config.value.high_delay,
      low_enabled: config.value.low_enabled,
      low_temperature: config.value.low_temperature,
      low_delay: config.value.low_delay,
      offline_enabled: config.value.offline_enabled,
      offline_timeout: config.value.offline_timeout,
      offline_delay: config.value.offline_delay,
    }
    await apiSensorAlarmConfig.update(props.sensorId, update)
    emit('saved')
    emit('close')
  } catch (e) {
    error.value = 'Nie udało się zapisać konfiguracji'
  } finally {
    saving.value = false
  }
}

const highTempStr = computed({
  get: () => config.value.high_temperature?.toString() ?? '',
  set: (v: string) => {
    const n = parseFloat(v)
    config.value.high_temperature = isNaN(n) ? null : n
  }
})

const lowTempStr = computed({
  get: () => config.value.low_temperature?.toString() ?? '',
  set: (v: string) => {
    const n = parseFloat(v)
    config.value.low_temperature = isNaN(n) ? null : n
  }
})
</script>

<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="alarm-modal">
      <header>
        <h2>⚙ Konfiguracja alarmów</h2>
        <p class="sensor-label">Sensor: <strong>{{ sensorName }}</strong></p>
      </header>

      <div v-if="loading" class="loading">Ładowanie...</div>

      <div v-else class="sections">
        <!-- HIGH TEMPERATURE -->
        <section>
          <h3>Alarm wysokiej temperatury</h3>
          <label class="toggle-row">
            <span>Włączony</span>
            <input type="checkbox" v-model="config.high_enabled" class="switch">
          </label>
          <div class="field-row">
            <label>Temperatura [°C]</label>
            <input type="number" v-model="highTempStr" step="0.1" :disabled="!config.high_enabled">
          </div>
          <div class="field-row">
            <label>Opóźnienie alarmu [min]</label>
            <input type="number" v-model.number="config.high_delay" step="1" min="0" :disabled="!config.high_enabled">
          </div>
        </section>

        <!-- LOW TEMPERATURE -->
        <section>
          <h3>Alarm niskiej temperatury</h3>
          <label class="toggle-row">
            <span>Włączony</span>
            <input type="checkbox" v-model="config.low_enabled" class="switch">
          </label>
          <div class="field-row">
            <label>Temperatura [°C]</label>
            <input type="number" v-model="lowTempStr" step="0.1" :disabled="!config.low_enabled">
          </div>
          <div class="field-row">
            <label>Opóźnienie alarmu [min]</label>
            <input type="number" v-model.number="config.low_delay" step="1" min="0" :disabled="!config.low_enabled">
          </div>
        </section>

        <!-- OFFLINE -->
        <section>
          <h3>Alarm OFFLINE</h3>
          <label class="toggle-row">
            <span>Włączony</span>
            <input type="checkbox" v-model="config.offline_enabled" class="switch">
          </label>
          <div class="field-row">
            <label>Brak komunikacji po [min]</label>
            <input type="number" v-model.number="config.offline_timeout" step="1" min="1" :disabled="!config.offline_enabled">
          </div>
          <div class="field-row">
            <label>Opóźnienie alarmu [min]</label>
            <input type="number" v-model.number="config.offline_delay" step="1" min="0" :disabled="!config.offline_enabled">
          </div>
        </section>
      </div>

      <p v-if="error" class="error">{{ error }}</p>

      <footer>
        <button type="button" @click="$emit('close')" :disabled="saving">Anuluj</button>
        <button type="button" class="primary" @click="save" :disabled="saving || loading">
          {{ saving ? 'Zapisywanie...' : 'Zapisz' }}
        </button>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: grid;
  place-items: center;
  z-index: 10;
}

.alarm-modal {
  width: min(500px, calc(100vw - 32px));
  max-height: 90vh;
  overflow-y: auto;
  padding: 25px;
  background: #0a1827;
  border: 1px solid #26516b;
  border-radius: 9px;
  color: #f1f5ff;
}

.alarm-modal h2 {
  margin: 0 0 4px;
  font-size: 22px;
}

.sensor-label {
  margin: 0 0 18px;
  color: #afbfda;
  font-size: 15px;
}

.sensor-label strong {
  color: #00dde1;
}

.sections {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

section {
  background: #0b1e2d;
  border: 1px solid #162e43;
  border-radius: 7px;
  padding: 16px;
}

section h3 {
  margin: 0 0 12px;
  font-size: 17px;
  color: #00dde1;
}

.toggle-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  cursor: pointer;
  color: #e8f0ff;
}

.toggle-row .switch {
  width: 40px;
  height: 22px;
  appearance: none;
  background: #1a3346;
  border-radius: 11px;
  position: relative;
  cursor: pointer;
  transition: background 0.2s;
  flex-shrink: 0;
}

.toggle-row .switch::before {
  content: '';
  position: absolute;
  top: 3px;
  left: 3px;
  width: 16px;
  height: 16px;
  background: #7a8aa5;
  border-radius: 50%;
  transition: transform 0.2s, background 0.2s;
}

.toggle-row .switch:checked {
  background: #06d8e4;
}

.toggle-row .switch:checked::before {
  transform: translateX(18px);
  background: white;
}

.field-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
}

.field-row label {
  min-width: 160px;
  color: #b3c7e6;
  font-size: 14px;
}

.field-row input {
  flex: 1;
  background: #07121f;
  border: 1px solid #294b68;
  border-radius: 5px;
  color: white;
  padding: 8px;
  font: inherit;
  font-size: 15px;
}

.field-row input:disabled {
  opacity: 0.4;
}

.loading {
  text-align: center;
  padding: 30px;
  color: #afbfda;
}

.error {
  color: #ff3151;
  margin: 12px 0;
}

footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 20px;
}

footer button {
  padding: 9px 20px;
  color: white;
  border: 1px solid #294b68;
  border-radius: 5px;
  background: #102133;
  cursor: pointer;
  font-size: 15px;
}

footer button.primary {
  background: linear-gradient(115deg, #06c7f3, #078de4);
  border-color: #139de5;
}

footer button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
