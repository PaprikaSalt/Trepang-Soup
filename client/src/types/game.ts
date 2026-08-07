export type RoomStage = "lobby" | "playing" | "settlement" | "closed";
export type PuzzleSource = "ai" | "library";
export type Difficulty = "新手" | "标准" | "烧脑";
export type PuzzleStyle = "轻松日常" | "经典悬疑" | "暗黑惊悚" | "荒诞幽默";
export type QuestionStatus = "queued" | "thinking" | "answered" | "cancelled" | "failed";
export type TimelineKind = "system" | "qa" | "hint";

export interface Player {
  id: string;
  nickname: string;
  online: boolean;
  isHost: boolean;
  accent: string;
  joinedAt: number;
}

export interface RoomConfig {
  source: PuzzleSource;
  difficulty: Difficulty;
  style: PuzzleStyle;
}

export interface Puzzle {
  id: string;
  title: string;
  surface: string;
  truth: string;
  keyFacts: string[];
}

export interface Question {
  id: string;
  authorId: string;
  authorName: string;
  content: string;
  createdAt: number;
  status: QuestionStatus;
  answer?: string;
  answerType?: "yes" | "no" | "irrelevant" | "partial" | "cannot_reveal";
}

export interface DiscussionMessage {
  id: string;
  authorId: string;
  authorName: string;
  content: string;
  createdAt: number;
}

export interface TimelineItem {
  id: string;
  kind: TimelineKind;
  createdAt: number;
  question?: Question;
  title?: string;
  content?: string;
  actorName?: string;
}

export interface Award {
  title: string;
  recipient: string;
  reason: string;
}

export interface Settlement {
  score: number;
  grade: string;
  summary: string;
  awards: Award[];
  endedAt: number;
  gaveUp: boolean;
  missingDetailCount: number;
  detailPenalty: number;
}

export interface RematchState {
  status: "voting" | "generating";
  eligiblePlayerIds: string[];
  acceptedPlayerIds: string[];
}

export interface LocalHistoryEntry {
  id: string;
  roomCode: string;
  puzzle: Puzzle;
  timeline: TimelineItem[];
  discussions: DiscussionMessage[];
  settlement: Settlement;
}
