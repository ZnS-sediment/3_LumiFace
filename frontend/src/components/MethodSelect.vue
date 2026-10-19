<script setup lang="ts">
import { computed } from 'vue'
import { methods } from '../api/client'
const props = defineProps<{ modelValue: string }>()
defineEmits<{ 'update:modelValue': [value: string] }>()
const selectedMethod = computed(() => methods.find((method) => method.value === props.modelValue))
</script>
<template>
  <div class="method-select">
    <el-select
      :model-value="modelValue"
      aria-label="增强算法"
      @update:model-value="$emit('update:modelValue', $event)"
      ><el-option v-for="m in methods" :key="m.value" :label="m.label" :value="m.value"
    /></el-select>
    <p class="method-hint">{{ selectedMethod?.description }}</p>
  </div>
</template>
