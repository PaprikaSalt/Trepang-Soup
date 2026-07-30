<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";

import AppHeader from "../components/AppHeader.vue";
import CreateRoomDialog from "../components/CreateRoomDialog.vue";
import JoinRoomDialog from "../components/JoinRoomDialog.vue";
import { useGameStore } from "../stores/game";
import type { RoomConfig } from "../types/game";

const router = useRouter();
const game = useGameStore();
const createOpen = ref(false);
const joinOpen = ref(false);
const creating = ref(false);
const joining = ref(false);
const admissionError = ref("");
const historyLabel = computed(() =>
  game.history.length ? `本地保存了 ${game.history.length} 局` : "还没有本地记录",
);

onMounted(() => {
  void game.checkServer();
});

async function createRoom(nickname: string, config: RoomConfig): Promise<void> {
  if (creating.value) return;
  creating.value = true;
  admissionError.value = "";
  try {
    const code = await game.createRoom(nickname, config);
    createOpen.value = false;
    await router.push(`/lobby/${code}`);
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
    await router.push(`/lobby/${normalized}`);
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
              <small>选择 AI 生成或私人题库</small>
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
              <small>填写昵称和六位邀请码</small>
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
              <small>{{ historyLabel }}</small>
            </span>
          </button>

          <button type="button" @click="router.push('/library')">
            <span class="home-tool-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24">
                <path d="M6 5.5h10.5A1.5 1.5 0 0 1 18 7v12H7.5A1.5 1.5 0 0 1 6 17.5v-12Z" />
                <path d="M6 17.5A1.5 1.5 0 0 1 7.5 16H18M6 5.5H4.8A.8.8 0 0 0 4 6.3v12.2" />
              </svg>
            </span>
            <span>
              <strong>题库管理</strong>
              <small>管理员专用入口</small>
            </span>
          </button>
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
