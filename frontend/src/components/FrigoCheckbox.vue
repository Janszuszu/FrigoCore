<script setup lang="ts">
type CheckboxValue = boolean | 'indeterminate'

const props = defineProps<{
  modelValue: CheckboxValue
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
}>()

function onClick() {
  // indeterminate click always resolves to checked
  emit('update:modelValue', props.modelValue === true ? false : true)
}
</script>

<template>
  <span
    class="frigo-checkbox"
    :class="{
      checked: modelValue === true,
      indeterminate: modelValue === 'indeterminate',
    }"
    role="checkbox"
    :aria-checked="modelValue === true ? 'true' : modelValue === 'indeterminate' ? 'mixed' : 'false'"
    tabindex="0"
    @click="onClick"
    @keydown.space.prevent="onClick"
    @keydown.enter.prevent="onClick"
  >
    <svg v-if="modelValue === true" viewBox="0 0 24 24" class="check-icon">
      <path d="M5 13l4 4L19 7" />
    </svg>
    <span v-else-if="modelValue === 'indeterminate'" class="indeterminate-bar"></span>
  </span>
</template>

<style scoped>
.frigo-checkbox {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 21px;
  height: 21px;
  border: 2px solid #06d8e4;
  border-radius: 4px;
  background: transparent;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
  flex-shrink: 0;
  outline: none;
}

.frigo-checkbox:hover {
  border-color: #4be6ef;
}

.frigo-checkbox.checked {
  background: #06d8e4;
  border-color: #06d8e4;
}

.frigo-checkbox.indeterminate {
  border-color: #06d8e4;
}

.check-icon {
  width: 16px;
  height: 16px;
  fill: none;
  stroke: white;
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.indeterminate-bar {
  width: 10px;
  height: 3px;
  background: #06d8e4;
  border-radius: 2px;
}
</style>
