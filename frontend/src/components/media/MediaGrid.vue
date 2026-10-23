<script setup lang="ts">
import { useUiStore } from '@/stores'
import type { ItemSummary } from '@/types'
import MediaCard from './MediaCard.vue'

defineProps<{ items: ItemSummary[] }>()

const uiStore = useUiStore()
</script>

<template>
  <v-container fluid class="pa-0">
    <v-row>
      <v-col
        v-for="item in items"
        :key="item.id"
        v-bind="uiStore.gridColProps"
      >
        <MediaCard :item="item" />
      </v-col>
    </v-row>
  </v-container>
</template>
