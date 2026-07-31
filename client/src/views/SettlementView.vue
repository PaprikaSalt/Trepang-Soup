<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRouter } from "vue-router";

import AppHeader from "../components/AppHeader.vue";
import PlayerAvatar from "../components/PlayerAvatar.vue";
import { useGameStore } from "../stores/game";

const router = useRouter();
const game = useGameStore();

const settlement = computed(() => game.settlement);
const voting = ref(false);
const leaving = ref(false);
const acceptedPlayerIds = computed(() => new Set(game.rematch?.acceptedPlayerIds ?? []));
const eligiblePlayers = computed(() =>
  (game.rematch?.eligiblePlayerIds ?? [])
    .map((playerId) => game.players.find((player) => player.id === playerId))
    .filter((player) => player !== undefined),
);
const selfAccepted = computed(() => acceptedPlayerIds.value.has(game.selfId));

onMounted(async () => {
  try {
    await game.ensureRoom();
    // 结算只能由服务端事件或恢复快照进入，避免客户端自行伪造本局结果。
    if (game.stage === "lobby") await router.replace(`/lobby/${game.roomCode}`);
    else if (game.stage === "playing") await router.replace(`/room/${game.roomCode}`);
    else if (game.stage === "closed") await router.replace("/");
  } catch {
    await router.replace("/");
  }
});

watch(
  () => game.stage,
  (stage) => {
    if (stage === "playing") void router.replace(`/room/${game.roomCode}`);
    else if (stage === "lobby") void router.replace(`/lobby/${game.roomCode}`);
    else if (stage === "closed") void router.replace("/");
  },
);

async function toggleRematchVote(): Promise<void> {
  if (voting.value || game.rematch?.status === "generating") return;
  voting.value = true;
  try {
    await game.voteRematch(!selfAccepted.value);
  } finally {
    voting.value = false;
  }
}

async function leaveRoom(): Promise<void> {
  if (leaving.value) return;
  leaving.value = true;
  try {
    await game.leaveRoom();
  } finally {
    await router.replace("/");
    leaving.value = false;
  }
}
</script>

<template>
  <div class="page page--settlement">
    <AppHeader :room-code="game.roomCode" />
    <main v-if="settlement" class="settlement-main">
      <section class="settlement-hero">
        <p class="eyebrow">THE SOUP IS CLEAR</p>
        <div class="score-seal">
          <span>{{ settlement.grade }}</span>
          <small>{{ settlement.score }} 分</small>
          <i></i>
        </div>
        <h1>汤见底了，<br /><span>今晚推得不错。</span></h1>
        <p>{{ settlement.summary }}</p>
        <div class="settlement-meta">
          <span>正式问答 {{ game.questions.filter((question) => question.status === "answered").length }} 条</span>
          <i></i>
          <span>公共提示 {{ game.hintCount }} 次</span>
          <i></i>
          <span>{{ settlement.gaveUp ? "公布汤底" : "成功结案" }}</span>
        </div>
      </section>

      <section class="truth-panel">
        <div class="section-label">
          <span>完整汤底</span>
          <small>{{ game.puzzle.title }}</small>
        </div>
        <blockquote>{{ game.puzzle.truth }}</blockquote>
        <div class="truth-facts">
          <span v-for="fact in game.puzzle.keyFacts" :key="fact">{{ fact }}</span>
        </div>
      </section>

      <section class="awards-section">
        <div class="awards-heading">
          <div>
            <p class="eyebrow">TONIGHT'S HONORS</p>
            <h2>今晚的小奖状</h2>
          </div>
          <p>主持人的评价只在这局有效，笑完就好。</p>
        </div>
        <div class="award-grid">
          <article v-for="(award, index) in settlement.awards" :key="award.title" class="award-card">
            <span class="award-card__number">0{{ index + 1 }}</span>
            <small>{{ award.title }}</small>
            <h3>{{ award.recipient }}</h3>
            <p>{{ award.reason }}</p>
          </article>
        </div>
      </section>

      <section v-if="game.rematch" class="rematch-panel">
        <div class="rematch-panel__heading">
          <div>
            <p class="eyebrow">ONE MORE ROUND</p>
            <h2>原班人马，再来一碗</h2>
          </div>
          <strong>
            {{ game.rematch.acceptedPlayerIds.length }} / {{ game.rematch.eligiblePlayerIds.length }}
          </strong>
        </div>

        <div class="rematch-voters">
          <article
            v-for="player in eligiblePlayers"
            :key="player.id"
            :class="{ accepted: acceptedPlayerIds.has(player.id) }"
          >
            <PlayerAvatar
              :name="player.nickname"
              :color="player.accent"
              :online="player.online"
              size="small"
            />
            <span>{{ player.nickname }}</span>
            <i>{{ acceptedPlayerIds.has(player.id) ? "已同意" : "等待中" }}</i>
          </article>
        </div>

        <div v-if="game.rematch.status === 'generating'" class="rematch-generating">
          <span class="button-spinner"></span>
          <strong>主持人正在准备下一碗汤……</strong>
        </div>
      </section>

      <div class="settlement-actions">
        <button class="secondary-button" type="button" @click="router.push('/history')">查看本地记录</button>
        <button class="secondary-button" type="button" :disabled="leaving" @click="leaveRoom">
          {{ leaving ? "正在离开……" : "退出房间" }}
        </button>
        <button
          v-if="game.rematch"
          class="primary-button"
          type="button"
          :disabled="voting || game.rematch.status === 'generating'"
          @click="toggleRematchVote"
        >
          {{ selfAccepted ? "撤回同意" : "同意再来一局" }}
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M5 12h14M14 7l5 5-5 5" />
          </svg>
        </button>
      </div>
    </main>
  </div>
</template>
