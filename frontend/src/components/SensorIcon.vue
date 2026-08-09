<script setup lang="ts">
/**
 * Sensor icon library for refrigeration/HVAC monitoring.
 *
 * The identifier is persisted per sensor (Sensor.icon), so the admin panel
 * and the client dashboard always draw the same symbol. Adding an icon here
 * is enough — the backend validates the identifier as a slug rather than
 * against a fixed list, so no backend change is needed.
 */
import { computed } from "vue";
import { SENSOR_ICONS, DEFAULT_SENSOR_ICON } from "@/utils/sensorIcons";

const props = withDefaults(
  defineProps<{ icon?: string | null; size?: number | string }>(),
  { icon: DEFAULT_SENSOR_ICON, size: 20 },
);

const paths = computed(
  () => SENSOR_ICONS[props.icon || DEFAULT_SENSOR_ICON]?.paths
    ?? SENSOR_ICONS[DEFAULT_SENSOR_ICON].paths,
);
</script>

<template>
  <svg
    class="sensor-icon"
    viewBox="0 0 24 24"
    :width="size"
    :height="size"
    aria-hidden="true"
  >
    <path v-for="(d, i) in paths" :key="i" :d="d" />
  </svg>
</template>

<style scoped>
.sensor-icon {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
  flex: none;
}
</style>
