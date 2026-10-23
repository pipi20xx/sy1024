<script setup lang="ts">
import { useConfirm } from '@/composables'

const { show, options, onConfirm, onCancel } = useConfirm()
</script>

<template>
  <v-dialog v-model="show" max-width="460">
    <v-card rounded="xl">
      <v-card-title class="text-h6 d-flex align-center">
        <v-icon v-if="options.confirmColor === 'error'" icon="mdi-alert-circle" class="mr-2" />
        <v-icon v-else-if="options.confirmColor === 'warning'" icon="mdi-alert" class="mr-2" />
        <v-icon v-else icon="mdi-help-circle" class="mr-2 text-accent-gold" />
        {{ options.title }}
        <v-spacer />
        <v-btn size="small" variant="text" icon="mdi-close" @click="onCancel" />
      </v-card-title>
      <v-card-text class="text-body-1 pre-line">
        {{ options.content }}
      </v-card-text>
      <v-card-actions>
        <v-spacer />
        <v-btn variant="tonal" color="grey" prepend-icon="mdi-close" @click="onCancel">{{ options.cancelText }}</v-btn>
        <v-btn :color="options.confirmColor || 'primary'" variant="tonal" :prepend-icon="options.confirmColor === 'error' ? 'mdi-delete' : 'mdi-check'" @click="onConfirm">{{ options.confirmText }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>
