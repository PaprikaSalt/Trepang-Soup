<script setup lang="ts">
import { RouterView } from "vue-router";
</script>

<template>
  <div class="app-shell">
    <div class="ambient ambient--left" aria-hidden="true"></div>
    <div class="ambient ambient--right" aria-hidden="true"></div>
    <div class="noise-layer" aria-hidden="true"></div>
    <RouterView v-slot="{ Component, route }">
      <!-- out-in guarantees the previous page is gone before the next page begins entering. -->
      <Transition name="page-shift" mode="out-in" :duration="{ enter: 470, leave: 180 }">
        <component :is="Component" :key="route.fullPath" />
      </Transition>
    </RouterView>
  </div>
</template>
