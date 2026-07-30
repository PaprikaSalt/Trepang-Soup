<script setup lang="ts">
import { computed, ref } from "vue";

import BaseModal from "./BaseModal.vue";

const props = defineProps<{
  open: boolean;
  nickname: string;
}>();

const emit = defineEmits<{
  close: [];
  join: [nickname: string, code: string];
}>();

const localNickname = ref(props.nickname);
const code = ref("");
const canSubmit = computed(() => localNickname.value.trim() && code.value.replace(/\s/g, "").length === 6);

function normalizeCode(): void {
  code.value = code.value.toUpperCase().replace(/[^A-Z2-9]/g, "").slice(0, 6);
}

function submit(): void {
  if (!canSubmit.value) return;
  emit("join", localNickname.value.trim(), code.value);
}
</script>

<template>
  <BaseModal
    :open="open"
    eyebrow="JOIN FRIENDS"
    title="今晚，谁已经把汤端上桌了？"
    description="填入昵称和朋友发来的六位邀请码。"
    @close="emit('close')"
  >
    <form class="dialog-form" @submit.prevent="submit">
      <label class="field">
        <span>你的昵称</span>
        <input v-model="localNickname" maxlength="16" autocomplete="nickname" placeholder="朋友怎么称呼你？" />
      </label>
      <label class="field">
        <span>房间邀请码</span>
        <input
          v-model="code"
          class="code-input"
          maxlength="6"
          autocomplete="off"
          placeholder="N7K4WM"
          @input="normalizeCode"
        />
      </label>
      <p class="field-help">演示阶段输入任意 6 位字母或数字都可以进入模拟房间。</p>
      <button class="primary-button primary-button--full" type="submit" :disabled="!canSubmit">
        推门进去
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="M5 12h14M14 7l5 5-5 5" />
        </svg>
      </button>
    </form>
  </BaseModal>
</template>
