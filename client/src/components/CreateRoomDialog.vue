<script setup lang="ts">
import { computed, reactive } from "vue";

import type { Difficulty, PuzzleStyle, RoomConfig } from "../types/game";
import BaseModal from "./BaseModal.vue";

const props = defineProps<{
  open: boolean;
  nickname: string;
  loading?: boolean;
  error?: string;
}>();

const emit = defineEmits<{
  close: [];
  create: [nickname: string, config: RoomConfig];
}>();

const form = reactive<RoomConfig & { nickname: string }>({
  nickname: props.nickname,
  source: "ai",
  difficulty: "新手",
  style: "经典悬疑",
});

const difficulties: Array<{ value: Difficulty; hint: string }> = [
  { value: "新手", hint: "线索集中" },
  { value: "标准", hint: "需要串联" },
  { value: "烧脑", hint: "多层因果" },
];

const styles: Array<{ value: PuzzleStyle; hint: string }> = [
  { value: "轻松日常", hint: "巧合与误会" },
  { value: "经典悬疑", hint: "适度紧张" },
  { value: "暗黑惊悚", hint: "压迫与反转" },
  { value: "荒诞幽默", hint: "离谱但合理" },
];

const canSubmit = computed(() => form.nickname.trim().length >= 1);

function submit(): void {
  if (!canSubmit.value || props.loading) return;
  emit("create", form.nickname.trim(), {
    source: form.source,
    difficulty: form.difficulty,
    style: form.style,
  });
}
</script>

<template>
  <BaseModal
    :open="open"
    wide
    eyebrow="CREATE A ROOM"
    title="开一间今晚的推理房"
    description="先把门推开，题目和朋友随后就到。"
    @close="emit('close')"
  >
    <form class="dialog-form" @submit.prevent="submit">
      <label class="field">
        <span>你的昵称</span>
        <input v-model="form.nickname" maxlength="16" autocomplete="nickname" placeholder="朋友怎么称呼你？" />
      </label>

      <fieldset class="choice-section">
        <legend>题目来源</legend>
        <div class="segmented segmented--two">
          <button
            type="button"
            :class="{ active: form.source === 'ai' }"
            @click="form.source = 'ai'"
          >
            <span class="choice-icon choice-icon--spark">✦</span>
            <strong>AI 现场生成</strong>
            <small>每次都是一碗新汤</small>
          </button>
          <button
            type="button"
            :class="{ active: form.source === 'library' }"
            @click="form.source = 'library'"
          >
            <span class="choice-icon">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M6 5.5h10.5A1.5 1.5 0 0 1 18 7v12H7.5A1.5 1.5 0 0 1 6 17.5v-12Z" />
                <path d="M6 17.5A1.5 1.5 0 0 1 7.5 16H18M6 5.5H4.8A.8.8 0 0 0 4 6.3v12.2" />
              </svg>
            </span>
            <strong>私人题库</strong>
            <small>避开最近出现的题目</small>
          </button>
        </div>
      </fieldset>

      <Transition name="soft">
        <div v-if="form.source === 'ai'" class="ai-options">
          <fieldset class="choice-section">
            <legend>难度</legend>
            <div class="chip-grid chip-grid--three">
              <button
                v-for="item in difficulties"
                :key="item.value"
                type="button"
                class="choice-chip"
                :class="{ active: form.difficulty === item.value }"
                @click="form.difficulty = item.value"
              >
                <strong>{{ item.value }}</strong>
                <small>{{ item.hint }}</small>
              </button>
            </div>
          </fieldset>

          <fieldset class="choice-section">
            <legend>风格</legend>
            <div class="chip-grid chip-grid--four">
              <button
                v-for="item in styles"
                :key="item.value"
                type="button"
                class="choice-chip"
                :class="{ active: form.style === item.value }"
                @click="form.style = item.value"
              >
                <strong>{{ item.value }}</strong>
                <small>{{ item.hint }}</small>
              </button>
            </div>
          </fieldset>
        </div>
      </Transition>

      <div v-if="form.source === 'library'" class="library-note">
        <span class="tiny-lamp" aria-hidden="true"></span>
        <div>
          <strong>会从私人题库随机端上一碗</strong>
          <p>默认避开最近 10 道题，不需要选择难度或风格。</p>
        </div>
      </div>

      <p v-if="props.error" class="form-error">{{ props.error }}</p>
      <button class="primary-button primary-button--full" type="submit" :disabled="!canSubmit || props.loading">
        <span v-if="props.loading" class="button-spinner"></span>
        {{ props.loading ? "正在连接房间……" : "创建房间" }}
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M5 12h14M14 7l5 5-5 5" />
        </svg>
      </button>
    </form>
  </BaseModal>
</template>
