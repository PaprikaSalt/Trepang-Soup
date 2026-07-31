<script setup lang="ts">
import { isTauri } from "@tauri-apps/api/core";
import { relaunch } from "@tauri-apps/plugin-process";
import { check, type Update } from "@tauri-apps/plugin-updater";
import { computed, onMounted, ref } from "vue";

import BaseModal from "./BaseModal.vue";

const availableUpdate = ref<Update | null>(null);
const installing = ref(false);
const updateError = ref("");
const downloadedBytes = ref(0);
const totalBytes = ref<number | null>(null);

const progress = computed(() => {
  if (!totalBytes.value) return null;
  return Math.min(100, Math.round((downloadedBytes.value / totalBytes.value) * 100));
});

onMounted(async () => {
  if (!isTauri()) return;
  try {
    // The updater validates the signed GitHub Release manifest before exposing it here.
    availableUpdate.value = await check({ timeout: 12_000 });
  } catch (error) {
    console.warn("检查更新失败", error);
  }
});

async function dismiss(): Promise<void> {
  if (installing.value) return;
  await availableUpdate.value?.close();
  availableUpdate.value = null;
}

async function installUpdate(): Promise<void> {
  const update = availableUpdate.value;
  if (!update || installing.value) return;
  installing.value = true;
  updateError.value = "";
  downloadedBytes.value = 0;
  totalBytes.value = null;
  try {
    await update.downloadAndInstall((event) => {
      if (event.event === "Started") totalBytes.value = event.data.contentLength ?? null;
      else if (event.event === "Progress") downloadedBytes.value += event.data.chunkLength;
      else if (event.event === "Finished" && totalBytes.value) {
        downloadedBytes.value = totalBytes.value;
      }
    });
    await relaunch();
  } catch (error) {
    updateError.value = error instanceof Error ? error.message : "更新安装失败，请稍后重试。";
    installing.value = false;
  }
}
</script>

<template>
  <BaseModal
    :open="Boolean(availableUpdate)"
    eyebrow="UPDATE AVAILABLE"
    :title="`发现新版本 ${availableUpdate?.version || ''}`"
    description="更新包由 GitHub Releases 提供，并在安装前验证签名。"
    @close="dismiss"
  >
    <div class="update-panel">
      <p v-if="availableUpdate?.body" class="update-notes">{{ availableUpdate.body }}</p>
      <p v-else class="update-notes">这个版本包含新的功能与稳定性改进。</p>

      <div v-if="installing" class="update-progress" aria-live="polite">
        <div><i :style="{ width: `${progress ?? 12}%` }"></i></div>
        <span>{{ progress === null ? "正在下载更新……" : `已下载 ${progress}%` }}</span>
      </div>
      <p v-if="updateError" class="form-error">{{ updateError }}</p>

      <div class="modal-actions">
        <button class="secondary-button" type="button" :disabled="installing" @click="dismiss">
          稍后再说
        </button>
        <button class="primary-button" type="button" :disabled="installing" @click="installUpdate">
          <span v-if="installing" class="button-spinner"></span>
          {{ installing ? "正在更新……" : "下载并安装" }}
        </button>
      </div>
    </div>
  </BaseModal>
</template>
