<template>
  <video
    ref="videoEl"
    :src="src"
    controls
    class="clip-player"
    @ended="$emit('ended')"
  ></video>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  src: { type: String, required: true },
})
defineEmits(['ended'])

const videoEl = ref(null)

watch(() => props.src, () => {
  if (videoEl.value) {
    videoEl.value.load()
  }
})
</script>

<style scoped>
.clip-player {
  width: 100%;
  max-height: 480px;
  display: block;
  background: #000;
  border-radius: 8px;
}
</style>
