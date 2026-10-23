<script setup lang="ts">
import { ref } from 'vue'

defineOptions({ inheritAttrs: false })

const show = ref(false)
</script>

<template>
  <v-text-field
    v-bind="$attrs"
    :type="show ? 'text' : 'password'"
    :append-inner-icon="show ? 'mdi-eye-off' : 'mdi-eye'"
    @click:append-inner="show = !show"
  />
</template>
