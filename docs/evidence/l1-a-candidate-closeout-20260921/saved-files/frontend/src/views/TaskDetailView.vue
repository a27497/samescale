<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  downloadTaskEmbeddedSubtitle,
  probeTaskEmbeddedSubtitles,
  toReadableEmbeddedSubtitleError,
} from "../api/embeddedSubtitles";
import { requestTaskPlaybackToken, toReadablePlaybackError } from "../api/media";
import { fetchPublicRuntimeConfiguration } from "../api/runtimeConfiguration";
import { cancelTask, fetchTaskDetail, retryTask, toReadableTaskError } from "../api/task";
import CourseContentPanel from "../components/task-detail/CourseContentPanel.vue";
import CourseFilesPanel from "../components/task-detail/CourseFilesPanel.vue";
import CourseOverviewPanel from "../components/task-detail/CourseOverviewPanel.vue";
import CourseQaPanel from "../components/task-detail/CourseQaPanel.vue";
import CourseStudyPanel from "../components/task-detail/CourseStudyPanel.vue";
import CourseTechnicalPanel from "../components/task-detail/CourseTechnicalPanel.vue";
import CourseVideoAside from "../components/task-detail/CourseVideoAside.vue";
import CourseWorkspaceHeader from "../components/task-detail/CourseWorkspaceHeader.vue";
import CourseWorkspaceNav from "../components/task-detail/CourseWorkspaceNav.vue";
import type { CourseWorkspace } from "../components/task-detail/workspace";
import { useTaskEventsStore } from "../stores/taskEvents";
import { useTaskResultStore } from "../stores/taskResult";
import type { TaskDetailResponse } from "../types/task";
import { isRetryableTaskStatus } from "../utils/taskStatus";
import {
  UNKNOWN_SUBTITLE_LANGUAGE,
  subtitleLanguageForSelection,
  subtitleTrackForSelection,
} from "../utils/subtitleLanguage";

type SubtitleStatus = "none" | "loading" | "loaded" | "not_found" | "unsupported" | "failed";
type VideoAsideExpose = { seekTo: (seconds: number) => void };

const route = useRoute();
const router = useRouter();
const taskEventsStore = useTaskEventsStore();
const taskResultStore = useTaskResultStore();

const activeWorkspace = ref<CourseWorkspace>("overview");
const videoAsideRef = ref<VideoAsideExpose | null>(null);
const taskDetail = ref<TaskDetailResponse | null>(null);
const taskDetailRequestVersion = ref(0);
const cancelLoading = ref(false);
const retryLoading = ref(false);
const playbackUrl = ref("");
const playbackExpiresAt = ref("");
const playbackLoading = ref(false);
const playbackError = ref("");
const playbackRequestVersion = ref(0);
const subtitleTrackUrl = ref("");
const subtitleLanguage = ref(UNKNOWN_SUBTITLE_LANGUAGE);
const subtitleText = ref("");
const subtitleStatus = ref<SubtitleStatus>("none");
const subtitleMessage = ref("");
const subtitleRequestVersion = ref(0);
const commandVersion = ref(0);
const completedResultReloadTaskId = ref("");

const taskId = computed(() => {
  const value = route.params.taskId;
  return Array.isArray(value) ? value[0] || "" : value || "";
});
const task = computed(() => taskEventsStore.task);
const result = computed(() => taskResultStore.result);
const hasTaskId = computed(() => taskId.value.trim().length > 0);
const canCancelTask = computed(() => ["CREATED", "QUEUED", "RUNNING", "RETRYING"].includes(task.value?.status || ""));
const canRetryTask = computed(() => isRetryableTaskStatus(task.value?.status));
const isDemoMode = ref(false);

onMounted(() => {
  void loadPublicRuntimeConfiguration();
});

watch(taskId, (nextTaskId) => {
  commandVersion.value += 1;
  cancelLoading.value = false;
  retryLoading.value = false;
  taskEventsStore.connect(nextTaskId);
  void loadTaskDetail(nextTaskId);
  void taskResultStore.load(nextTaskId);
  void refreshTaskPlayback(nextTaskId);
  void refreshTaskEmbeddedSubtitles(nextTaskId);
  activeWorkspace.value = "overview";
  completedResultReloadTaskId.value = "";
}, { immediate: true });

watch(() => task.value?.status, (status) => {
  const currentTaskId = taskId.value.trim();
  if (status !== "SUCCEEDED" || !currentTaskId || completedResultReloadTaskId.value === currentTaskId) return;
  completedResultReloadTaskId.value = currentTaskId;
  void taskResultStore.load(currentTaskId);
});

onBeforeUnmount(() => {
  taskEventsStore.disconnect();
  taskResultStore.clear();
  clearTaskDetail();
  clearTaskPlayback();
  clearTaskEmbeddedSubtitles();
});

function changeWorkspace(workspace: CourseWorkspace) {
  activeWorkspace.value = workspace;
}

async function loadPublicRuntimeConfiguration() {
  try {
    isDemoMode.value = (await fetchPublicRuntimeConfiguration()).demoMode === true;
  } catch {
    // Do not show a Demo notice when the backend cannot verify the active provider mode.
    isDemoMode.value = false;
  }
}

function seekTo(startTimeMillis: number) {
  videoAsideRef.value?.seekTo(Math.max(0, startTimeMillis || 0) / 1000);
}

function reconnect() {
  taskEventsStore.reconnect();
  void loadTaskDetail(taskId.value);
  void taskResultStore.load(taskId.value);
  void refreshTaskPlayback(taskId.value);
  void refreshTaskEmbeddedSubtitles(taskId.value);
}

function clearTaskDetail() {
  taskDetailRequestVersion.value += 1;
  taskDetail.value = null;
}

async function loadTaskDetail(currentTaskId: string) {
  const normalizedTaskId = currentTaskId.trim();
  if (!normalizedTaskId) { clearTaskDetail(); return; }
  const version = taskDetailRequestVersion.value + 1;
  taskDetailRequestVersion.value = version;
  taskDetail.value = null;
  try {
    const response = await fetchTaskDetail(normalizedTaskId);
    if (version === taskDetailRequestVersion.value) taskDetail.value = response;
  } catch {
    if (version === taskDetailRequestVersion.value) taskDetail.value = null;
  }
}

function clearTaskPlayback() {
  playbackRequestVersion.value += 1;
  playbackUrl.value = "";
  playbackExpiresAt.value = "";
  playbackLoading.value = false;
  playbackError.value = "";
}

async function refreshTaskPlayback(currentTaskId = taskId.value) {
  const normalizedTaskId = currentTaskId.trim();
  if (!normalizedTaskId) { clearTaskPlayback(); return; }
  const version = playbackRequestVersion.value + 1;
  playbackRequestVersion.value = version;
  playbackLoading.value = true;
  playbackError.value = "";
  playbackUrl.value = "";
  playbackExpiresAt.value = "";
  try {
    const response = await requestTaskPlaybackToken(normalizedTaskId);
    if (version !== playbackRequestVersion.value) return;
    playbackUrl.value = response.playbackUrl;
    playbackExpiresAt.value = response.expiresAt;
  } catch (error) {
    if (version !== playbackRequestVersion.value) return;
    playbackUrl.value = "";
    playbackExpiresAt.value = "";
    playbackError.value = toReadablePlaybackError(error);
  } finally {
    if (version === playbackRequestVersion.value) playbackLoading.value = false;
  }
}

function revokeSubtitleUrl() {
  if (subtitleTrackUrl.value) {
    URL.revokeObjectURL(subtitleTrackUrl.value);
    subtitleTrackUrl.value = "";
  }
}

function clearTaskEmbeddedSubtitles(status: SubtitleStatus = "none") {
  subtitleRequestVersion.value += 1;
  subtitleText.value = "";
  subtitleLanguage.value = UNKNOWN_SUBTITLE_LANGUAGE;
  subtitleStatus.value = status;
  subtitleMessage.value = "";
  revokeSubtitleUrl();
}

async function refreshTaskEmbeddedSubtitles(currentTaskId: string) {
  const normalizedTaskId = currentTaskId.trim();
  if (!normalizedTaskId) { clearTaskEmbeddedSubtitles(); return; }
  const version = subtitleRequestVersion.value + 1;
  subtitleRequestVersion.value = version;
  subtitleStatus.value = "loading";
  subtitleMessage.value = "";
  subtitleText.value = "";
  revokeSubtitleUrl();
  try {
    const probe = await probeTaskEmbeddedSubtitles(normalizedTaskId);
    if (version !== subtitleRequestVersion.value) return;
    if (probe.status === "UNSUPPORTED") { subtitleStatus.value = "unsupported"; return; }
    if (probe.status === "NOT_FOUND" || probe.selectedStreamIndex === null) { subtitleStatus.value = "not_found"; return; }
    const selectedTrack = subtitleTrackForSelection(probe, probe.selectedStreamIndex);
    if (!selectedTrack) { subtitleStatus.value = "not_found"; return; }
    if (selectedTrack.supported === false) { subtitleStatus.value = "unsupported"; return; }
    const selectedLanguage = subtitleLanguageForSelection(probe, probe.selectedStreamIndex);
    const vttText = await downloadTaskEmbeddedSubtitle(normalizedTaskId, probe.selectedStreamIndex);
    if (version !== subtitleRequestVersion.value) return;
    subtitleText.value = vttText;
    subtitleLanguage.value = selectedLanguage;
    subtitleTrackUrl.value = URL.createObjectURL(new Blob([vttText], { type: "text/vtt;charset=utf-8" }));
    subtitleStatus.value = "loaded";
  } catch (error) {
    if (version !== subtitleRequestVersion.value) return;
    subtitleStatus.value = "failed";
    subtitleMessage.value = toReadableEmbeddedSubtitleError(error);
    subtitleText.value = "";
    revokeSubtitleUrl();
  }
}

function refreshTaskVideo() {
  void refreshTaskPlayback(taskId.value);
  void refreshTaskEmbeddedSubtitles(taskId.value);
}

async function confirmCancelTask() {
  if (!taskId.value || cancelLoading.value) return;
  const currentTaskId = taskId.value;
  const version = commandVersion.value;
  try {
    await ElMessageBox.confirm("取消后课程将停止继续处理，已生成的数据会保留。确定取消吗？", "取消处理", {
      confirmButtonText: "确认取消",
      cancelButtonText: "继续等待",
      type: "warning",
    });
  } catch { return; }
  if (version !== commandVersion.value || taskId.value !== currentTaskId) return;
  cancelLoading.value = true;
  try {
    await cancelTask(currentTaskId);
    if (version !== commandVersion.value || taskId.value !== currentTaskId) return;
    ElMessage.success("取消请求已提交");
    reconnect();
  } catch (error) {
    if (version === commandVersion.value && taskId.value === currentTaskId) ElMessage.error(toReadableTaskError(error));
  } finally {
    if (version === commandVersion.value && taskId.value === currentTaskId) cancelLoading.value = false;
  }
}

async function confirmRetryTask() {
  if (!taskId.value || retryLoading.value) return;
  const currentTaskId = taskId.value;
  const version = commandVersion.value;
  try {
    await ElMessageBox.confirm("系统会基于原视频创建新的处理任务，原失败记录会保留。确定重新处理吗？", "重新处理", {
      confirmButtonText: "重新处理",
      cancelButtonText: "取消",
      type: "warning",
    });
  } catch { return; }
  if (version !== commandVersion.value || taskId.value !== currentTaskId) return;
  retryLoading.value = true;
  try {
    const response = await retryTask(currentTaskId);
    if (version !== commandVersion.value || taskId.value !== currentTaskId) return;
    ElMessage.success("已创建新的处理任务，正在打开课程详情。");
    await router.push(`/tasks/${encodeURIComponent(response.newTaskId)}`);
  } catch (error) {
    if (version === commandVersion.value && taskId.value === currentTaskId) ElMessage.error(toReadableTaskError(error));
  } finally {
    if (version === commandVersion.value && taskId.value === currentTaskId) retryLoading.value = false;
  }
}
</script>

<template>
  <main class="course-workspace-page">
    <div class="course-workspace-page__inner">
      <CourseWorkspaceHeader
        :status="task?.status"
        :can-cancel="canCancelTask"
        :can-retry="canRetryTask"
        :refreshing="taskEventsStore.isConnecting || taskResultStore.loading"
        :cancel-loading="cancelLoading"
        :retry-loading="retryLoading"
        @refresh="reconnect"
        @cancel="confirmCancelTask"
        @retry="confirmRetryTask"
      />

      <el-alert
        v-if="isDemoMode"
        class="demo-notice"
        :closable="false"
        title="当前使用本地演示数据，未调用外部 AI 服务。"
        type="info"
        show-icon
      />

      <el-empty v-if="!hasTaskId" description="课程地址中缺少任务 ID" />
      <div v-else class="course-layout">
        <div class="course-layout__media">
          <CourseVideoAside
            :key="taskId"
            ref="videoAsideRef"
            :task="task"
            :task-detail="taskDetail"
            :connection-status="taskEventsStore.connectionStatus"
            :connection-error="taskEventsStore.errorMessage"
            :last-heartbeat-at="taskEventsStore.lastHeartbeatAt"
            :playback-url="playbackUrl"
            :playback-loading="playbackLoading"
            :playback-error="playbackError"
            :playback-expires-at="playbackExpiresAt"
            :subtitle-track-url="subtitleTrackUrl"
            :subtitle-language="subtitleLanguage"
            :subtitle-text="subtitleText"
            :subtitle-status="subtitleStatus"
            :subtitle-message="subtitleMessage"
            @refresh-video="refreshTaskVideo"
          />
        </div>

        <section class="course-layout__content" aria-label="课程学习工作台">
          <CourseWorkspaceNav :active="activeWorkspace" @change="changeWorkspace" />
          <el-alert v-if="taskResultStore.errorMessage" :closable="false" :title="taskResultStore.errorMessage" type="error" show-icon />
          <el-skeleton v-if="taskResultStore.loading && !result" :rows="6" animated />
          <KeepAlive v-else>
            <CourseOverviewPanel
              v-if="activeWorkspace === 'overview'"
              :task="task"
              :task-detail="taskDetail"
              :result="result"
              :can-retry="canRetryTask"
              :retry-loading="retryLoading"
              @navigate="changeWorkspace"
              @retry="confirmRetryTask"
            />
            <CourseContentPanel v-else-if="activeWorkspace === 'content'" :task-id="taskId" :status="task?.status" :result="result" @seek="seekTo" />
            <CourseStudyPanel v-else-if="activeWorkspace === 'study'" :task-id="taskId" :status="task?.status" :result="result" @seek="seekTo" />
            <CourseQaPanel v-else-if="activeWorkspace === 'qa'" :task-id="taskId" @seek="seekTo" />
            <CourseFilesPanel v-else-if="activeWorkspace === 'files'" :task-id="taskId" :status="task?.status" :artifacts="result?.artifacts ?? []" />
            <CourseTechnicalPanel
              v-else
              :task-id="taskId"
              :task="task"
              :task-detail="taskDetail"
              :result="result"
              :connection-status="taskEventsStore.connectionStatus"
              :last-heartbeat-at="taskEventsStore.lastHeartbeatAt"
            />
          </KeepAlive>
        </section>
      </div>
    </div>
  </main>
</template>

<style scoped>
.course-workspace-page { min-height: calc(100vh - var(--header-height)); background: var(--color-canvas); }
.course-workspace-page__inner { width: min(1360px, calc(100% - 48px)); margin: 0 auto; padding: 30px 0 64px; }
.demo-notice { margin-top: 18px; }
.course-layout { display: grid; grid-template-columns: minmax(360px, 420px) minmax(0, 1fr); gap: 24px; align-items: start; margin-top: 24px; }
.course-layout__media { position: sticky; top: calc(var(--header-height) + 24px); min-width: 0; }
.course-layout__content { display: grid; gap: 16px; min-width: 0; }
@media (max-width: 1080px) { .course-layout { grid-template-columns: minmax(320px, 370px) minmax(0, 1fr); gap: 18px; } }
@media (max-width: 1024px) { .course-workspace-page :deep(button) { min-height: 40px; } }
@media (max-width: 900px) { .course-workspace-page__inner { width: min(100% - 32px, 760px); }.course-layout { grid-template-columns: 1fr; }.course-layout__media { position: static; } }
@media (max-width: 520px) { .course-workspace-page__inner { width: min(100% - 24px, 760px); padding-top: 22px; }.course-layout { margin-top: 18px; } }
</style>
