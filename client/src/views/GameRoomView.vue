<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

import AppHeader from "../components/AppHeader.vue";
import BaseModal from "../components/BaseModal.vue";
import PlayerAvatar from "../components/PlayerAvatar.vue";
import { useGameStore } from "../stores/game";
import type { Question, TimelineItem } from "../types/game";

const router = useRouter();
const game = useGameStore();
const discussionDraft = ref("");
const questionDraft = ref("");
const conclusionDraft = ref("");
const conclusionOpen = ref(false);
const giveUpOpen = ref(false);
const closeRoomOpen = ref(false);
const hintLoading = ref(false);
const conclusionLoading = ref(false);
const conclusionFeedback = ref("");
const feed = ref<HTMLElement | null>(null);

onMounted(async () => {
  try {
    await game.ensureRoom();
    if (game.stage === "lobby") await router.push(`/lobby/${game.roomCode}`);
  } catch {
    await router.push("/");
  }
});

watch(
  () => game.timeline.length,
  async () => {
    await nextTick();
    feed.value?.scrollTo({ top: feed.value.scrollHeight, behavior: "smooth" });
  },
);

watch(
  () => game.stage,
  (value) => {
    if (value === "settlement") void router.push(`/settlement/${game.roomCode}`);
    if (value === "closed") void router.push("/");
  },
);

function formatTime(value: number): string {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(value);
}

function answerLabel(question: Question): string {
  const labels = {
    yes: "是",
    no: "否",
    irrelevant: "无关",
    partial: "部分正确",
  };
  return question.answerType ? labels[question.answerType] : "回答";
}

async function sendDiscussion(): Promise<void> {
  const content = discussionDraft.value;
  try {
    await game.sendDiscussion(content);
    discussionDraft.value = "";
  } catch {
    // The store exposes a reader-facing error while preserving the unsent draft.
  }
}

async function submitQuestion(): Promise<void> {
  const content = questionDraft.value;
  try {
    await game.submitQuestion(content);
    questionDraft.value = "";
  } catch {
    // Keep the draft so a transient connection failure does not discard the question.
  }
}

async function askForHint(): Promise<void> {
  if (hintLoading.value) return;
  hintLoading.value = true;
  try {
    await game.requestHint();
  } finally {
    hintLoading.value = false;
  }
}

async function submitConclusion(): Promise<void> {
  if (!conclusionDraft.value.trim() || conclusionLoading.value) return;
  conclusionLoading.value = true;
  conclusionFeedback.value = "";
  try {
    const result = await game.submitConclusion(conclusionDraft.value);
    if (result === "correct") {
      conclusionOpen.value = false;
    } else if (result === "close") {
      const latestFeedback = [...game.timeline]
        .reverse()
        .find((item) => item.title === "结案反馈")?.content;
      conclusionFeedback.value =
        latestFeedback || "已经很接近了，请继续补全关键行为之间的因果关系。";
    } else {
      conclusionFeedback.value = game.lastError || "主持人暂时无法判断，请稍后重试。";
    }
  } finally {
    conclusionLoading.value = false;
  }
}

async function giveUp(): Promise<void> {
  try {
    await game.giveUp();
    giveUpOpen.value = false;
    conclusionOpen.value = false;
  } catch {
    // The confirmation remains open when the server does not accept the command.
  }
}

async function closeRoom(): Promise<void> {
  try {
    await game.closeRoom();
    closeRoomOpen.value = false;
  } catch {
    // The room remains visible so the host can retry after a connection error.
  }
}

function timelineKey(item: TimelineItem): string {
  return item.id;
}
</script>

<template>
  <div class="page page--game">
    <AppHeader :room-code="game.roomCode" compact>
      <template #actions>
        <button
          v-if="game.isHost"
          class="text-button text-button--danger"
          type="button"
          @click="closeRoomOpen = true"
        >
          关闭房间
        </button>
      </template>
    </AppHeader>

    <main class="game-layout">
      <aside class="game-sidebar game-sidebar--left">
        <section class="puzzle-panel">
          <div class="section-label">
            <span>汤面</span>
            <small>
              {{
                game.roomConfig.source === "library"
                  ? "私人题库 · 随机抽取"
                  : `${game.roomConfig.difficulty} · ${game.roomConfig.style}`
              }}
            </small>
          </div>
          <blockquote>{{ game.puzzle.surface }}</blockquote>
        </section>

        <section class="members-panel">
          <div class="section-label">
            <span>围桌玩家</span>
            <small>{{ game.onlineCount }} 在线</small>
          </div>
          <div class="member-list">
            <div v-for="player in game.players" :key="player.id" class="member-row">
              <PlayerAvatar :name="player.nickname" :color="player.accent" size="small" />
              <span>{{ player.nickname }}</span>
              <em v-if="player.isHost">房主</em>
            </div>
          </div>
        </section>

        <button class="conclusion-button" type="button" @click="conclusionOpen = true">
          <span>
            <strong>我们知道了</strong>
          </span>
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M9 18h6M10 22h4M8.5 14.5a6 6 0 1 1 7 0c-.9.6-1.5 1.5-1.5 2.5h-4c0-1-.6-1.9-1.5-2.5Z" />
          </svg>
        </button>
      </aside>

      <section class="host-column">
        <header class="column-heading">
          <div>
            <span class="host-orb"><i></i></span>
            <div>
              <p>AI 主持人</p>
              <small>正在认真听你们胡说八道</small>
            </div>
          </div>
          <span class="connection-state"><i></i>{{ game.connectionLabel }}</span>
        </header>

        <div ref="feed" class="timeline-feed">
          <article
            v-for="item in game.timeline"
            :key="timelineKey(item)"
            class="timeline-item"
            :class="`timeline-item--${item.kind}`"
          >
            <template v-if="item.kind === 'system'">
              <span class="timeline-rule"></span>
              <div class="system-message">
                <strong>{{ item.title }}</strong>
                <p>{{ item.content }}</p>
              </div>
              <span class="timeline-rule"></span>
            </template>

            <template v-else-if="item.kind === 'hint'">
              <div class="hint-card">
                <div class="hint-card__top">
                  <span>✦</span>
                  <strong>{{ item.title }}</strong>
                  <small>{{ formatTime(item.createdAt) }}</small>
                </div>
                <p>{{ item.content }}</p>
                <em>由 {{ item.actorName }} 请求 · 本局评分 -7</em>
              </div>
            </template>

            <template v-else-if="item.question">
              <div class="question-line">
                <div class="message-author">
                  <PlayerAvatar :name="item.question.authorName" size="small" />
                  <strong>{{ item.question.authorName }}</strong>
                  <small>{{ formatTime(item.question.createdAt) }}</small>
                </div>
                <p>{{ item.question.content }}</p>
              </div>
              <div class="host-answer">
                <div class="host-answer__label">
                  <span class="host-orb host-orb--small"><i></i></span>
                  <strong>{{ answerLabel(item.question) }}</strong>
                </div>
                <p>{{ item.question.answer }}</p>
              </div>
            </template>
          </article>

          <div v-if="game.pendingQuestions.some((question) => question.status === 'thinking')" class="ai-thinking">
            <span class="host-orb host-orb--small"><i></i></span>
            <p>主持人翻了翻汤底</p>
            <span class="thinking-dots"><i></i><i></i><i></i></span>
          </div>
        </div>

        <p v-if="game.lastError" class="game-error">{{ game.lastError }}</p>

        <form class="question-composer" @submit.prevent="submitQuestion">
          <div class="composer-label">
            <span>向主持人提问</span>
            <small>Enter 发送 · Shift + Enter 换行</small>
          </div>
          <div class="composer-box">
            <textarea
              v-model="questionDraft"
              rows="2"
              maxlength="180"
              placeholder="这个问题会进入待回答队列……"
              @keydown.enter.exact.prevent="submitQuestion"
            ></textarea>
            <button type="submit" :disabled="!questionDraft.trim()" aria-label="提交问题">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m5 12 14-7-4 14-3-6-7-1Z" />
                <path d="m12 13 7-8" />
              </svg>
            </button>
          </div>
        </form>
      </section>

      <aside class="game-sidebar game-sidebar--right">
        <section class="queue-panel">
          <div class="section-label section-label--queue">
            <span>待回答</span>
            <small>{{ game.pendingQuestions.length }} 个问题</small>
          </div>
          <div v-if="game.pendingQuestions.length" class="question-queue">
            <article
              v-for="(question, index) in game.pendingQuestions"
              :key="question.id"
              class="queue-item"
              :class="{ 'queue-item--thinking': question.status === 'thinking' }"
            >
              <span class="queue-index">{{ String(index + 1).padStart(2, "0") }}</span>
              <div>
                <p>{{ question.content }}</p>
                <small>
                  {{ question.authorName }}
                  <i>·</i>
                  {{ question.status === "thinking" ? "主持人思考中" : "等待回答" }}
                </small>
              </div>
              <button
                v-if="question.authorId === game.selfId && question.status === 'queued'"
                type="button"
                title="撤回问题"
                @click="game.removeQuestion(question.id)"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M6 7h12M10 7V5h4v2M8 7l1 12h6l1-12" />
                </svg>
              </button>
              <span v-else-if="question.status === 'thinking'" class="mini-spinner"></span>
            </article>
          </div>
          <div v-else class="queue-empty">
            <span class="empty-rings"><i></i><i></i></span>
            <p>队列空空的</p>
            <small>问一个能让大家突然安静的问题。</small>
          </div>

          <button class="hint-button" type="button" :disabled="hintLoading" @click="askForHint">
            <span class="hint-button__icon">?</span>
            <span>
              <strong>{{ hintLoading ? "主持人正在梳理……" : "我没招了" }}</strong>
            </span>
          </button>
        </section>

        <section class="discussion-panel">
          <div class="section-label">
            <span>聊天室</span>
          </div>
          <div class="discussion-list">
            <article v-for="message in game.discussions" :key="message.id" class="discussion-message">
              <PlayerAvatar
                :name="message.authorName"
                :color="game.players.find((player) => player.id === message.authorId)?.accent"
                size="small"
              />
              <div>
                <p>
                  <strong>{{ message.authorName }}</strong>
                  <small>{{ formatTime(message.createdAt) }}</small>
                </p>
                <span>{{ message.content }}</span>
              </div>
            </article>
          </div>
          <form class="discussion-composer" @submit.prevent="sendDiscussion">
            <input v-model="discussionDraft" maxlength="180" placeholder="和朋友小声商量……" />
            <button type="submit" :disabled="!discussionDraft.trim()" aria-label="发送讨论">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m5 12 14-7-4 14-3-6-7-1Z" />
              </svg>
            </button>
          </form>
        </section>
      </aside>
    </main>

    <BaseModal
      :open="conclusionOpen"
      wide
      eyebrow="FINAL THEORY"
      title="把你们认为的真相讲完整"
      description="不用逐字命中汤底，但要解释关键人物、动机和反常行为。"
      @close="conclusionOpen = false"
    >
      <div class="conclusion-form">
        <textarea
          v-model="conclusionDraft"
          rows="7"
          maxlength="800"
          placeholder="林夏发现……所以她故意……最后……"
        ></textarea>
        <p v-if="conclusionFeedback" class="conclusion-feedback">{{ conclusionFeedback }}</p>
        <div class="modal-actions">
          <button class="ghost-button ghost-button--danger" type="button" @click="giveUpOpen = true">
            实在想不到，公布汤底
          </button>
          <button
            class="primary-button"
            type="button"
            :disabled="!conclusionDraft.trim() || conclusionLoading"
            @click="submitConclusion"
          >
            <span v-if="conclusionLoading" class="button-spinner"></span>
            {{ conclusionLoading ? "主持人正在核对……" : "提交完整推理" }}
          </button>
        </div>
      </div>
    </BaseModal>

    <BaseModal
      :open="giveUpOpen"
      eyebrow="LAST CHANCE"
      title="真的要直接看汤底吗？"
      description="这会结束本局并影响评分，不过承认想不到也是推理的一部分。"
      @close="giveUpOpen = false"
    >
      <div class="confirm-actions">
        <button class="secondary-button" type="button" @click="giveUpOpen = false">再想一会儿</button>
        <button class="danger-button" type="button" @click="giveUp">公布汤底</button>
      </div>
    </BaseModal>

    <BaseModal
      :open="closeRoomOpen"
      eyebrow="CLOSE ROOM"
      title="确定要关闭房间吗？"
      description="所有玩家都会离开当前房间，本局不会进入结算，也不会保存到本地对局记录。"
      @close="closeRoomOpen = false"
    >
      <div class="confirm-actions">
        <button class="secondary-button" type="button" @click="closeRoomOpen = false">取消</button>
        <button class="danger-button" type="button" @click="closeRoom">关闭房间</button>
      </div>
    </BaseModal>
  </div>
</template>
