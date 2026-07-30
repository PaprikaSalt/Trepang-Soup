<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

const props = withDefaults(
  defineProps<{
    roomCode?: string;
    compact?: boolean;
    showHistory?: boolean;
  }>(),
  {
    roomCode: "",
    compact: false,
    showHistory: true,
  },
);

const route = useRoute();
const router = useRouter();
const isHome = computed(() => route.name === "home");

function goHome(): void {
  void router.push("/");
}
</script>

<template>
  <header class="app-header" :class="{ 'app-header--compact': props.compact }">
    <button class="brand-button" type="button" aria-label="返回首页" @click="goHome">
      <span class="brand-mark" aria-hidden="true">
        <span class="brand-mark__shell"></span>
        <span class="brand-mark__head"></span>
      </span>
      <span class="brand-copy">
        <strong>Trepang Soup</strong>
        <small>海龟汤</small>
      </span>
    </button>

    <div v-if="roomCode" class="room-code-chip">
      <span>房间</span>
      <strong>{{ roomCode }}</strong>
    </div>

    <nav class="header-actions" aria-label="应用导航">
      <slot name="actions"></slot>
      <button
        v-if="!isHome"
        class="text-button"
        type="button"
        @click="goHome"
      >
        回到首页
      </button>
      <button
        v-if="showHistory"
        class="icon-button"
        type="button"
        title="本地对局"
        @click="router.push('/history')"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3L4.5 8.9" />
          <path d="M4.5 4.8v4.1h4.1M12 8v4.4l3 1.8" />
        </svg>
      </button>
    </nav>
  </header>
</template>
