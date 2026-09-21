<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { parseVttCues } from "../utils/vtt";
import { formatApiTimestamp } from "../utils/time";
import { normalizeSubtitleLanguage } from "../utils/subtitleLanguage";

type SubtitleStatus = "none" | "loading" | "loaded" | "not_found" | "unsupported" | "failed";

const props = defineProps<{
  title: string;
  description: string;
  playbackUrl: string;
  loading: boolean;
  errorMessage: string;
  expiresAt?: string;
  subtitleTrackUrl?: string;
  subtitleLanguage?: string;
  subtitleLabel?: string;
  subtitleText?: string;
  subtitleStatus?: SubtitleStatus;
  subtitleMessage?: string;
}>();

defineEmits<{
  refresh: [];
}>();

const currentTime = ref(0);
const videoRef = ref<HTMLVideoElement | null>(null);
const pendingSeekSeconds = ref<number | null>(null);
const subtitleCues = computed(() => parseVttCues(props.subtitleText || ""));
const activeSubtitleText = computed(() => {
  const cue = subtitleCues.value.find(
    (item) => currentTime.value >= item.start && currentTime.value <= item.end,
  );
  return cue?.text ?? "";
});
const resolvedSubtitleLabel = computed(() => props.subtitleLabel || "原视频自带字幕");
const resolvedSubtitleLanguage = computed(() => normalizeSubtitleLanguage(props.subtitleLanguage));
const resolvedSubtitleStatus = computed<SubtitleStatus>(() => props.subtitleStatus || "none");
const subtitleStatusText = computed(() => {
  if (props.subtitleMessage) {
    return props.subtitleMessage;
  }
  switch (resolvedSubtitleStatus.value) {
    case "loading":
      return `${resolvedSubtitleLabel.value}：检测中`;
    case "loaded":
      return `${resolvedSubtitleLabel.value}：已加载`;
    case "not_found":
      return `${resolvedSubtitleLabel.value}：未检测到`;
    case "unsupported":
      return `${resolvedSubtitleLabel.value}：暂不支持该字幕格式`;
    case "failed":
      return `${resolvedSubtitleLabel.value}加载失败`;
    default:
      return `${resolvedSubtitleLabel.value}：未检测到`;
  }
});

watch(
  () => props.playbackUrl,
  () => {
    currentTime.value = 0;
  },
);

function updateCurrentTime(event: Event) {
  currentTime.value = (event.currentTarget as HTMLVideoElement).currentTime;
}

function seekTo(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return;
  pendingSeekSeconds.value = seconds;
  if (videoRef.value && videoRef.value.readyState > 0) applyPendingSeek();
}

function handleLoadedMetadata(event: Event) {
  updateCurrentTime(event);
  applyPendingSeek();
}

function applyPendingSeek() {
  if (!videoRef.value || pendingSeekSeconds.value === null) return;
  videoRef.value.currentTime = pendingSeekSeconds.value;
  pendingSeekSeconds.value = null;
  const playResult = videoRef.value.play();
  if (playResult) void playResult.catch(() => undefined);
}

defineExpose({
  seekTo,
});
</script>

<template>
  <section class="video-card" aria-label="视频播放">
    <div class="video-card__header">
      <div>
        <h2>{{ title }}</h2>
        <p>{{ description }}</p>
      </div>
      <el-button :loading="loading" @click="$emit('refresh')">刷新播放链接</el-button>
    </div>

    <el-skeleton v-if="loading && !playbackUrl" :rows="3" animated />

    <el-alert
      v-if="errorMessage"
      :closable="false"
      :title="errorMessage"
      show-icon
      type="warning"
    />

    <div v-if="playbackUrl" class="video-card__player-shell">
      <video
      v-if="playbackUrl"
      ref="videoRef"
      class="course-video-player"
      :src="playbackUrl"
      controls
      preload="metadata"
      @loadedmetadata="handleLoadedMetadata"
      @seeked="updateCurrentTime"
      @timeupdate="updateCurrentTime"
    >
        <track
          v-if="subtitleTrackUrl"
          kind="subtitles"
          :src="subtitleTrackUrl"
          :srclang="resolvedSubtitleLanguage"
          :label="resolvedSubtitleLabel"
          default
        />
        当前浏览器可能不支持该视频编码，建议上传 H.264 MP4 或 WebM。
      </video>
      <div v-if="activeSubtitleText" class="video-card__subtitle-overlay" aria-live="polite">
        {{ activeSubtitleText }}
      </div>
    </div>

    <p
      class="video-card__subtitle"
      :class="`video-card__subtitle--${resolvedSubtitleStatus}`"
    >
      {{ subtitleStatusText }}
    </p>

    <p v-if="expiresAt" class="video-card__expiry">
      播放链接有效期至 {{ formatApiTimestamp(expiresAt) }}
    </p>
  </section>
</template>

<style scoped>
.video-card {
  display: grid;
  gap: 14px;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.video-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.video-card h2 {
  margin: 0;
  color: var(--color-ink);
  font-size: 18px;
  line-height: 1.25;
}

.video-card p {
  margin: 8px 0 0;
  color: var(--color-ink-soft);
  line-height: 1.6;
}

.video-card__player-shell {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-sm);
  background: var(--color-ink);
}

.course-video-player {
  display: block;
  width: 100%;
  max-height: 62vh;
  background: var(--color-ink);
}

.video-card__subtitle-overlay {
  position: absolute;
  right: 18px;
  bottom: 54px;
  left: 18px;
  max-width: calc(100% - 36px);
  margin: 0 auto;
  padding: 8px 12px;
  border-radius: 6px;
  background: rgb(17 24 39 / 78%);
  color: #ffffff;
  font-size: 16px;
  font-weight: 650;
  line-height: 1.5;
  text-align: center;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  pointer-events: none;
}

.video-card__subtitle {
  margin: 0;
  color: var(--color-ink-soft);
  font-size: 13px;
  line-height: 1.5;
}

.video-card__subtitle--loaded {
  color: var(--color-brand);
}

.video-card__subtitle--loading {
  color: var(--color-brand);
}

.video-card__subtitle--not_found,
.video-card__subtitle--none {
  color: var(--color-ink-muted);
}

.video-card__subtitle--unsupported,
.video-card__subtitle--failed {
  color: #b45309;
}

.video-card__expiry {
  margin: 0;
  color: var(--color-ink-muted);
  font-size: 12px;
}

@media (max-width: 720px) {
  .video-card__header {
    flex-direction: column;
  }

  .video-card__header :deep(.el-button) {
    width: 100%;
    margin-left: 0;
  }

  .video-card__subtitle-overlay {
    right: 10px;
    bottom: 48px;
    left: 10px;
    max-width: calc(100% - 20px);
    font-size: 14px;
  }
}
</style>
