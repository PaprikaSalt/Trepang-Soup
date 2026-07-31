<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import AppHeader from "../components/AppHeader.vue";
import BaseModal from "../components/BaseModal.vue";
import {
  AdminTransportError,
  adminTransport,
  type LibraryPuzzle,
  type PuzzleImportFile,
  type PuzzleImportItem,
  type PuzzleWrite,
} from "../transport/AdminTransport";

interface PuzzleDraft {
  id: string | null;
  title: string;
  surface: string;
  truth: string;
  keyFactsText: string;
  active: boolean;
}

const admin = adminTransport;
const unlocked = ref(false);
const password = ref("");
const passwordError = ref("");
const loginLoading = ref(false);
const libraryLoading = ref(false);
const libraryError = ref("");
const editorOpen = ref(false);
const editorError = ref("");
const saving = ref(false);
const deleteOpen = ref(false);
const deleting = ref(false);
const editing = ref<PuzzleDraft | null>(null);
const query = ref("");
const items = ref<LibraryPuzzle[]>([]);
const importInput = ref<HTMLInputElement | null>(null);
const importOpen = ref(false);
const importFileName = ref("");
const importItems = ref<PuzzleImportItem[]>([]);
const importMode = ref<"upsert" | "replace">("upsert");
const importError = ref("");
const importing = ref(false);
const importSuccess = ref("");

const filteredItems = computed(() => {
  const needle = query.value.trim();
  return needle
    ? items.value.filter((item) => `${item.title}${item.surface}`.includes(needle))
    : items.value;
});
const editingExisting = computed(() => Boolean(editing.value?.id));

onMounted(async () => {
  if (!admin.hasSession()) return;
  libraryLoading.value = true;
  try {
    items.value = await admin.listPuzzles();
    unlocked.value = true;
  } catch (error) {
    passwordError.value = handleAdminError(error);
  } finally {
    libraryLoading.value = false;
  }
});

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "发生了未知错误。";
}

function handleAdminError(error: unknown): string {
  const message = messageOf(error);
  if (error instanceof AdminTransportError && error.status === 401) {
    // 管理员令牌只保存在内存中，过期后立即退回登录页重新挑战。
    admin.clearSession();
    unlocked.value = false;
    passwordError.value = message;
    editorOpen.value = false;
    deleteOpen.value = false;
  }
  return message;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function parseImportFile(text: string): PuzzleImportFile {
  const document = JSON.parse(text) as unknown;
  if (!isRecord(document) || document.schemaVersion !== 1 || !Array.isArray(document.puzzles)) {
    throw new Error("文件必须包含 schemaVersion: 1 和 puzzles 数组。");
  }
  if (!document.puzzles.length || document.puzzles.length > 1_000) {
    throw new Error("每个文件需要包含 1 至 1000 道题目。");
  }

  const ids = new Set<string>();
  const puzzles = document.puzzles.map((raw, index): PuzzleImportItem => {
    const label = `第 ${index + 1} 道题`;
    if (!isRecord(raw)) throw new Error(`${label}不是 JSON 对象。`);
    const id = typeof raw.id === "string" ? raw.id.trim() : "";
    const title = typeof raw.title === "string" ? raw.title.trim() : "";
    const surface = typeof raw.surface === "string" ? raw.surface.trim() : "";
    const truth = typeof raw.truth === "string" ? raw.truth.trim() : "";
    const keyFacts = Array.isArray(raw.keyFacts)
      ? raw.keyFacts.map((fact) => (typeof fact === "string" ? fact.trim() : ""))
      : [];

    if (!/^puzzle_[A-Za-z0-9_-]{1,73}$/.test(id)) {
      throw new Error(`${label}的 id 必须以 puzzle_ 开头，且只能包含字母、数字、下划线和连字符。`);
    }
    if (ids.has(id)) throw new Error(`${label}的 id 与文件内其他题目重复。`);
    if (!title || title.length > 80) throw new Error(`${label}的标题长度必须为 1 至 80 个字符。`);
    if (surface.length < 20 || surface.length > 800) {
      throw new Error(`${label}的汤面长度必须为 20 至 800 个字符。`);
    }
    if (truth.length < 40 || truth.length > 2_000) {
      throw new Error(`${label}的汤底长度必须为 40 至 2000 个字符。`);
    }
    if (keyFacts.length < 2 || keyFacts.length > 8 || keyFacts.some((fact) => !fact)) {
      throw new Error(`${label}必须包含 2 至 8 条非空关键事实。`);
    }
    if (new Set(keyFacts).size !== keyFacts.length) {
      throw new Error(`${label}的关键事实不能重复。`);
    }
    if (typeof raw.active !== "boolean") throw new Error(`${label}的 active 必须是布尔值。`);

    const timestamps: Pick<PuzzleImportItem, "createdAt" | "updatedAt"> = {};
    for (const field of ["createdAt", "updatedAt"] as const) {
      const value = raw[field];
      if (value !== undefined && (!Number.isInteger(value) || Number(value) < 0)) {
        throw new Error(`${label}的 ${field} 必须是非负整数。`);
      }
      if (typeof value === "number") timestamps[field] = value;
    }
    ids.add(id);
    return { id, title, surface, truth, keyFacts, active: raw.active, ...timestamps };
  });
  return { schemaVersion: 1, puzzles };
}

function openImportPicker(): void {
  importError.value = "";
  importSuccess.value = "";
  if (importInput.value) importInput.value.value = "";
  importInput.value?.click();
}

async function selectImportFile(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  try {
    const parsed = parseImportFile(await file.text());
    importFileName.value = file.name;
    importItems.value = parsed.puzzles;
    importMode.value = "upsert";
    importError.value = "";
    importOpen.value = true;
  } catch (error) {
    importError.value = error instanceof SyntaxError ? "JSON 格式不正确，请检查逗号和引号。" : messageOf(error);
  }
}

async function confirmImport(): Promise<void> {
  if (importing.value || !importItems.value.length) return;
  importing.value = true;
  importError.value = "";
  try {
    const imported = await admin.importPuzzles(importItems.value, importMode.value);
    items.value = await admin.listPuzzles();
    importSuccess.value = `已成功导入 ${imported} 道题目。`;
    importOpen.value = false;
  } catch (error) {
    importError.value = handleAdminError(error);
  } finally {
    importing.value = false;
  }
}

function closeImport(): void {
  if (!importing.value) importOpen.value = false;
}

async function unlock(): Promise<void> {
  if (!password.value || loginLoading.value) return;
  loginLoading.value = true;
  passwordError.value = "";
  try {
    await admin.login(password.value);
    libraryLoading.value = true;
    items.value = await admin.listPuzzles();
    unlocked.value = true;
    password.value = "";
  } catch (error) {
    passwordError.value = messageOf(error);
  } finally {
    loginLoading.value = false;
    libraryLoading.value = false;
  }
}

function openEditor(item?: LibraryPuzzle): void {
  editing.value = item
    ? {
        id: item.id,
        title: item.title,
        surface: item.surface,
        truth: item.truth,
        keyFactsText: item.keyFacts.join("\n"),
        active: item.active,
      }
    : {
        id: null,
        title: "",
        surface: "",
        truth: "",
        keyFactsText: "",
        active: true,
      };
  editorError.value = "";
  editorOpen.value = true;
}

function closeEditor(): void {
  if (!saving.value) editorOpen.value = false;
}

function puzzlePayload(): PuzzleWrite | null {
  if (!editing.value) return null;
  const title = editing.value.title.trim();
  const surface = editing.value.surface.trim();
  const truth = editing.value.truth.trim();
  const keyFacts = editing.value.keyFactsText
    .split(/\r?\n/)
    .map((fact) => fact.trim())
    .filter(Boolean);

  if (!title) editorError.value = "请填写内部标题。";
  else if (surface.length < 20) editorError.value = "汤面至少需要 20 个字符。";
  else if (truth.length < 40) editorError.value = "汤底至少需要 40 个字符。";
  else if (keyFacts.length < 2 || keyFacts.length > 8) {
    editorError.value = "请填写 2 至 8 条关键事实，每行一条。";
  } else if (new Set(keyFacts).size !== keyFacts.length) {
    editorError.value = "关键事实不能重复。";
  } else {
    editorError.value = "";
    return { title, surface, truth, keyFacts, active: editing.value.active };
  }
  return null;
}

async function saveItem(): Promise<void> {
  if (saving.value) return;
  const payload = puzzlePayload();
  if (!payload || !editing.value) return;

  saving.value = true;
  try {
    const saved = editing.value.id
      ? await admin.updatePuzzle(editing.value.id, payload)
      : await admin.createPuzzle(payload);
    const index = items.value.findIndex((item) => item.id === saved.id);
    if (index >= 0) items.value[index] = saved;
    else items.value.unshift(saved);
    editorOpen.value = false;
  } catch (error) {
    editorError.value = handleAdminError(error);
  } finally {
    saving.value = false;
  }
}

function requestDelete(): void {
  if (editing.value?.id) deleteOpen.value = true;
}

async function deleteItem(): Promise<void> {
  if (!editing.value?.id || deleting.value) return;
  deleting.value = true;
  libraryError.value = "";
  try {
    await admin.deletePuzzle(editing.value.id);
    items.value = items.value.filter((item) => item.id !== editing.value?.id);
    deleteOpen.value = false;
    editorOpen.value = false;
  } catch (error) {
    libraryError.value = handleAdminError(error);
  } finally {
    deleting.value = false;
  }
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
            <input
              v-model="password"
              type="password"
              autocomplete="current-password"
              placeholder="输入服务端配置的专用密码"
            />
          </label>
          <p v-if="passwordError" class="form-error">{{ passwordError }}</p>
          <button
            class="primary-button primary-button--full"
            type="submit"
            :disabled="!password || loginLoading"
          >
            <span v-if="loginLoading" class="button-spinner"></span>
            {{ loginLoading ? "正在安全验证……" : "解锁题库" }}
          </button>
        </form>
        <small>密码仅在本机参与一次性挑战计算，不会明文传输或保存。</small>
      </section>

      <template v-else>
        <header class="subpage-heading">
          <div>
            <p class="eyebrow">PRIVATE LIBRARY</p>
            <h1>私人题库</h1>
            <p>只有你可以维护这些题目；房主开局时只能随机抽取。</p>
          </div>
          <div class="library-heading-actions">
            <input
              ref="importInput"
              class="visually-hidden"
              type="file"
              accept="application/json,.json"
              @change="selectImportFile"
            />
            <button class="secondary-button" type="button" :disabled="libraryLoading" @click="openImportPicker">
              批量导入 JSON
            </button>
            <button class="primary-button" type="button" :disabled="libraryLoading" @click="openEditor()">
              新增题目
              <span>+</span>
            </button>
          </div>
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
            <span>共 {{ items.length }} 道</span>
          </div>
        </div>

        <p v-if="importSuccess" class="library-state library-state--success">{{ importSuccess }}</p>
        <p v-if="importError && !importOpen" class="library-state library-state--error">{{ importError }}</p>
        <p v-if="libraryError" class="library-state library-state--error">{{ libraryError }}</p>
        <div v-if="libraryLoading" class="library-state">
          <span class="button-spinner"></span>
          正在读取题库……
        </div>
        <section v-else-if="filteredItems.length" class="library-list">
          <article v-for="item in filteredItems" :key="item.id" class="library-card">
            <span class="library-card__status" :class="{ inactive: !item.active }"></span>
            <div>
              <small>{{ item.active ? "已启用" : "已停用" }} · {{ item.keyFacts.length }} 条关键事实</small>
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
        <div v-else class="library-empty">
          <span>✦</span>
          <h2>{{ query ? "没有匹配的题目" : "题库还是空的" }}</h2>
          <p>{{ query ? "换一个关键词试试。" : "新增第一道题，私人题库房间就可以随机抽取了。" }}</p>
        </div>
      </template>
    </main>

    <BaseModal
      :open="importOpen"
      eyebrow="IMPORT PUZZLES"
      title="批量导入私人题库"
      :description="`${importFileName} · ${importItems.length} 道题目已通过本地校验`"
      @close="closeImport"
    >
      <div class="import-options">
        <label :class="{ active: importMode === 'upsert' }">
          <input v-model="importMode" type="radio" value="upsert" />
          <span>
            <strong>合并导入</strong>
            <small>同 ID 题目更新，新 ID 题目新增，保留其他题目。</small>
          </span>
        </label>
        <label :class="{ active: importMode === 'replace' }">
          <input v-model="importMode" type="radio" value="replace" />
          <span>
            <strong>替换整个题库</strong>
            <small>删除文件中未包含的旧题目，请谨慎使用。</small>
          </span>
        </label>
      </div>
      <p v-if="importError" class="form-error">{{ importError }}</p>
      <div class="modal-actions">
        <button class="secondary-button" type="button" :disabled="importing" @click="importOpen = false">
          取消
        </button>
        <button class="primary-button" type="button" :disabled="importing" @click="confirmImport">
          <span v-if="importing" class="button-spinner"></span>
          {{ importing ? "正在写入……" : `导入 ${importItems.length} 道题目` }}
        </button>
      </div>
    </BaseModal>

    <BaseModal
      :open="editorOpen"
      wide
      eyebrow="PUZZLE EDITOR"
      :title="editingExisting ? '编辑题目' : '新增题目'"
      @close="closeEditor"
    >
      <form v-if="editing" class="dialog-form" @submit.prevent="saveItem">
        <label class="field">
          <span>内部标题</span>
          <input v-model="editing.title" maxlength="80" placeholder="方便你在题库中识别" />
        </label>
        <label class="field">
          <span>汤面</span>
          <textarea
            v-model="editing.surface"
            rows="4"
            maxlength="800"
            placeholder="玩家开局时看到的故事……"
          ></textarea>
        </label>
        <label class="field">
          <span>汤底</span>
          <textarea
            v-model="editing.truth"
            rows="6"
            maxlength="2000"
            placeholder="仅服务端与 AI 主持人可以读取……"
          ></textarea>
        </label>
        <label class="field">
          <span>关键事实</span>
          <textarea
            v-model="editing.keyFactsText"
            rows="4"
            placeholder="每行一条，填写 2 至 8 条……"
          ></textarea>
        </label>
        <label class="toggle-row">
          <span>
            <strong>允许随机抽取</strong>
            <small>停用后仍保留题目，但不会进入房间。</small>
          </span>
          <input v-model="editing.active" type="checkbox" />
          <i></i>
        </label>
        <p v-if="editorError" class="form-error">{{ editorError }}</p>
        <div class="modal-actions">
          <button
            v-if="editingExisting"
            class="ghost-button ghost-button--danger"
            type="button"
            :disabled="saving"
            @click="requestDelete"
          >
            删除题目
          </button>
          <button class="primary-button" type="submit" :disabled="saving">
            <span v-if="saving" class="button-spinner"></span>
            {{ saving ? "正在保存……" : "保存题目" }}
          </button>
        </div>
      </form>
    </BaseModal>

    <BaseModal
      :open="deleteOpen"
      eyebrow="DELETE PUZZLE"
      title="确定删除这道题吗？"
      description="删除后无法恢复；已经开始的房间不会受影响。"
      @close="deleteOpen = false"
    >
      <div class="confirm-actions">
        <button class="secondary-button" type="button" :disabled="deleting" @click="deleteOpen = false">
          取消
        </button>
        <button class="danger-button" type="button" :disabled="deleting" @click="deleteItem">
          <span v-if="deleting" class="button-spinner"></span>
          {{ deleting ? "正在删除……" : "删除题目" }}
        </button>
      </div>
    </BaseModal>
  </div>
</template>
