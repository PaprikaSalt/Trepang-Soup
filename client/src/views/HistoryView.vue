<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";

import AppHeader from "../components/AppHeader.vue";
import BaseModal from "../components/BaseModal.vue";
import { useGameStore } from "../stores/game";
import type { LocalHistoryEntry } from "../types/game";

const router = useRouter();
const game = useGameStore();
const selected = ref<LocalHistoryEntry | null>(null);
const confirmClear = ref(false);

function formatDate(value: number): string {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(value);
}
</script>

<template>
  <div class="page page--subpage">
    <AppHeader />
    <main class="subpage-main">
      <header class="subpage-heading">
        <div>
          <p class="eyebrow">LOCAL MEMORIES</p>
          <h1>最近端过的汤</h1>
          <p>这些记录只留在这台电脑里，服务器不会保存。</p>
        </div>
        <button v-if="game.history.length" class="ghost-button ghost-button--danger" type="button" @click="confirmClear = true">
          清空记录
        </button>
      </header>

      <section v-if="game.history.length" class="history-list">
        <button
          v-for="entry in game.history"
          :key="entry.id"
          class="history-card"
          type="button"
          @click="selected = entry"
        >
          <span class="history-score">{{ entry.settlement.grade }}</span>
          <div class="history-card__copy">
            <small>{{ formatDate(entry.settlement.endedAt) }} · 房间 {{ entry.roomCode }}</small>
            <h2>{{ entry.puzzle.title }}</h2>
            <p>{{ entry.puzzle.surface }}</p>
          </div>
          <div class="history-card__meta">
            <strong>{{ entry.settlement.score }} 分</strong>
            <span>{{ entry.timeline.filter((item) => item.kind === "qa").length }} 条问答</span>
          </div>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="m9 6 6 6-6 6" />
          </svg>
        </button>
      </section>

      <section v-else class="large-empty">
        <span class="empty-bowl"><i></i></span>
        <h2>碗柜还是空的</h2>
        <p>完成一局后，汤面、问答和结算会安静地留在这里。</p>
        <button class="primary-button" type="button" @click="router.push('/')">去开第一桌</button>
      </section>
    </main>

    <BaseModal
      :open="Boolean(selected)"
      wide
      eyebrow="LOCAL GAME RECORD"
      :title="selected?.puzzle.title ?? '对局记录'"
      @close="selected = null"
    >
      <div v-if="selected" class="history-detail">
        <div class="history-detail__surface">
          <small>汤面</small>
          <p>{{ selected.puzzle.surface }}</p>
        </div>
        <div class="history-detail__timeline">
          <article v-for="item in selected.timeline" :key="item.id">
            <template v-if="item.kind === 'qa' && item.question">
              <strong>{{ item.question.authorName }}：{{ item.question.content }}</strong>
              <p>主持人：{{ item.question.answer }}</p>
            </template>
            <template v-else-if="item.kind === 'hint'">
              <strong>{{ item.title }}</strong>
              <p>{{ item.content }}</p>
            </template>
          </article>
        </div>
        <div class="history-detail__truth">
          <small>汤底</small>
          <p>{{ selected.puzzle.truth }}</p>
        </div>
      </div>
    </BaseModal>

    <BaseModal
      :open="confirmClear"
      title="清空这台电脑上的全部记录？"
      description="此操作无法撤销，但不会影响私人题库。"
      @close="confirmClear = false"
    >
      <div class="confirm-actions">
        <button class="secondary-button" type="button" @click="confirmClear = false">取消</button>
        <button
          class="danger-button"
          type="button"
          @click="game.clearHistory(); confirmClear = false"
        >
          确认清空
        </button>
      </div>
    </BaseModal>
  </div>
</template>
