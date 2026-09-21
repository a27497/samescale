<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import {
  downloadUploadEmbeddedSubtitle,
  probeUploadEmbeddedSubtitles,
  toReadableEmbeddedSubtitleError,
} from "../api/embeddedSubtitles";
import { requestUploadPlaybackToken, toReadablePlaybackError } from "../api/media";
import { createAnalysisTask, toReadableTaskError } from "../api/task";
import TermHelp from "../components/common/TermHelp.vue";
import VideoPlaybackCard from "../components/VideoPlaybackCard.vue";
import PageHeading from "../components/ui/PageHeading.vue";
import SectionPanel from "../components/ui/SectionPanel.vue";
import UploadFilePicker from "../components/upload/UploadFilePicker.vue";
import UploadProgress from "../components/upload/UploadProgress.vue";
import { useUploadStore } from "../stores/upload";
import { isAuthExpiredMessage } from "../utils/errorMessage";
import { formatFileSize } from "../utils/fileSize";
import {
  UNKNOWN_SUBTITLE_LANGUAGE,
  subtitleLanguageForSelection,
  subtitleTrackForSelection,
} from "../utils/subtitleLanguage";

const uploadStore = useUploadStore();
const route = useRoute();
const router = useRouter();
const TARGET_LANGUAGE_VALUE = "zh-CN";
const TARGET_LANGUAGE_LABEL = "简体中文";
const sourceLanguage = ref<"auto" | "en" | "en-us" | "en-gb" | "zh" | "zh-cn" | "zh-tw">("en");
const createTaskLoading = ref(false);
const createTaskError = ref("");
const playbackUrl = ref("");
const playbackExpiresAt = ref("");
const playbackLoading = ref(false);
const playbackError = ref("");
const playbackRequestVersion = ref(0);
const embeddedSubtitleTrackUrl = ref("");
const embeddedSubtitleLanguage = ref(UNKNOWN_SUBTITLE_LANGUAGE);
const embeddedSubtitleText = ref("");
const embeddedSubtitleStatus = ref<"none" | "loading" | "loaded" | "not_found" | "unsupported" | "failed">("none");
const embeddedSubtitleMessage = ref("");
const embeddedSubtitleRequestVersion = ref(0);

const selectedFile = computed(() => uploadStore.selected?.file ?? null);
const extensionText = computed(() => uploadStore.selected?.extension || "未选择");
const isUploadDisabled = computed(() => !uploadStore.canStart || uploadStore.isBusy);
const isResumeDisabled = computed(() => !uploadStore.canResume || uploadStore.isBusy);
const canPauseUpload = computed(() => uploadStore.phase === "checking" || uploadStore.phase === "uploading");
const hasSession = computed(() => uploadStore.uploadId.length > 0);
const completedUploadId = computed(() => uploadStore.completed?.uploadId || uploadStore.uploadId);
const completedSizeBytes = computed(() => uploadStore.completed?.sizeBytes ?? selectedFile.value?.size ?? 0);
const canCreateTask = computed(() => uploadStore.phase === "success" && completedUploadId.value.length > 0);
const uploadStatusText = computed(() => {
  switch (uploadStore.phase) {
    case "empty":
      return "请选择视频文件";
    case "ready":
      return "等待上传";
    case "hashing":
    case "creating":
    case "checking":
      return "正在检查文件";
    case "uploading":
    case "completing":
      return "正在上传";
    case "paused":
      return "上传已暂停";
    case "success":
      return "上传完成";
    case "error":
      return "上传失败";
    default:
      return uploadStore.statusText;
  }
});

watch(
  () => uploadStore.errorMessage,
  (message) => {
    if (isAuthExpiredMessage(message)) {
      void router.push({
        path: "/login",
        query: { redirect: route.fullPath },
      });
    }
  },
);

watch(
  [canCreateTask, completedUploadId],
  ([ready]) => {
    if (ready) {
      void refreshUploadPlayback();
      void refreshUploadEmbeddedSubtitles();
    } else {
      clearUploadPlayback();
      clearEmbeddedSubtitles();
    }
  },
);

onBeforeUnmount(() => {
  clearUploadPlayback();
  clearEmbeddedSubtitles();
});

function selectFile(file: File | null) {
  createTaskError.value = "";
  clearUploadPlayback();
  clearEmbeddedSubtitles();
  uploadStore.selectFile(file);
}

function resetUpload() {
  createTaskError.value = "";
  clearUploadPlayback();
  clearEmbeddedSubtitles();
  uploadStore.reset();
}

function clearUploadPlayback() {
  playbackRequestVersion.value += 1;
  playbackUrl.value = "";
  playbackExpiresAt.value = "";
  playbackLoading.value = false;
  playbackError.value = "";
}

function clearEmbeddedSubtitles(status: "none" | "not_found" | "unsupported" | "failed" = "none") {
  embeddedSubtitleRequestVersion.value += 1;
  embeddedSubtitleText.value = "";
  embeddedSubtitleLanguage.value = UNKNOWN_SUBTITLE_LANGUAGE;
  embeddedSubtitleStatus.value = status;
  embeddedSubtitleMessage.value = "";
  revokeEmbeddedSubtitleTrackUrl();
}

function revokeEmbeddedSubtitleTrackUrl() {
  if (embeddedSubtitleTrackUrl.value) {
    URL.revokeObjectURL(embeddedSubtitleTrackUrl.value);
    embeddedSubtitleTrackUrl.value = "";
  }
}

async function refreshUploadEmbeddedSubtitles() {
  const uploadId = completedUploadId.value.trim();
  if (!canCreateTask.value || !uploadId) {
    clearEmbeddedSubtitles();
    return;
  }

  const currentVersion = embeddedSubtitleRequestVersion.value + 1;
  embeddedSubtitleRequestVersion.value = currentVersion;
  embeddedSubtitleStatus.value = "loading";
  embeddedSubtitleMessage.value = "";
  embeddedSubtitleText.value = "";
  revokeEmbeddedSubtitleTrackUrl();

  try {
    const probe = await probeUploadEmbeddedSubtitles(uploadId);
    if (currentVersion !== embeddedSubtitleRequestVersion.value) {
      return;
    }
    if (probe.status === "UNSUPPORTED") {
      embeddedSubtitleStatus.value = "unsupported";
      return;
    }
    if (probe.status === "NOT_FOUND" || probe.selectedStreamIndex === null) {
      embeddedSubtitleStatus.value = "not_found";
      return;
    }
    const selectedTrack = subtitleTrackForSelection(probe, probe.selectedStreamIndex);
    if (!selectedTrack) {
      embeddedSubtitleStatus.value = "not_found";
      return;
    }
    if (selectedTrack.supported === false) {
      embeddedSubtitleStatus.value = "unsupported";
      return;
    }

    const selectedLanguage = subtitleLanguageForSelection(probe, probe.selectedStreamIndex);
    const vttText = await downloadUploadEmbeddedSubtitle(uploadId, probe.selectedStreamIndex);
    if (currentVersion !== embeddedSubtitleRequestVersion.value) {
      return;
    }
    embeddedSubtitleText.value = vttText;
    embeddedSubtitleLanguage.value = selectedLanguage;
    embeddedSubtitleTrackUrl.value = URL.createObjectURL(new Blob([vttText], { type: "text/vtt;charset=utf-8" }));
    embeddedSubtitleStatus.value = "loaded";
  } catch (error) {
    if (currentVersion !== embeddedSubtitleRequestVersion.value) {
      return;
    }
    embeddedSubtitleStatus.value = "failed";
    embeddedSubtitleMessage.value = toReadableEmbeddedSubtitleError(error);
    embeddedSubtitleText.value = "";
    revokeEmbeddedSubtitleTrackUrl();
    if (isAuthExpiredMessage(embeddedSubtitleMessage.value)) {
      await router.push({
        path: "/login",
        query: { redirect: route.fullPath },
      });
    }
  }
}

async function refreshUploadPlayback() {
  const uploadId = completedUploadId.value.trim();
  if (!canCreateTask.value || !uploadId) {
    clearUploadPlayback();
    return;
  }
  const currentVersion = playbackRequestVersion.value + 1;
  playbackRequestVersion.value = currentVersion;
  playbackLoading.value = true;
  playbackError.value = "";
  try {
    const response = await requestUploadPlaybackToken(uploadId);
    if (currentVersion !== playbackRequestVersion.value) {
      return;
    }
    playbackUrl.value = response.playbackUrl;
    playbackExpiresAt.value = response.expiresAt;
  } catch (error) {
    if (currentVersion !== playbackRequestVersion.value) {
      return;
    }
    playbackUrl.value = "";
    playbackExpiresAt.value = "";
    playbackError.value = toReadablePlaybackError(error);
    if (isAuthExpiredMessage(playbackError.value)) {
      await router.push({
        path: "/login",
        query: { redirect: route.fullPath },
      });
    }
  } finally {
    if (currentVersion === playbackRequestVersion.value) {
      playbackLoading.value = false;
    }
  }
}

function refreshUploadPreview() {
  void refreshUploadPlayback();
  void refreshUploadEmbeddedSubtitles();
}

async function createTask() {
  const uploadId = completedUploadId.value.trim();
  const language = TARGET_LANGUAGE_VALUE;
  if (!uploadId) {
    createTaskError.value = "缺少上传记录，请重新完成上传。";
    return;
  }
  if (!language) {
    createTaskError.value = "未设置目标语言，请刷新页面后重试。";
    return;
  }

  createTaskLoading.value = true;
  createTaskError.value = "";
  try {
    const task = await createAnalysisTask({ uploadId, targetLanguage: language, sourceLanguage: sourceLanguage.value });
    ElMessage.success("处理任务已创建，正在打开详情。");
    await router.push(`/tasks/${encodeURIComponent(task.taskId)}`);
  } catch (error) {
    createTaskError.value = toReadableTaskError(error);
    if (isAuthExpiredMessage(createTaskError.value)) {
      await router.push({
        path: "/login",
        query: { redirect: route.fullPath },
      });
    }
  } finally {
    createTaskLoading.value = false;
  }
}
</script>

<template>
  <main class="upload-page page-container">
    <PageHeading
      eyebrow="上传课程"
      title="上传课程视频"
      description="支持 MP4、MOV、MKV 和 WebM。上传完成后，可以生成字幕、翻译和学习笔记。"
    />

    <SectionPanel class="upload-workspace">
      <UploadFilePicker :disabled="uploadStore.isBusy" @select="selectFile" />

      <template v-if="selectedFile">
        <div class="selected-file" aria-label="已选择文件">
          <div class="selected-file__main">
            <span>已选择</span>
            <strong>{{ selectedFile.name }}</strong>
          </div>
          <div class="selected-file__meta">
            <span>{{ extensionText.toUpperCase() }}</span>
            <span>{{ formatFileSize(selectedFile.size) }}</span>
          </div>
        </div>

        <el-alert
          v-if="uploadStore.errorMessage"
          :closable="false"
          :title="uploadStore.errorMessage"
          show-icon
          type="error"
        />

        <UploadProgress
          :phase="uploadStore.phase"
          :progress-percent="uploadStore.progressPercent"
          :status-text="uploadStatusText"
          :total-chunks="uploadStore.totalChunks"
          :uploaded-chunks="uploadStore.uploadedCount"
          :uploaded-bytes="uploadStore.uploadedBytes"
          :total-bytes="uploadStore.totalBytes"
          :speed-bytes-per-second="uploadStore.speedBytesPerSecond"
          :eta-seconds="uploadStore.etaSeconds"
          :uploading-count="uploadStore.uploadingCount"
          :failed-count="uploadStore.failedCount"
          :retry-count="uploadStore.retryCount"
          :max-concurrency="3"
          :chunk-size-bytes="uploadStore.chunkSizeBytes"
          :upload-id="uploadStore.uploadId"
        />

        <section v-if="!canCreateTask" class="upload-actions" aria-label="上传操作">
          <el-button
            :disabled="isUploadDisabled"
            :loading="uploadStore.isBusy && !hasSession"
            type="primary"
            size="large"
            @click="uploadStore.startUpload()"
          >
            开始上传
          </el-button>
          <el-button v-if="canPauseUpload" @click="uploadStore.pauseUpload()">暂停</el-button>
          <el-button
            :disabled="isResumeDisabled"
            :loading="uploadStore.isBusy && hasSession"
            @click="uploadStore.resumeUpload()"
          >
            继续上传
          </el-button>
          <el-button :disabled="uploadStore.isBusy" text @click="resetUpload">重新选择</el-button>
        </section>
      </template>
    </SectionPanel>

    <SectionPanel
      v-if="canCreateTask"
      class="upload-confirmation"
      title="确认原视频"
      description="请确认下方视频就是你准备整理的课程。确认无误后即可开始。"
    >
      <VideoPlaybackCard
        title="原视频预览"
        description="这里播放刚刚上传的原始视频。"
        :playback-url="playbackUrl"
        :loading="playbackLoading"
        :error-message="playbackError"
        :expires-at="playbackExpiresAt"
        subtitle-label="原视频自带字幕"
        :subtitle-track-url="embeddedSubtitleTrackUrl"
        :subtitle-language="embeddedSubtitleLanguage"
        :subtitle-text="embeddedSubtitleText"
        :subtitle-status="embeddedSubtitleStatus"
        :subtitle-message="embeddedSubtitleMessage"
        @refresh="refreshUploadPreview"
      />

      <details class="preview-note">
        <summary>关于原视频预览 <TermHelp term="原视频预览" /></summary>
        <p>
          浏览器预览支持视频内嵌的文本软字幕轨道；图片字幕和未随视频上传的外挂字幕不会在这里显示。
        </p>
      </details>

      <el-alert
        v-if="createTaskError"
        :closable="false"
        :title="createTaskError"
        show-icon
        type="error"
      />

      <div class="course-start">
        <div>
          <strong>视频确认无误</strong>
          <p>
            将以{{ TARGET_LANGUAGE_LABEL }}处理 · {{ formatFileSize(completedSizeBytes) }}
            <TermHelp term="课程处理" />
          </p>
        </div>
        <el-select v-model="sourceLanguage" aria-label="原视频语言" style="width: 160px">
          <el-option label="英文" value="en" />
          <el-option label="中文" value="zh" />
          <el-option label="自动检测" value="auto" />
        </el-select>
        <el-button :loading="createTaskLoading" type="primary" size="large" @click="createTask">
          开始处理
        </el-button>
      </div>
    </SectionPanel>
  </main>
</template>

<style scoped>
.upload-page {
  display: grid;
  gap: 28px;
  padding-block: 46px 72px;
}

.upload-workspace {
  display: grid;
  gap: 22px;
}

.selected-file {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  padding: 16px 0;
  border-bottom: 1px solid var(--color-border);
}

.selected-file__main {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.selected-file__main span {
  color: var(--color-ink-muted);
  font-size: 12px;
}

.selected-file__main strong {
  color: var(--color-ink);
  overflow-wrap: anywhere;
}

.selected-file__meta {
  display: flex;
  flex: 0 0 auto;
  gap: 12px;
  color: var(--color-ink-muted);
  font-size: 13px;
}

.upload-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.upload-actions :deep(.el-button + .el-button) {
  margin-left: 0;
}

.upload-confirmation {
  display: grid;
  gap: 20px;
}

.preview-note {
  color: var(--color-ink-soft);
  font-size: 13px;
}

.preview-note summary {
  color: var(--color-brand-strong);
  cursor: pointer;
  font-weight: 650;
}

.preview-note p {
  margin: 10px 0 0;
  line-height: 1.65;
}

.course-start {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  padding-top: 22px;
  border-top: 1px solid var(--color-border);
}

.course-start strong {
  color: var(--color-ink);
  font-size: 17px;
}

.course-start p {
  margin: 7px 0 0;
  color: var(--color-ink-muted);
  font-size: 13px;
}

@media (max-width: 640px) {
  .upload-page {
    padding-block: 34px 52px;
  }

  .selected-file,
  .course-start {
    align-items: flex-start;
    flex-direction: column;
  }

  .upload-actions,
  .upload-actions :deep(.el-button),
  .course-start :deep(.el-button) {
    width: 100%;
  }

  .upload-actions :deep(.el-button) {
    margin-left: 0;
  }
}
</style>
