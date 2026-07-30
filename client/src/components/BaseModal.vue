<script setup lang="ts">
defineProps<{
  open: boolean;
  eyebrow?: string;
  title: string;
  description?: string;
  wide?: boolean;
}>();

const emit = defineEmits<{
  close: [];
}>();
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="modal-backdrop" @mousedown.self="emit('close')">
        <section
          class="modal-card"
          :class="{ 'modal-card--wide': wide }"
          role="dialog"
          aria-modal="true"
          :aria-label="title"
        >
          <button class="modal-close" type="button" aria-label="关闭" @click="emit('close')">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="m7 7 10 10M17 7 7 17" />
            </svg>
          </button>
          <p v-if="eyebrow" class="eyebrow">{{ eyebrow }}</p>
          <h2>{{ title }}</h2>
          <p v-if="description" class="modal-description">{{ description }}</p>
          <slot />
        </section>
      </div>
    </Transition>
  </Teleport>
</template>
