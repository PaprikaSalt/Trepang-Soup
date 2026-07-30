<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

import AppHeader from "../components/AppHeader.vue";
import PlayerAvatar from "../components/PlayerAvatar.vue";
import { useGameStore } from "../stores/game";

const router = useRouter();
const game = useGameStore();
const copied = ref(false);
const starting = ref(false);

const sourceLabel = computed(() =>
  game.roomConfig.source === "ai"
    ? `AI 生成 · ${game.roomConfig.difficulty} · ${game.roomConfig.style}`
    : "私人题库 · 随机抽取",
);

onMounted(async () => {
  try {
    await game.ensureRoom();
  } catch {
    await router.push("/");
  }
});

watch(
  () => game.stage,
  (value) => {
    if (value === "playing") void router.push(`/room/${game.roomCode}`);
    if (value === "closed") void router.push("/");
  },
);

async function copyCode(): Promise<void> {
  try {
    await navigator.clipboard.writeText(game.roomCode);
  } catch {
    // Clipboard may be unavailable in browser preview; the visible code is still selectable.
  }
  copied.value = true;
  window.setTimeout(() => (copied.value = false), 1400);
}

async function startGame(): Promise<void> {
  if (starting.value) return;
  starting.value = true;
  try {
    await game.startGame();
  } finally {
    starting.value = false;
  }
}
</script>

<template>
  <div class="page page--lobby">
    <AppHeader :room-code="game.roomCode" />
    <main class="lobby-main">
      <section class="lobby-copy">
        <p class="eyebrow">ROOM IS OPEN</p>
        <h1>人还没齐，<br /><span>先把椅子拉过来。</span></h1>
        <p>邀请码发给朋友，他们填个昵称就能进来。游戏开始后也不关门。</p>

        <button class="invite-card" type="button" @click="copyCode">
          <span>
            <small>房间邀请码</small>
            <strong>{{ game.roomCode }}</strong>
          </span>
          <i>
            <svg v-if="!copied" viewBox="0 0 24 24" aria-hidden="true">
              <rect x="8" y="8" width="11" height="11" rx="2" />
              <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2" />
            </svg>
            <svg v-else viewBox="0 0 24 24" aria-hidden="true">
              <path d="m5 12 4 4L19 6" />
            </svg>
          </i>
          <em>{{ copied ? "已复制，发给朋友吧" : "点击复制邀请码" }}</em>
        </button>

        <div class="lobby-setting">
          <span class="setting-icon">✦</span>
          <div>
            <small>今晚的汤</small>
            <strong>{{ sourceLabel }}</strong>
          </div>
        </div>
      </section>

      <section class="lobby-panel">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">AROUND THE TABLE</p>
            <h2>已经坐下的人</h2>
          </div>
          <span class="online-pill"><i></i>{{ game.onlineCount }}/20 在线</span>
        </div>

        <div class="player-grid">
          <article v-for="player in game.players" :key="player.id" class="player-card">
            <PlayerAvatar :name="player.nickname" :color="player.accent" size="large" :online="player.online" />
            <div>
              <strong>{{ player.nickname }}</strong>
              <small>{{ player.id === game.selfId ? "这是你" : "等待开局" }}</small>
            </div>
            <span v-if="player.isHost" class="host-badge">房主</span>
          </article>
          <article class="player-card player-card--empty">
            <span class="empty-seat">+</span>
            <div>
              <strong>还空着一把椅子</strong>
              <small>把邀请码发出去</small>
            </div>
          </article>
        </div>

        <div class="lobby-note">
          <span class="pulse-dot"></span>
          <p>游戏开始后仍可中途加入，新朋友会自动看到完整问答。</p>
        </div>

        <p v-if="game.lastError" class="form-error">{{ game.lastError }}</p>

        <button
          v-if="game.isHost"
          class="primary-button primary-button--full primary-button--large"
          type="button"
          :disabled="starting"
          @click="startGame"
        >
          <span v-if="starting" class="button-spinner"></span>
          {{ starting ? "主持人正在端汤……" : "人差不多了，开始吧" }}
        </button>
        <div v-else class="waiting-host">
          <span class="thinking-dots"><i></i><i></i><i></i></span>
          等房主把汤端上桌
        </div>
      </section>
    </main>
  </div>
</template>
