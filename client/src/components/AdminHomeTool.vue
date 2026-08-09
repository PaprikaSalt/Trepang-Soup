<script setup lang="ts">
import { useRouter } from "vue-router";

const router = useRouter();
</script>

<template>
  <button type="button" @click="router.push('/library')">
    <span class="home-tool-icon" aria-hidden="true">
      <svg viewBox="0 0 24 24">
        <path d="M6 5.5h10.5A1.5 1.5 0 0 1 18 7v12H7.5A1.5 1.5 0 0 1 6 17.5v-12Z" />
        <path d="M6 17.5A1.5 1.5 0 0 1 7.5 16H18M6 5.5H4.8A.8.8 0 0 0 4 6.3v12.2" />
      </svg>
    </span>
    <span><strong>题库管理</strong></span>
  </button>
</template>
