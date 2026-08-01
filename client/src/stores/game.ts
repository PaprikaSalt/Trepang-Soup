import { computed, ref } from "vue";
import { defineStore } from "pinia";

import { SERVER_URL } from "../config/server";
import { clearSession, getClientInstanceId, loadSession, saveSession } from "../persistence/session";
import type {
  EventType,
  PersistedSession,
  ProtocolDifficulty,
  ProtocolDiscussion,
  ProtocolPlayer,
  ProtocolPuzzleStyle,
  ProtocolQuestion,
  ProtocolRematchState,
  ProtocolSettlement,
  RoomSnapshotPayload,
  ServerEvent,
  SnapshotTimelineEntry,
  TransportStatus,
} from "../protocol/types";
import { ServerTransport, TransportError } from "../transport/ServerTransport";
import type {
  DiscussionMessage,
  LocalHistoryEntry,
  Player,
  Puzzle,
  Question,
  RematchState,
  RoomConfig,
  RoomStage,
  Settlement,
  TimelineItem,
} from "../types/game";

const PROFILE_KEY = "trepang-soup.profile";
const HISTORY_KEY = "trepang-soup.history";
const TRANSPORT_MODE = import.meta.env.VITE_TRANSPORT_MODE === "mock" ? "mock" : "server";
const RECONNECT_DELAYS = [1_000, 2_000, 4_000, 8_000, 15_000] as const;
const sleep = (duration: number) =>
  new Promise<void>((resolve) => window.setTimeout(resolve, duration));

export type ConclusionSubmissionResult =
  | { status: "settled" }
  | { status: "confirmation_required"; missingDetailCount: number; scorePenalty: number }
  | { status: "continue" }
  | { status: "rejected" };

const MOCK_PUZZLE: Puzzle = {
  id: "mock-dorm-light",
  title: "门缝里的光",
  surface:
    "凌晨，林夏回到宿舍，发现门缝里透着光。她没有敲门，而是在门口大声抱怨钥匙丢了，随后躲进楼梯间报警。几分钟后，她确认自己救了室友。为什么？",
  truth:
    "室友本应独自在宿舍休息，却提前和林夏约定：若遇到危险，就用台灯连续闪三次。林夏从门缝看见灯光正在重复闪烁，意识到屋内还有威胁室友的人。她故意大声说钥匙丢了，让屋内的人相信她无法进入，再躲开视线报警。警方及时赶到并控制了闯入者。",
  keyFacts: ["灯光是求救信号", "屋内存在威胁室友的人", "抱怨钥匙丢了是在伪装", "报警是预先计划后的行动"],
};

const PLAYER_COLORS = ["#d7a95b", "#7fb2c7", "#b492ca", "#87b69a", "#d48f82"];
const TO_PROTOCOL_DIFFICULTY: Record<RoomConfig["difficulty"], ProtocolDifficulty> = {
  新手: "beginner",
  标准: "standard",
  烧脑: "hard",
};
const FROM_PROTOCOL_DIFFICULTY: Record<ProtocolDifficulty, RoomConfig["difficulty"]> = {
  beginner: "新手",
  standard: "标准",
  hard: "烧脑",
};
const TO_PROTOCOL_STYLE: Record<RoomConfig["style"], ProtocolPuzzleStyle> = {
  轻松日常: "light_daily",
  经典悬疑: "classic_mystery",
  暗黑惊悚: "dark_thriller",
  荒诞幽默: "absurd_humor",
};
const FROM_PROTOCOL_STYLE: Record<ProtocolPuzzleStyle, RoomConfig["style"]> = {
  light_daily: "轻松日常",
  classic_mystery: "经典悬疑",
  dark_thriller: "暗黑惊悚",
  absurd_humor: "荒诞幽默",
};

function id(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function loadJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "发生了未知错误。";
}

function accentFor(playerId: string, index = 0): string {
  let hash = 0;
  for (const character of playerId) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return PLAYER_COLORS[(hash + index) % PLAYER_COLORS.length];
}

function mapPlayer(player: ProtocolPlayer, index = 0): Player {
  return {
    ...player,
    accent: accentFor(player.id, index),
  };
}

function mapQuestion(question: ProtocolQuestion): Question {
  return { ...question };
}

function mapDiscussion(discussion: ProtocolDiscussion): DiscussionMessage {
  return { ...discussion };
}

function mapSettlement(settlement: ProtocolSettlement): Settlement {
  return {
    score: settlement.score,
    grade: settlement.grade,
    summary: settlement.summary,
    awards: settlement.awards.map((award) => ({
      title: award.title,
      recipient: award.recipientName,
      reason: award.reason,
    })),
    endedAt: settlement.endedAt,
    gaveUp: settlement.gaveUp,
    missingDetailCount: settlement.missingDetailCount ?? 0,
    detailPenalty: settlement.detailPenalty ?? 0,
  };
}

function mapRematch(value: ProtocolRematchState): RematchState {
  return {
    status: value.status,
    eligiblePlayerIds: [...value.eligiblePlayerIds],
    acceptedPlayerIds: [...value.acceptedPlayerIds],
  };
}

function timelineFromEvent(
  eventId: number,
  eventType: EventType,
  createdAt: number,
  payload: Record<string, unknown>,
): TimelineItem | null {
  if (eventType === "room.started" || eventType === "room.restarted") {
    return {
      id: `event-${eventId}`,
      kind: "system",
      createdAt,
      title: "推理开始",
      content: "主持人已经端上汤面。讨论可以天马行空，正式问题会按顺序回答。",
    };
  }
  if (eventType === "question.answered") {
    const question = payload.question as ProtocolQuestion | undefined;
    return question
      ? {
          id: `event-${eventId}`,
          kind: "qa",
          createdAt,
          question: mapQuestion(question),
        }
      : null;
  }
  if (eventType === "hint.created") {
    return {
      id: `event-${eventId}`,
      kind: "hint",
      createdAt,
      actorName: String(payload.requestedByName || "玩家"),
      title: `公共提示 · 第 ${Number(payload.hintNumber || 1)} 次`,
      content: String(payload.content || ""),
    };
  }
  if (eventType === "conclusion.close" || eventType === "conclusion.rejected") {
    return {
      id: `event-${eventId}`,
      kind: "system",
      createdAt,
      title: "结案反馈",
      content: String(payload.feedback || "主持人请大家继续补全推理。"),
    };
  }
  return null;
}

function mockAnswer(content: string): Pick<Question, "answer" | "answerType"> {
  const normalized = content.replace(/\s/g, "");
  if (/灯|光|闪|信号/.test(normalized)) {
    return { answer: "是。灯光不是普通的照明，它确实在向林夏传递信息。", answerType: "yes" };
  }
  if (/室友.*危险|绑架|挟持|闯入|坏人/.test(normalized)) {
    return { answer: "基本正确。室友正处在危险之中，而且屋内还有另一个人。", answerType: "partial" };
  }
  if (/钥匙.*丢|假装|故意.*抱怨|骗/.test(normalized)) {
    return { answer: "是。她并没有真的丢钥匙，那句话是说给屋里的人听的。你们靠近关键了。", answerType: "yes" };
  }
  if (/室友.*死|尸体|鬼|灵异/.test(normalized)) {
    return { answer: "否。室友还活着，也没有灵异因素。先别急着把寝室变成鬼片片场。", answerType: "no" };
  }
  return { answer: "无关。这个方向暂时不能帮助你们解释她为什么故意不进门。", answerType: "irrelevant" };
}

export const useGameStore = defineStore("game", () => {
  const savedProfile = loadJson<{ nickname: string }>(PROFILE_KEY, { nickname: "" });
  const nickname = ref(savedProfile.nickname);
  const roomCode = ref("");
  const roomId = ref("");
  const stage = ref<RoomStage>("lobby");
  const roomConfig = ref<RoomConfig>({
    source: "ai",
    difficulty: "新手",
    style: "经典悬疑",
  });
  const selfId = ref(id("self"));
  const players = ref<Player[]>([]);
  const puzzle = ref<Puzzle>({ ...MOCK_PUZZLE });
  const questions = ref<Question[]>([]);
  const timeline = ref<TimelineItem[]>([]);
  const discussions = ref<DiscussionMessage[]>([]);
  const hintCount = ref(0);
  const settlement = ref<Settlement | null>(null);
  const rematch = ref<RematchState | null>(null);
  const roundNumber = ref(1);
  const processingQueue = ref(false);
  const history = ref<LocalHistoryEntry[]>(loadJson<LocalHistoryEntry[]>(HISTORY_KEY, []));
  const connectionStatus = ref<TransportStatus>(TRANSPORT_MODE === "mock" ? "connected" : "idle");
  const lastError = ref("");
  const lastEventId = ref(0);
  let roomRevision = 0;
  let activeSession: PersistedSession | null = null;
  let autoReconnectEnabled = false;
  let reconnectGeneration = 0;
  let reconnectPromise: Promise<void> | null = null;

  const transport = new ServerTransport(SERVER_URL);
  transport.onStatus((status) => {
    if (
      status === "disconnected" &&
      autoReconnectEnabled &&
      activeSession &&
      stage.value !== "closed"
    ) {
      connectionStatus.value = "reconnecting";
      void reconnectRoom();
      return;
    }
    connectionStatus.value = status;
    if (status === "connected") autoReconnectEnabled = true;
  });
  transport.onEvent(applyServerEvent);

  const self = computed(() => players.value.find((player) => player.id === selfId.value));
  const isHost = computed(() => self.value?.isHost ?? false);
  const isServerMode = computed(() => TRANSPORT_MODE === "server");
  const onlineCount = computed(() => players.value.filter((player) => player.online).length);
  const pendingQuestions = computed(() =>
    questions.value.filter((question) => question.status === "queued" || question.status === "thinking"),
  );
  const connectionLabel = computed(() => {
    if (TRANSPORT_MODE === "mock") return "本地模拟服务已连接";
    const labels: Record<TransportStatus, string> = {
      idle: "等待连接后端服务",
      checking: "正在检查后端服务",
      available: "游戏服务器已连接",
      connecting: "正在连接多人房间",
      reconnecting: "连接中断，正在自动恢复房间",
      connected: "游戏服务器已连接",
      disconnected: "与房间的连接已断开",
      error: "后端服务暂时不可用",
    };
    return labels[connectionStatus.value];
  });

  function persistProfile(): void {
    window.localStorage.setItem(PROFILE_KEY, JSON.stringify({ nickname: nickname.value }));
  }

  function persistHistory(): void {
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify(history.value));
  }

  function updatePersistedEventId(): void {
    if (!activeSession) return;
    activeSession = { ...activeSession, lastEventId: lastEventId.value };
    saveSession(activeSession);
  }

  function isTerminalSessionError(error: unknown): boolean {
    if (!(error instanceof TransportError)) return false;
    return ["HTTP_401", "HTTP_404", "HTTP_410", "SESSION_INVALID", "ROOM_NOT_FOUND"].includes(
      error.code,
    );
  }

  function cancelReconnect(): void {
    reconnectGeneration += 1;
    reconnectPromise = null;
    autoReconnectEnabled = false;
  }

  async function reconnectRoom(): Promise<void> {
    if (TRANSPORT_MODE !== "server" || !activeSession || stage.value === "closed") return;
    if (reconnectPromise) return reconnectPromise;

    const generation = reconnectGeneration;
    reconnectPromise = (async () => {
      for (let attempt = 0; attempt < RECONNECT_DELAYS.length; attempt += 1) {
        connectionStatus.value = "reconnecting";
        const delay = RECONNECT_DELAYS[attempt];
        lastError.value =
          attempt === 0
            ? "连接意外中断，正在恢复房间状态……"
            : `自动重连尚未成功，${delay / 1_000} 秒后再次尝试。`;
        await sleep(delay);

        if (generation !== reconnectGeneration || !activeSession || stage.value === "closed") {
          return;
        }

        try {
          const previousSession: PersistedSession = activeSession;
          const resumed = await transport.resumeSession(previousSession);
          if (generation !== reconnectGeneration) return;

          // Resume rotates the token. Persist it before opening WebSocket so a
          // failed socket handshake can still be retried with the newest token.
          activeSession = {
            roomId: resumed.roomId,
            inviteCode: previousSession.inviteCode,
            playerId: resumed.playerId,
            sessionToken: resumed.sessionToken,
            expiresAt: resumed.expiresAt,
            lastEventId: 0,
          };
          saveSession(activeSession);
          roomId.value = activeSession.roomId;
          roomCode.value = activeSession.inviteCode;
          selfId.value = activeSession.playerId;
          await transport.connect(activeSession);
          if (generation !== reconnectGeneration) {
            transport.disconnect();
            return;
          }
          lastError.value = "";
          return;
        } catch (error) {
          if (generation !== reconnectGeneration) return;
          if (isTerminalSessionError(error)) {
            clearSession();
            activeSession = null;
            autoReconnectEnabled = false;
            connectionStatus.value = "error";
            lastError.value = "房间会话已失效，请返回首页后重新加入。";
            return;
          }
        }
      }

      connectionStatus.value = "error";
      lastError.value = "网络仍然不可用。房间记录已保留，重新进入页面即可再次恢复。";
    })().finally(() => {
      if (generation === reconnectGeneration) reconnectPromise = null;
    });

    return reconnectPromise;
  }

  function recoverFromEventGap(): void {
    if (!activeSession || reconnectPromise) return;
    lastError.value = "检测到房间消息缺口，正在重新同步完整状态……";
    connectionStatus.value = "reconnecting";
    // A fresh snapshot is safer than applying later events on incomplete state.
    transport.disconnect();
    void reconnectRoom();
  }

  function resetRoom(): void {
    roomRevision += 1;
    questions.value = [];
    timeline.value = [];
    discussions.value = [];
    hintCount.value = 0;
    settlement.value = null;
    rematch.value = null;
    roundNumber.value = 1;
    processingQueue.value = false;
    lastEventId.value = 0;
    lastError.value = "";
  }

  function resetRoundState(): void {
    roomRevision += 1;
    questions.value = [];
    timeline.value = [];
    discussions.value = [];
    hintCount.value = 0;
    settlement.value = null;
    rematch.value = null;
    processingQueue.value = false;
    lastError.value = "";
  }

  function makePlayers(selfNickname: string, host: boolean): Player[] {
    const now = Date.now();
    return [
      {
        id: selfId.value,
        nickname: selfNickname,
        online: true,
        isHost: host,
        accent: PLAYER_COLORS[0],
        joinedAt: now,
      },
      {
        id: "mock-player-moon",
        nickname: "月半",
        online: true,
        isHost: !host,
        accent: PLAYER_COLORS[1],
        joinedAt: now - 5000,
      },
      {
        id: "mock-player-seven",
        nickname: "小七",
        online: true,
        isHost: false,
        accent: PLAYER_COLORS[2],
        joinedAt: now - 3000,
      },
      {
        id: "mock-player-pine",
        nickname: "松子",
        online: true,
        isHost: false,
        accent: PLAYER_COLORS[3],
        joinedAt: now - 1000,
      },
    ];
  }

  async function checkServer(): Promise<void> {
    if (TRANSPORT_MODE === "mock") {
      connectionStatus.value = "connected";
      return;
    }
    try {
      await transport.healthCheck();
      lastError.value = "";
    } catch (error) {
      lastError.value = errorMessage(error);
    }
  }

  async function createRoom(profileName: string, config: RoomConfig): Promise<string> {
    nickname.value = profileName.trim();
    persistProfile();
    resetRoom();
    roomConfig.value = config;

    if (TRANSPORT_MODE === "mock") {
      roomCode.value = "N7K4WM";
      roomId.value = "mock-room";
      players.value = makePlayers(nickname.value, true);
      stage.value = "lobby";
      return roomCode.value;
    }

    cancelReconnect();
    transport.disconnect();
    try {
      const admission = await transport.createRoom({
        nickname: nickname.value,
        source: config.source,
        difficulty: config.source === "ai" ? TO_PROTOCOL_DIFFICULTY[config.difficulty] : null,
        style: config.source === "ai" ? TO_PROTOCOL_STYLE[config.style] : null,
      });
      activeSession = { ...admission, lastEventId: 0 };
      saveSession(activeSession);
      roomId.value = admission.roomId;
      roomCode.value = admission.inviteCode;
      selfId.value = admission.playerId;
      await transport.connect(activeSession);
      return admission.inviteCode;
    } catch (error) {
      lastError.value = errorMessage(error);
      throw error;
    }
  }

  async function joinRoom(profileName: string, code: string): Promise<string> {
    nickname.value = profileName.trim();
    persistProfile();
    resetRoom();

    if (TRANSPORT_MODE === "mock") {
      roomCode.value = code.trim().toUpperCase();
      roomId.value = "mock-room";
      roomConfig.value = { source: "ai", difficulty: "新手", style: "经典悬疑" };
      players.value = makePlayers(nickname.value, false);
      stage.value = "lobby";
      return roomCode.value;
    }

    cancelReconnect();
    transport.disconnect();
    try {
      const admission = await transport.joinRoom({
        nickname: nickname.value,
        inviteCode: code.trim().toUpperCase(),
        clientInstanceId: getClientInstanceId(),
      });
      activeSession = { ...admission, lastEventId: 0 };
      saveSession(activeSession);
      roomId.value = admission.roomId;
      roomCode.value = admission.inviteCode;
      selfId.value = admission.playerId;
      await transport.connect(activeSession);
      return admission.inviteCode;
    } catch (error) {
      lastError.value = errorMessage(error);
      throw error;
    }
  }

  async function ensureRoom(): Promise<void> {
    if (TRANSPORT_MODE === "mock") {
      ensureDemoRoom();
      return;
    }
    if (roomId.value && connectionStatus.value === "connected") return;
    if (reconnectPromise) {
      await reconnectPromise;
      if (connectionStatus.value === "connected") return;
    }

    const stored = loadSession();
    if (!stored) throw new TransportError("没有可恢复的房间，请重新加入。", "NO_SESSION");
    cancelReconnect();
    try {
      const resumed = await transport.resumeSession(stored);
      activeSession = {
        roomId: resumed.roomId,
        inviteCode: stored.inviteCode,
        playerId: resumed.playerId,
        sessionToken: resumed.sessionToken,
        expiresAt: resumed.expiresAt,
        // Public room state is not persisted, so force a complete snapshot after app restart.
        lastEventId: 0,
      };
      saveSession(activeSession);
      roomId.value = activeSession.roomId;
      roomCode.value = activeSession.inviteCode;
      selfId.value = activeSession.playerId;
      await transport.connect(activeSession);
    } catch (error) {
      if (isTerminalSessionError(error)) {
        clearSession();
        activeSession = null;
      }
      lastError.value = errorMessage(error);
      throw error;
    }
  }

  function ensureDemoRoom(): void {
    if (roomCode.value) return;
    nickname.value ||= "海盐";
    roomCode.value = "N7K4WM";
    roomId.value = "mock-room";
    players.value = makePlayers(nickname.value, true);
    stage.value = "lobby";
  }

  async function startGame(): Promise<void> {
    if (TRANSPORT_MODE === "server") {
      await runCommand("room.start", {}, ["room.started"]);
      return;
    }
    mockStartGame();
  }

  function mockStartGame(): void {
    stage.value = "playing";
    timeline.value = [
      {
        id: id("system"),
        kind: "system",
        createdAt: Date.now(),
        title: "推理开始",
        content: "主持人已经端上汤面。讨论可以天马行空，正式问题会按顺序回答。",
      },
    ];
    discussions.value = [
      {
        id: id("discussion"),
        authorId: "mock-player-moon",
        authorName: "月半",
        content: "我先盯住“为什么要大声说钥匙丢了”，感觉是故意给谁听的。",
        createdAt: Date.now() - 60_000,
      },
      {
        id: id("discussion"),
        authorId: "mock-player-seven",
        authorName: "小七",
        content: "门缝里的光也怪，室友如果睡了为什么还亮着？",
        createdAt: Date.now() - 28_000,
      },
    ];
  }

  async function sendDiscussion(content: string): Promise<void> {
    const clean = content.trim();
    if (!clean) return;
    if (TRANSPORT_MODE === "server") {
      await runCommand("discussion.send", { content: clean }, ["discussion.created"]);
      return;
    }
    discussions.value.push({
      id: id("discussion"),
      authorId: selfId.value,
      authorName: nickname.value,
      content: clean,
      createdAt: Date.now(),
    });
  }

  async function submitQuestion(content: string): Promise<void> {
    const clean = content.trim();
    if (!clean) return;
    if (TRANSPORT_MODE === "server") {
      await runCommand(
        "question.submit",
        { clientQuestionId: id("local-question"), content: clean },
        ["question.queued"],
      );
      return;
    }
    questions.value.push({
      id: id("question"),
      authorId: selfId.value,
      authorName: nickname.value,
      content: clean,
      createdAt: Date.now(),
      status: "queued",
    });
    void processMockQueue();
  }

  async function processMockQueue(): Promise<void> {
    if (processingQueue.value) return;
    processingQueue.value = true;
    const activeRevision = roomRevision;
    while (true) {
      const next = questions.value.find((question) => question.status === "queued");
      if (!next) break;
      next.status = "thinking";
      await sleep(1_400);
      if (activeRevision !== roomRevision) break;
      Object.assign(next, mockAnswer(next.content), { status: "answered" as const });
      timeline.value.push({
        id: id("qa"),
        kind: "qa",
        createdAt: Date.now(),
        question: { ...next },
      });
      await sleep(250);
    }
    if (activeRevision === roomRevision) processingQueue.value = false;
  }

  async function removeQuestion(questionId: string): Promise<void> {
    if (TRANSPORT_MODE === "server") {
      await runCommand("question.cancel", { questionId }, ["question.cancelled"]);
      return;
    }
    const index = questions.value.findIndex(
      (question) =>
        question.id === questionId && question.authorId === selfId.value && question.status === "queued",
    );
    if (index >= 0) questions.value.splice(index, 1);
  }

  async function requestHint(): Promise<void> {
    if (TRANSPORT_MODE === "server") {
      const event = await runCommand("hint.request", {}, ["hint.created", "hint.failed"], 30_000);
      if (event.type === "hint.failed") throw new TransportError("主持人暂时无法整理提示。");
      return;
    }
    const requestor = nickname.value;
    hintCount.value += 1;
    timeline.value.push({
      id: id("system"),
      kind: "system",
      createdAt: Date.now(),
      title: `${requestor} 举起了白旗`,
      content: "主持人正在把散落的线索重新摆上桌面……",
    });
    await sleep(1_200);
    timeline.value.push({
      id: id("hint"),
      kind: "hint",
      createdAt: Date.now(),
      actorName: requestor,
      title: `公共提示 · 第 ${hintCount.value} 次`,
      content:
        "目前可以确认：林夏并非粗心忘带钥匙，她在刻意让屋里的人相信自己进不去。把“门缝里的光”当作一种交流方式，再想想室友为什么不能直接开口求救。",
    });
  }

  async function submitConclusion(
    content: string,
    acceptDetailPenalty = false,
  ): Promise<ConclusionSubmissionResult> {
    if (TRANSPORT_MODE === "server") {
      // 默认提交不携带新字段，保证服务器滚动升级期间仍能兼容 1.2.x。
      const payload = acceptDetailPenalty
        ? { content: content.trim(), acceptDetailPenalty: true }
        : { content: content.trim() };
      const event = await runCommand(
        "conclusion.submit",
        payload,
        [
          "game.settled",
          "conclusion.confirmation_required",
          "conclusion.close",
          "conclusion.rejected",
        ],
        60_000,
      );
      if (event.type === "game.settled") return { status: "settled" };
      if (event.type === "conclusion.confirmation_required") {
        return {
          status: "confirmation_required",
          missingDetailCount: Number(event.payload.missingDetailCount || 0),
          scorePenalty: Number(event.payload.scorePenalty || 0),
        };
      }
      return { status: event.type === "conclusion.rejected" ? "rejected" : "continue" };
    }
    await sleep(900);
    const normalized = content.replace(/\s/g, "");
    const coreCovered = /危险|挟持|绑架|闯入|歹徒|坏人/.test(normalized);
    if (!coreCovered) return { status: "continue" };
    const missingDetailCount = Number(!/灯|闪|信号|求救/.test(normalized)) +
      Number(!/假装|故意|骗|伪装|钥匙/.test(normalized));
    const detailPenalty = missingDetailCount * 6;
    if (missingDetailCount >= 2 && !acceptDetailPenalty) {
      return { status: "confirmation_required", missingDetailCount, scorePenalty: detailPenalty };
    }
    finishGame(false, detailPenalty, missingDetailCount);
    return { status: "settled" };
  }

  async function giveUp(): Promise<void> {
    if (TRANSPORT_MODE === "server") {
      // The server asks AI to review the full round before publishing all three awards.
      await runCommand("conclusion.give_up", {}, ["game.settled"], 60_000);
      return;
    }
    finishGame(true);
  }

  function finishGame(gaveUp: boolean, detailPenalty = 0, missingDetailCount = 0): void {
    const baseScore = gaveUp ? 56 : 92;
    const score = Math.max(30, baseScore - hintCount.value * 7 - detailPenalty);
    settlement.value = {
      score,
      grade: score >= 90 ? "S" : score >= 80 ? "A" : score >= 70 ? "B" : "C",
      summary: gaveUp
        ? "你们沿着门口的异常行为摸到了真相边缘，只差把灯光和室友的处境连起来。"
        : "你们先锁定了“钥匙丢了”是一场表演，再把门缝里的光还原成求救信号。",
      awards: [
        {
          title: "MVP 玩家",
          recipient: nickname.value,
          reason: "把伪装、求救信号和室友的危险处境连成了完整闭环。",
        },
        {
          title: "最佳带偏奖",
          recipient: nickname.value,
          reason: "留下了本局最有戏剧性的错误方向。",
        },
        {
          title: "最有价值问题",
          recipient: nickname.value,
          reason: "提出的问题最有效地缩小了真相范围。",
        },
      ],
      endedAt: Date.now(),
      gaveUp,
      missingDetailCount,
      detailPenalty,
    };
    stage.value = "settlement";
    rematch.value = {
      status: "voting",
      eligiblePlayerIds: players.value.map((player) => player.id),
      acceptedPlayerIds: [],
    };
    persistCompletedGame();
  }

  async function voteRematch(agree: boolean): Promise<void> {
    if (stage.value !== "settlement" || !rematch.value) return;
    if (TRANSPORT_MODE === "server") {
      await runCommand("rematch.vote", { agree }, ["rematch.updated"]);
      return;
    }

    const accepted = new Set(rematch.value.acceptedPlayerIds);
    if (agree) accepted.add(selfId.value);
    else accepted.delete(selfId.value);
    rematch.value = { ...rematch.value, acceptedPlayerIds: [...accepted] };
    if (!agree) return;

    // Mock mode lets the remaining demo players agree automatically so the
    // complete settlement-to-next-round transition stays previewable.
    await sleep(900);
    if (!rematch.value?.acceptedPlayerIds.includes(selfId.value)) return;
    rematch.value = {
      ...rematch.value,
      status: "generating",
      acceptedPlayerIds: [...rematch.value.eligiblePlayerIds],
    };
    await sleep(1_000);
    resetRoundState();
    roundNumber.value += 1;
    puzzle.value = { ...MOCK_PUZZLE, id: `${MOCK_PUZZLE.id}-${roundNumber.value}` };
    stage.value = "playing";
    timeline.value = [
      {
        id: id("system"),
        kind: "system",
        createdAt: Date.now(),
        title: "新一轮推理开始",
        content: "大家一致同意再来一碗，主持人已经换上了新的汤面。",
      },
    ];
  }

  async function leaveRoom(): Promise<void> {
    try {
      if (TRANSPORT_MODE === "server" && activeSession && stage.value !== "closed") {
        await runCommand("room.leave", {}, ["player.left", "room.closed"]);
      }
    } catch {
      // The server may already have expired a settled room; local cleanup must
      // still complete so the user is never trapped on the result screen.
    } finally {
      // Leaving is a local terminal action even if the old room has already
      // expired on the server.
      cancelReconnect();
      clearSession();
      activeSession = null;
      transport.disconnect();
      resetRoom();
      players.value = [];
      roomCode.value = "";
      roomId.value = "";
      stage.value = "closed";
    }
  }

  async function closeRoom(): Promise<void> {
    if (!isHost.value) return;
    if (TRANSPORT_MODE === "server") {
      await runCommand("room.close", {}, ["room.closed"]);
      return;
    }
    resetRoom();
    players.value = [];
    roomCode.value = "";
    roomId.value = "";
    stage.value = "closed";
  }

  function clearHistory(): void {
    history.value = [];
    persistHistory();
  }

  async function runCommand(
    type: Parameters<ServerTransport["sendAndWait"]>[0],
    payload: Record<string, unknown>,
    targets: Parameters<ServerTransport["sendAndWait"]>[2],
    timeoutMs?: number,
  ): Promise<ServerEvent> {
    lastError.value = "";
    try {
      return await transport.sendAndWait(type, payload, targets, timeoutMs);
    } catch (error) {
      lastError.value = errorMessage(error);
      throw error;
    }
  }

  function applyServerEvent(event: ServerEvent): void {
    if (event.type === "protocol.error" || event.type === "session.rejected" || event.type === "command.rejected") {
      const error = event.payload.error as Record<string, unknown> | undefined;
      lastError.value = typeof error?.message === "string" ? error.message : "服务端拒绝了当前操作。";
      return;
    }

    if (event.type === "room.snapshot") {
      applySnapshot(event.payload as unknown as RoomSnapshotPayload);
      return;
    }

    if (event.eventId <= lastEventId.value) return;
    if (lastEventId.value > 0 && event.eventId > lastEventId.value + 1) {
      recoverFromEventGap();
      return;
    }
    lastEventId.value = event.eventId;
    updatePersistedEventId();

    if (event.type === "room.started") {
      stage.value = "playing";
      const surface = event.payload.puzzleSurface as Puzzle | undefined;
      if (surface) puzzle.value = { ...surface, truth: "", keyFacts: [] };
      addTimeline(event);
    } else if (event.type === "room.restarted") {
      resetRoundState();
      roundNumber.value = Number(event.payload.roundNumber || roundNumber.value + 1);
      stage.value = "playing";
      const surface = event.payload.puzzleSurface as Puzzle | undefined;
      if (surface) puzzle.value = { ...surface, truth: "", keyFacts: [] };
      addTimeline(event);
    } else if (event.type === "room.closed") {
      stage.value = "closed";
      clearSession();
      activeSession = null;
      cancelReconnect();
      transport.disconnect();
    } else if (event.type === "room.host_changed") {
      const hostPlayerId = String(event.payload.hostPlayerId || "");
      players.value = players.value.map((player) => ({ ...player, isHost: player.id === hostPlayerId }));
    } else if (event.type === "player.joined") {
      const player = event.payload.player as ProtocolPlayer | undefined;
      if (player && !players.value.some((item) => item.id === player.id)) {
        players.value.push(mapPlayer(player, players.value.length));
      }
    } else if (event.type === "player.left" || event.type === "player.kicked") {
      const playerId = String(event.payload.playerId || "");
      players.value = players.value.filter((player) => player.id !== playerId);
      if (playerId === selfId.value) stage.value = "closed";
    } else if (event.type === "player.online_changed") {
      const playerId = String(event.payload.playerId || "");
      const target = players.value.find((player) => player.id === playerId);
      if (target) target.online = Boolean(event.payload.online);
    } else if (event.type === "discussion.created") {
      const discussion = event.payload.discussion as ProtocolDiscussion | undefined;
      if (discussion && !discussions.value.some((item) => item.id === discussion.id)) {
        discussions.value.push(mapDiscussion(discussion));
      }
    } else if (event.type === "question.queued") {
      const question = event.payload.question as ProtocolQuestion | undefined;
      if (question && !questions.value.some((item) => item.id === question.id)) {
        questions.value.push(mapQuestion(question));
      }
    } else if (event.type === "question.thinking") {
      updateQuestionStatus(String(event.payload.questionId || ""), "thinking");
    } else if (event.type === "question.cancelled") {
      updateQuestionStatus(String(event.payload.questionId || ""), "cancelled");
    } else if (event.type === "question.answered") {
      const question = event.payload.question as ProtocolQuestion | undefined;
      if (question) replaceQuestion(mapQuestion(question));
      addTimeline(event);
    } else if (event.type === "question.failed") {
      updateQuestionStatus(String(event.payload.questionId || ""), "failed");
      const error = event.payload.error as Record<string, unknown> | undefined;
      if (typeof error?.message === "string") lastError.value = error.message;
    } else if (event.type === "hint.created") {
      hintCount.value = Number(event.payload.hintNumber || hintCount.value + 1);
      addTimeline(event);
    } else if (event.type === "hint.failed") {
      const error = event.payload.error as Record<string, unknown> | undefined;
      lastError.value = typeof error?.message === "string" ? error.message : "提示生成失败。";
    } else if (event.type === "conclusion.close" || event.type === "conclusion.rejected") {
      addTimeline(event);
    } else if (event.type === "game.settled") {
      applySettlement(event.payload as unknown as ProtocolSettlement);
    } else if (event.type === "rematch.updated" || event.type === "rematch.generating") {
      rematch.value = mapRematch(event.payload as unknown as ProtocolRematchState);
    } else if (event.type === "rematch.failed") {
      const nextState = event.payload.rematch as ProtocolRematchState | undefined;
      if (nextState) rematch.value = mapRematch(nextState);
      else if (rematch.value) rematch.value = { ...rematch.value, status: "voting" };
      const error = event.payload.error as Record<string, unknown> | undefined;
      lastError.value =
        typeof error?.message === "string" ? error.message : "下一局暂时没有准备好，请重新投票。";
    }
  }

  function applySnapshot(snapshot: RoomSnapshotPayload): void {
    roomId.value = snapshot.room.roomId;
    roomCode.value = snapshot.room.inviteCode;
    stage.value = snapshot.room.stage;
    selfId.value = snapshot.self.playerId;
    nickname.value = snapshot.self.nickname;
    roomConfig.value = {
      source: snapshot.room.source,
      difficulty: snapshot.room.difficulty
        ? FROM_PROTOCOL_DIFFICULTY[snapshot.room.difficulty]
        : "新手",
      style: snapshot.room.style ? FROM_PROTOCOL_STYLE[snapshot.room.style] : "经典悬疑",
    };
    players.value = snapshot.players.map(mapPlayer);
    questions.value = snapshot.questions.map(mapQuestion);
    discussions.value = snapshot.discussions.map(mapDiscussion);
    hintCount.value = snapshot.room.hintCount;
    roundNumber.value = snapshot.room.roundNumber ?? 1;
    timeline.value = snapshot.timeline
      .map((item: SnapshotTimelineEntry) =>
        timelineFromEvent(item.eventId, item.type, item.createdAt, item.payload),
      )
      .filter((item): item is TimelineItem => item !== null);
    if (snapshot.puzzleSurface) {
      puzzle.value = {
        ...snapshot.puzzleSurface,
        truth: snapshot.settlement?.truth || "",
        keyFacts: snapshot.settlement?.keyFacts || [],
      };
    }
    settlement.value = snapshot.settlement ? mapSettlement(snapshot.settlement) : null;
    rematch.value = snapshot.rematch ? mapRematch(snapshot.rematch) : null;
    lastEventId.value = snapshot.lastEventId;
    updatePersistedEventId();
    if (snapshot.settlement) persistCompletedGame();
  }

  function applySettlement(value: ProtocolSettlement): void {
    settlement.value = mapSettlement(value);
    puzzle.value = {
      ...puzzle.value,
      truth: value.truth,
      keyFacts: [...value.keyFacts],
    };
    stage.value = "settlement";
    persistCompletedGame();
  }

  function updateQuestionStatus(questionId: string, status: Question["status"]): void {
    const question = questions.value.find((item) => item.id === questionId);
    if (question) question.status = status;
  }

  function replaceQuestion(question: Question): void {
    const index = questions.value.findIndex((item) => item.id === question.id);
    if (index >= 0) questions.value[index] = question;
    else questions.value.push(question);
  }

  function addTimeline(event: ServerEvent): void {
    if (timeline.value.some((item) => item.id === `event-${event.eventId}`)) return;
    const item = timelineFromEvent(event.eventId, event.type, event.serverTime, event.payload);
    if (item) timeline.value.push(item);
  }

  function persistCompletedGame(): void {
    if (!settlement.value || !puzzle.value.truth) return;
    const entryId = `history-${roomId.value}-${settlement.value.endedAt}`;
    if (history.value.some((entry) => entry.id === entryId)) return;
    const entry: LocalHistoryEntry = {
      id: entryId,
      roomCode: roomCode.value,
      puzzle: { ...puzzle.value, keyFacts: [...puzzle.value.keyFacts] },
      timeline: timeline.value.map((item) => ({ ...item })),
      discussions: discussions.value.map((message) => ({ ...message })),
      settlement: {
        ...settlement.value,
        awards: settlement.value.awards.map((award) => ({ ...award })),
      },
    };
    history.value = [entry, ...history.value].slice(0, 30);
    persistHistory();
  }

  return {
    nickname,
    roomCode,
    roomId,
    stage,
    roomConfig,
    selfId,
    players,
    puzzle,
    questions,
    timeline,
    discussions,
    hintCount,
    settlement,
    rematch,
    roundNumber,
    history,
    connectionStatus,
    connectionLabel,
    lastError,
    isServerMode,
    self,
    isHost,
    onlineCount,
    pendingQuestions,
    checkServer,
    createRoom,
    joinRoom,
    ensureRoom,
    ensureDemoRoom,
    startGame,
    sendDiscussion,
    submitQuestion,
    removeQuestion,
    requestHint,
    submitConclusion,
    giveUp,
    finishGame,
    voteRematch,
    leaveRoom,
    closeRoom,
    clearHistory,
  };
});
