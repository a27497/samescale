<script setup lang="ts">
import { computed, ref } from "vue";
import VideoPlaybackCard from "../VideoPlaybackCard.vue";
import type { TaskEventPayload, TaskConnectionStatus, TaskDetailResponse } from "../../types/task";
import { formatDurationBetween } from "../../utils/time";
import { getTaskStatusLabel, getTaskStatusTagType } from "../../utils/taskStatus";
import { connectionText, courseStageText, formatWorkspaceTime, readableTaskError } from "./workspace";

type SubtitleStatus = "none" | "loading" | "loaded" | "not_found" | "unsupported" | "failed";
type VideoPlaybackExpose = { seekTo: (seconds: number) => void };

const props = defineProps<{
  task: TaskEventPayload | null;
  taskDetail: TaskDetailResponse | null;
  connectionStatus: TaskConnectionStatus;
  connectionError: string;
  lastHeartbeatAt: string;
  playbackUrl: string;
  playbackLoading: boolean;
  playbackError: string;
  playbackExpiresAt: string;
  subtitleTrackUrl: string;
  subtitleLanguage: string;
  subtitleText: string;
  subtitleStatus: SubtitleStatus;
  subtitleMessage: string;
}>();

defineEmits<{ refreshVideo: [] }>();

const playbackRef = ref<VideoPlaybackExpose | null>(null);
const progress = computed(() => props.task?.progressPercent ?? props.taskDetail?.progressPercent ?? 0);
const stage = computed(() => courseStageText(props.task?.currentStage || props.taskDetail?.currentStage || "", props.task?.status || props.taskDetail?.status));
const errorSummary = computed(() => readableTaskError(props.task?.errorMessage || props.taskDetail?.errorMessage || ""));
const isRunning = computed(() => ["CREATED", "QUEUED", "RUNNING", "RETRYING"].includes(props.task?.status || props.taskDetail?.status || ""));
const isSucceeded = computed(() => (props.task?.status || props.taskDetail?.status) === "SUCCEEDED");

function seekTo(seconds: number) {
  playbackRef.value?.seekTo(seconds);
}

defineExpose({ seekTo });
</script>

<template>
  <aside class="course-video-aside" aria-label="课程视频和处理状态">
    <VideoPlaybackCard
      ref="playbackRef"
      title="课程视频"
      description="播放上传的原始视频。"
      :playback-url="playbackUrl"
      :loading="playbackLoading"
      :error-message="playbackError"
      :expires-at="playbackExpiresAt"
      subtitle-label="原视频字幕"
      :subtitle-track-url="subtitleTrackUrl"
      :subtitle-language="subtitleLanguage"
      :subtitle-text="subtitleText"
      :subtitle-status="subtitleStatus"
      :subtitle-message="subtitleMessage"
      @refresh="$emit('refreshVideo')"
    />

    <section class="course-status" aria-labelledby="course-status-title">
      <div class="course-status__heading">
        <div>
          <span>处理状态</span>
          <strong id="course-status-title">{{ stage }}</strong>
        </div>
        <el-tag :type="getTaskStatusTagType(task?.status || taskDetail?.status)" effect="plain">
          {{ getTaskStatusLabel(task?.status || taskDetail?.status) }}
        </el-tag>
      </div>

      <template v-if="isRunning">
        <el-progress :percentage="progress" :stroke-width="10" />
        <div class="course-status__meta">
          <span>{{ progress }}%</span>
          <span>{{ formatWorkspaceTime(task?.updatedAt || taskDetail?.updatedAt) }}</span>
        </div>
        <p>{{ connectionText(connectionStatus) }}</p>
      </template>
      <template v-else-if="isSucceeded">
        <dl>
          <div><dt>处理耗时</dt><dd>{{ formatDurationBetween(taskDetail?.startedAt, taskDetail?.finishedAt) }}</dd></div>
          <div><dt>目标语言</dt><dd>{{ taskDetail?.targetLanguage || "暂无" }}</dd></div>
        </dl>
      </template>
      <template v-else>
        <p v-if="errorSummary" class="course-status__error" role="alert">{{ errorSummary }}</p>
        <p v-else>当前课程处理已结束。</p>
      </template>

      <p v-if="connectionError" class="course-status__error" role="alert">{{ connectionError }}</p>
    </section>

    <details class="course-details">
      <summary>课程信息</summary>
      <dl>
        <div><dt>任务 ID</dt><dd>{{ taskDetail?.taskId || task?.taskId || "暂无" }}</dd></div>
        <div><dt>原始状态</dt><dd>{{ task?.status || taskDetail?.status || "暂无" }}</dd></div>
        <div><dt>原始阶段</dt><dd>{{ task?.currentStage || taskDetail?.currentStage || "暂无" }}</dd></div>
        <div><dt>目标语言</dt><dd>{{ taskDetail?.targetLanguage || "暂无" }}</dd></div>
        <div><dt>最近心跳</dt><dd>{{ formatWorkspaceTime(lastHeartbeatAt) }}</dd></div>
        <div><dt>开始时间</dt><dd>{{ formatWorkspaceTime(taskDetail?.startedAt) }}</dd></div>
        <div><dt>结束时间</dt><dd>{{ formatWorkspaceTime(taskDetail?.finishedAt) }}</dd></div>
      </dl>
    </details>
  </aside>
</template>

<style scoped>
.course-video-aside { display: grid; gap: 16px; min-width: 0; }
.course-status, .course-details { border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface); box-shadow: var(--shadow-low); }
.course-status { display: grid; gap: 14px; padding: 18px; }
.course-status__heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
.course-status__heading > div { display: grid; gap: 4px; }
.course-status__heading span, .course-status__meta, .course-status p, dt { color: var(--color-ink-soft); font-size: 13px; }
.course-status__heading strong { color: var(--color-ink); font-size: 17px; }
.course-status__meta { display: flex; justify-content: space-between; gap: 12px; }
.course-status p { margin: 0; }
.course-status__error { color: var(--color-danger, #a33a3a) !important; }
dl { display: grid; gap: 10px; margin: 0; }
dl div { display: flex; justify-content: space-between; gap: 12px; }
dt, dd { margin: 0; }
dd { color: var(--color-ink); text-align: right; overflow-wrap: anywhere; }
.course-details { padding: 0 18px; }
.course-details summary { padding: 16px 0; color: var(--color-ink); font-weight: 700; cursor: pointer; }
.course-details dl { padding: 0 0 18px; }
</style>
