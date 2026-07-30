<script setup lang="ts">
import { computed, ref } from "vue";

import AppHeader from "../components/AppHeader.vue";
import BaseModal from "../components/BaseModal.vue";

interface LibraryItem {
  id: number;
  title: string;
  surface: string;
  truth: string;
  active: boolean;
}

const unlocked = ref(false);
const password = ref("");
const passwordError = ref("");
const editorOpen = ref(false);
const editing = ref<LibraryItem | null>(null);
const query = ref("");
const items = ref<LibraryItem[]>([
  {
    id: 1,
    title: "最后一班电梯",
    surface: "男人每天都坐最后一班电梯回家，有一天却在一楼坐到天亮。",
    truth: "这里将在真实后端接入后保存完整汤底。",
    active: true,
  },
  {
    id: 2,
    title: "没有寄出的明信片",
    surface: "她收到一张没有邮戳的明信片后，立刻取消了旅行。",
    truth: "这里将在真实后端接入后保存完整汤底。",
    active: true,
  },
  {
    id: 3,
    title: "雨夜的鞋印",
    surface: "门外只有一串走向房间的湿鞋印，屋里却没有任何人。",
    truth: "这里将在真实后端接入后保存完整汤底。",
    active: false,
  },
]);

const filteredItems = computed(() =>
  items.value.filter((item) => `${item.title}${item.surface}`.includes(query.value.trim())),
);

function unlock(): void {
  if (password.value === "soup") {
    unlocked.value = true;
    passwordError.value = "";
  } else {
    passwordError.value = "演示模式密码是 soup。真实版本不会在客户端保存管理员密码。";
  }
}

function openEditor(item?: LibraryItem): void {
  editing.value = item
    ? { ...item }
    : { id: Date.now(), title: "", surface: "", truth: "", active: true };
  editorOpen.value = true;
}

function saveItem(): void {
  if (!editing.value?.title.trim() || !editing.value.surface.trim() || !editing.value.truth.trim()) return;
  const index = items.value.findIndex((item) => item.id === editing.value?.id);
  if (index >= 0) items.value[index] = { ...editing.value };
  else items.value.unshift({ ...editing.value });
  editorOpen.value = false;
}
</script>

<template>
  <div class="page page--subpage">
    <AppHeader />
    <main class="subpage-main">
      <section v-if="!unlocked" class="admin-gate">
        <div class="admin-gate__glow"></div>
        <span class="admin-lock">
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <rect x="5" y="10" width="14" height="10" rx="2" />
            <path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v2" />
          </svg>
        </span>
        <p class="eyebrow">PRIVATE LIBRARY</p>
        <h1>私人题库</h1>
        <p>这里只给题库管理员留了一把钥匙。</p>
        <form @submit.prevent="unlock">
          <label class="field">
            <span>管理员密码</span>
            <input v-model="password" type="password" autocomplete="current-password" placeholder="输入专用密码" />
          </label>
          <p v-if="passwordError" class="form-error">{{ passwordError }}</p>
          <button class="primary-button primary-button--full" type="submit">解锁题库</button>
        </form>
        <small>当前为客户端演示界面，不会向服务器发送密码。</small>
      </section>

      <template v-else>
        <header class="subpage-heading">
          <div>
            <p class="eyebrow">PRIVATE LIBRARY</p>
            <h1>私人题库</h1>
            <p>只有你可以维护这些题目；房主开局时只能随机抽取。</p>
          </div>
          <button class="primary-button" type="button" @click="openEditor()">
            新增题目
            <span>+</span>
          </button>
        </header>

        <div class="library-toolbar">
          <label class="search-field">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="11" cy="11" r="6" />
              <path d="m16 16 4 4" />
            </svg>
            <input v-model="query" placeholder="搜索汤面或标题" />
          </label>
          <div>
            <span>{{ items.filter((item) => item.active).length }} 道启用</span>
            <i></i>
            <span>最近 10 道自动避开</span>
          </div>
        </div>

        <section class="library-list">
          <article v-for="item in filteredItems" :key="item.id" class="library-card">
            <span class="library-card__status" :class="{ inactive: !item.active }"></span>
            <div>
              <small>{{ item.active ? "已启用" : "已停用" }}</small>
              <h2>{{ item.title }}</h2>
              <p>{{ item.surface }}</p>
            </div>
            <button class="icon-button" type="button" title="编辑题目" @click="openEditor(item)">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m4 16-.5 4.5L8 20l10-10-4-4L4 16Z" />
                <path d="m12.5 7.5 4 4" />
              </svg>
            </button>
          </article>
        </section>
      </template>
    </main>

    <BaseModal
      :open="editorOpen"
      wide
      eyebrow="PUZZLE EDITOR"
      :title="items.some((item) => item.id === editing?.id) ? '编辑题目' : '新增题目'"
      @close="editorOpen = false"
    >
      <form v-if="editing" class="dialog-form" @submit.prevent="saveItem">
        <label class="field">
          <span>内部标题</span>
          <input v-model="editing.title" maxlength="40" placeholder="方便你在题库中识别" />
        </label>
        <label class="field">
          <span>汤面</span>
          <textarea v-model="editing.surface" rows="4" maxlength="500" placeholder="玩家开局时看到的故事……"></textarea>
        </label>
        <label class="field">
          <span>汤底与关键真相</span>
          <textarea v-model="editing.truth" rows="7" maxlength="2000" placeholder="仅服务端与 AI 主持人可以读取……"></textarea>
        </label>
        <label class="toggle-row">
          <span>
            <strong>允许随机抽取</strong>
            <small>停用后仍保留题目，但不会进入房间。</small>
          </span>
          <input v-model="editing.active" type="checkbox" />
          <i></i>
        </label>
        <button class="primary-button primary-button--full" type="submit">保存题目</button>
      </form>
    </BaseModal>
  </div>
</template>
