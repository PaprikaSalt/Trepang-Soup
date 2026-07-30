import { computed, ref } from "vue";
import { defineStore } from "pinia";

import type {
  DiscussionMessage,
  LocalHistoryEntry,
  Puzzle,
  Question,
  RoomConfig,
  RoomStage,
  Settlement,
  TimelineItem,
  Player,
} from "../types/game";

const PROFILE_KEY = "trepang-soup.profile";
const HISTORY_KEY = "trepang-soup.history";
const sleep = (duration: number) => new Promise((resolve) => window.setTimeout(resolve, duration));

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

function id(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function timeAgoStamp(): number {
  return Date.now() - 1000 * 60;
}

function loadJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
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
  if (/时间|凌晨/.test(normalized)) {
    return { answer: "部分相关。凌晨让她更警觉，但不是谜底的核心机关。", answerType: "partial" };
  }
  return { answer: "无关。这个方向暂时不能帮助你们解释她为什么故意不进门。", answerType: "irrelevant" };
}

export const useGameStore = defineStore("game", () => {
  const savedProfile = loadJson<{ nickname: string }>(PROFILE_KEY, { nickname: "" });
  const nickname = ref(savedProfile.nickname);
  const roomCode = ref("");
  const stage = ref<RoomStage>("lobby");
  const roomConfig = ref<RoomConfig>({
    source: "ai",
    difficulty: "新手",
    style: "经典悬疑",
  });
  const selfId = ref(id("self"));
  const players = ref<Player[]>([]);
  const puzzle = ref<Puzzle>(MOCK_PUZZLE);
  const questions = ref<Question[]>([]);
  const timeline = ref<TimelineItem[]>([]);
  const discussions = ref<DiscussionMessage[]>([]);
  const hintCount = ref(0);
  const settlement = ref<Settlement | null>(null);
  const processingQueue = ref(false);
  const history = ref<LocalHistoryEntry[]>(loadJson<LocalHistoryEntry[]>(HISTORY_KEY, []));
  let roomRevision = 0;

  const self = computed(() => players.value.find((player) => player.id === selfId.value));
  const isHost = computed(() => self.value?.isHost ?? false);
  const onlineCount = computed(() => players.value.filter((player) => player.online).length);
  const pendingQuestions = computed(() =>
    questions.value.filter((question) => question.status === "queued" || question.status === "thinking"),
  );

  function persistProfile(): void {
    window.localStorage.setItem(PROFILE_KEY, JSON.stringify({ nickname: nickname.value }));
  }

  function persistHistory(): void {
    window.localStorage.setItem(HISTORY_KEY, JSON.stringify(history.value));
  }

  function resetRoom(): void {
    roomRevision += 1;
    questions.value = [];
    timeline.value = [];
    discussions.value = [];
    hintCount.value = 0;
    settlement.value = null;
    processingQueue.value = false;
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

  function createRoom(profileName: string, config: RoomConfig): string {
    nickname.value = profileName.trim();
    persistProfile();
    resetRoom();
    roomCode.value = "N7K4WM";
    roomConfig.value = config;
    players.value = makePlayers(nickname.value, true);
    stage.value = "lobby";
    return roomCode.value;
  }

  function joinRoom(profileName: string, code: string): string {
    nickname.value = profileName.trim();
    persistProfile();
    resetRoom();
    roomCode.value = code.trim().toUpperCase();
    roomConfig.value = { source: "ai", difficulty: "新手", style: "经典悬疑" };
    players.value = makePlayers(nickname.value, false);
    stage.value = "lobby";
    return roomCode.value;
  }

  function ensureDemoRoom(): void {
    if (roomCode.value) return;
    createRoom(nickname.value || "海盐", roomConfig.value);
  }

  function startGame(): void {
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
        createdAt: timeAgoStamp(),
      },
      {
        id: id("discussion"),
        authorId: "mock-player-seven",
        authorName: "小七",
        content: "门缝里的光也怪，室友如果睡了为什么还亮着？",
        createdAt: Date.now() - 28000,
      },
    ];
  }

  function sendDiscussion(content: string): void {
    const clean = content.trim();
    if (!clean) return;
    discussions.value.push({
      id: id("discussion"),
      authorId: selfId.value,
      authorName: nickname.value,
      content: clean,
      createdAt: Date.now(),
    });
  }

  async function processQueue(): Promise<void> {
    if (processingQueue.value) return;
    processingQueue.value = true;
    const activeRevision = roomRevision;

    // MockTransport deliberately serializes AI work so UI behavior matches the future server queue.
    while (true) {
      const next = questions.value.find((question) => question.status === "queued");
      if (!next) break;
      next.status = "thinking";
      await sleep(1400);
      // Closing or replacing a room invalidates any delayed mock-AI response still in flight.
      if (activeRevision !== roomRevision) break;
      const result = mockAnswer(next.content);
      next.answer = result.answer;
      next.answerType = result.answerType;
      next.status = "answered";
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

  function submitQuestion(content: string): void {
    const clean = content.trim();
    if (!clean) return;
    questions.value.push({
      id: id("question"),
      authorId: selfId.value,
      authorName: nickname.value,
      content: clean,
      createdAt: Date.now(),
      status: "queued",
    });
    void processQueue();
  }

  function removeQuestion(questionId: string): void {
    const index = questions.value.findIndex(
      (question) =>
        question.id === questionId && question.authorId === selfId.value && question.status === "queued",
    );
    if (index >= 0) questions.value.splice(index, 1);
  }

  async function requestHint(): Promise<void> {
    const requestor = nickname.value;
    hintCount.value += 1;
    timeline.value.push({
      id: id("system"),
      kind: "system",
      createdAt: Date.now(),
      title: `${requestor} 举起了白旗`,
      content: "主持人正在把散落的线索重新摆上桌面……",
    });
    await sleep(1200);
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

  function conclusionLooksCorrect(content: string): boolean {
    const normalized = content.replace(/\s/g, "");
    const hasDanger = /危险|挟持|绑架|闯入|歹徒|坏人/.test(normalized);
    const hasSignal = /灯|闪|信号|求救/.test(normalized);
    const hasPretend = /假装|故意|骗|伪装|钥匙/.test(normalized);
    return hasDanger && hasSignal && hasPretend;
  }

  async function submitConclusion(content: string): Promise<"correct" | "close"> {
    await sleep(900);
    if (conclusionLooksCorrect(content)) {
      finishGame(false);
      return "correct";
    }
    return "close";
  }

  function finishGame(gaveUp: boolean): void {
    const baseScore = gaveUp ? 56 : 92;
    const score = Math.max(30, baseScore - hintCount.value * 7);
    settlement.value = {
      score,
      grade: score >= 90 ? "S" : score >= 80 ? "A" : score >= 70 ? "B" : "C",
      summary: gaveUp
        ? "你们沿着门口的异常行为摸到了真相边缘，只差把灯光和室友的处境连起来。下一碗汤，记得先问“这个动作是在演给谁看”。"
        : "你们先锁定了“钥匙丢了”是一场表演，再把门缝里的光还原成求救信号。思路从行为动机切入，最后拼出了完整因果链。",
      awards: [
        {
          title: "MVP 玩家",
          recipient: nickname.value,
          reason: "把伪装、求救信号和室友的危险处境连成了完整闭环。",
        },
        {
          title: "最有价值问题",
          recipient: "小七",
          reason: "“门缝里的光是室友主动制造的吗？”让大家第一次摸到核心机关。",
        },
        {
          title: "最佳带偏奖",
          recipient: "月半",
          reason: "坚定怀疑宿管阿姨长达三分钟，气势很足，证据没有。",
        },
      ],
      endedAt: Date.now(),
      gaveUp,
    };
    stage.value = "settlement";

    // Persist only on the local machine; completed room data is not designed for server storage.
    const entry: LocalHistoryEntry = {
      id: id("history"),
      roomCode: roomCode.value,
      puzzle: { ...puzzle.value },
      timeline: timeline.value.map((item) => ({ ...item })),
      discussions: discussions.value.map((message) => ({ ...message })),
      settlement: { ...settlement.value },
    };
    history.value = [entry, ...history.value].slice(0, 30);
    persistHistory();
  }

  function closeRoom(): void {
    if (!isHost.value) return;
    resetRoom();
    players.value = [];
    roomCode.value = "";
    stage.value = "lobby";
  }

  function clearHistory(): void {
    history.value = [];
    persistHistory();
  }

  return {
    nickname,
    roomCode,
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
    history,
    self,
    isHost,
    onlineCount,
    pendingQuestions,
    createRoom,
    joinRoom,
    ensureDemoRoom,
    startGame,
    sendDiscussion,
    submitQuestion,
    removeQuestion,
    requestHint,
    submitConclusion,
    finishGame,
    closeRoom,
    clearHistory,
  };
});
