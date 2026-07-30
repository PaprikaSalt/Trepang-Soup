<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    name: string;
    color?: string;
    size?: "small" | "medium" | "large";
    online?: boolean;
  }>(),
  {
    color: "#d7a95b",
    size: "medium",
    online: true,
  },
);

const initial = computed(() => props.name.trim().slice(0, 1).toUpperCase());
</script>

<template>
  <span
    class="player-avatar"
    :class="[`player-avatar--${size}`, { 'player-avatar--offline': !online }]"
    :style="{ '--avatar-color': color }"
    :title="name"
  >
    {{ initial }}
    <i v-if="online" aria-label="在线"></i>
  </span>
</template>
