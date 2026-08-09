<script setup lang="ts">
import { defineAsyncComponent, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import AppHeader from "../components/AppHeader.vue";
import CreateRoomDialog from "../components/CreateRoomDialog.vue";
import JoinRoomDialog from "../components/JoinRoomDialog.vue";
import { adminEnabled } from "../config/features";
import { useGameStore } from "../stores/game";
import type { RoomConfig, RoomStage } from "../types/game";

const router = useRouter();
const game = useGameStore();
const createOpen = ref(false);
const joinOpen = ref(false);
const creating = ref(false);
const joining = ref(false);
const admissionError = ref("");
// Keeping this UI in a lazy chunk lets Rollup remove it completely from public Web builds.
const AdminHomeTool = adminEnabled
  ? defineAsyncComponent(() => import("../components/AdminHomeTool.vue"))
  : null;
onMounted(() => {
  void game.checkServer();
});

function routeForStage(stage: RoomStage, code: string): string {
  // Admission returns after the authoritative snapshot arrives, so late
  // joiners must enter the page matching the server's current room stage.
  if (stage === "playing") return `/room/${code}`;
  if (stage === "settlement") return `/settlement/${code}`;
  if (stage === "lobby") return `/lobby/${code}`;
  return "/";
}

async function createRoom(nickname: string, config: RoomConfig): Promise<void> {
  if (creating.value) return;
  creating.value = true;
  admissionError.value = "";
  try {
    const code = await game.createRoom(nickname, config);
    createOpen.value = false;
    await router.push(routeForStage(game.stage, code));
  } catch (error) {
    admissionError.value = error instanceof Error ? error.message : "创建房间失败。";
  } finally {
    creating.value = false;
  }
}

async function joinRoom(nickname: string, code: string): Promise<void> {
  if (joining.value) return;
  joining.value = true;
  admissionError.value = "";
  try {
    const normalized = await game.joinRoom(nickname, code);
    joinOpen.value = false;
    await router.push(routeForStage(game.stage, normalized));
  } catch (error) {
    admissionError.value = error instanceof Error ? error.message : "加入房间失败。";
  } finally {
    joining.value = false;
  }
}

function openCreateDialog(): void {
  admissionError.value = "";
  createOpen.value = true;
}

function openJoinDialog(): void {
  admissionError.value = "";
  joinOpen.value = true;
}
</script>

<template>
  <div class="page page--home">
    <AppHeader :show-history="false" />

    <main class="home-main home-main--minimal">
      <section class="home-entry" aria-label="房间入口">
        <div class="home-entry__title">
          <h1>海龟汤</h1>
          <p>选择要进行的操作</p>
        </div>

        <div class="room-actions">
          <button class="room-action-card room-action-card--primary" type="button" @click="openCreateDialog">
            <span class="room-action-card__icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M12 5v14M5 12h14" />
              </svg>
            </span>
            <span class="room-action-card__copy">
              <strong>创建房间</strong>
            </span>
            <svg class="room-action-card__arrow" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M5 12h14M14 7l5 5-5 5" />
            </svg>
          </button>

          <button class="room-action-card" type="button" @click="openJoinDialog">
            <span class="room-action-card__icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M8 12h8M12 8l4 4-4 4" />
                <rect x="4" y="4" width="16" height="16" rx="4" />
              </svg>
            </span>
            <span class="room-action-card__copy">
              <strong>加入房间</strong>
            </span>
            <svg class="room-action-card__arrow" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M5 12h14M14 7l5 5-5 5" />
            </svg>
          </button>
        </div>

        <div class="home-tools">
          <button type="button" @click="router.push('/history')">
            <span class="home-tool-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3L4.5 8.9" />
                <path d="M4.5 4.8v4.1h4.1M12 8v4.4l3 1.8" />
              </svg>
            </span>
            <span>
              <strong>本地对局</strong>
            </span>
          </button>

          <AdminHomeTool v-if="AdminHomeTool" />
        </div>

        <div class="home-status" :class="{ 'home-status--error': game.connectionStatus === 'error' }">
          <span><i></i>{{ game.connectionLabel }}</span>
          <span v-if="game.nickname">上次昵称：{{ game.nickname }}</span>
        </div>
      </section>
    </main>

    <CreateRoomDialog
      :open="createOpen"
      :nickname="game.nickname"
      :loading="creating"
      :error="admissionError"
      @close="createOpen = false"
      @create="createRoom"
    />
    <JoinRoomDialog
      :open="joinOpen"
      :nickname="game.nickname"
      :loading="joining"
      :error="admissionError"
      @close="joinOpen = false"
      @join="joinRoom"
    />
  </div>
</template>
