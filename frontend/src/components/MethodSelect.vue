<script setup lang="ts">
import { methods } from '../api/client'
defineProps<{modelValue:string}>()
defineEmits<{ 'update:modelValue':[value:string] }>()
</script>
<template><el-select :model-value="modelValue" aria-label="增强算法" @update:model-value="$emit('update:modelValue',$event)"><el-option v-for="m in methods" :key="m.value" :label="m.label" :value="m.value"/></el-select></template>
