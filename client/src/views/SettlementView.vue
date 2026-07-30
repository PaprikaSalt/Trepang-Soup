<script setup lang="ts">
import { computed, onMounted } from "vue";
import { useRouter } from "vue-router";

import AppHeader from "../components/AppHeader.vue";
import { useGameStore } from "../stores/game";

const router = useRouter();
const game = useGameStore();

const settlement = computed(() => game.settlement);

onMounted(() => {
  game.ensureDemoRoom();
  if (!game.settlement) game.finishGame(false);
});

function returnHome(): void {
  void router.push("/");
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

      <div class="settlement-actions">
        <button class="secondary-button" type="button" @click="router.push('/history')">查看本地记录</button>
        <button class="primary-button" type="button" @click="returnHome">
          再开一桌
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M5 12h14M14 7l5 5-5 5" />
          </svg>
        </button>
      </div>
    </main>
  </div>
</template>
