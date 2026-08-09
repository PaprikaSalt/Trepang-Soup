export const PROTOCOL_VERSION = 1 as const;
export const CLIENT_VERSION = "1.5.0";

export type ProtocolDifficulty = "beginner" | "standard" | "hard";
export type ProtocolPuzzleStyle =
  | "light_daily"
  | "classic_mystery"
  | "dark_thriller"
  | "absurd_humor";
export type ProtocolPuzzleSource = "ai" | "library";
export type ProtocolRoomStage = "lobby" | "playing" | "settlement" | "closed";

export type CommandType =
  | "session.hello"
  | "room.start"
  | "room.close"
  | "room.kick"
  | "room.leave"
  | "rematch.vote"
  | "discussion.send"
  | "question.submit"
  | "question.cancel"
  | "hint.request"
  | "conclusion.begin"
  | "conclusion.submit"
  | "conclusion.give_up";

export type EventType =
  | "protocol.error"
  | "command.rejected"
  | "session.rejected"
  | "room.snapshot"
  | "room.started"
  | "room.restarted"
  | "room.closed"
  | "room.host_changed"
  | "player.joined"
  | "player.left"
  | "player.online_changed"
  | "player.kicked"
  | "discussion.created"
  | "question.queued"
  | "question.cancelled"
  | "question.thinking"
  | "question.answered"
  | "question.failed"
  | "hint.thinking"
  | "hint.created"
  | "hint.failed"
  | "conclusion.thinking"
  | "conclusion.confirmation_required"
  | "conclusion.close"
  | "conclusion.rejected"
  | "game.settled"
  | "rematch.updated"
  | "rematch.generating"
  | "rematch.failed";

export interface AdmissionResponse {
  roomId: string;
  inviteCode: string;
  playerId: string;
  sessionToken: string;
  expiresAt: number;
}

export interface ResumeResponse {
  roomId: string;
  playerId: string;
  sessionToken: string;
  expiresAt: number;
  snapshotVersion: number;
}

export interface PersistedSession extends AdmissionResponse {
  lastEventId: number;
}

export interface ProtocolPlayer {
  id: string;
  nickname: string;
  online: boolean;
  isHost: boolean;
  joinedAt: number;
}

export interface ProtocolQuestion {
  id: string;
  authorId: string;
  authorName: string;
  content: string;
  createdAt: number;
  status: "queued" | "thinking" | "answered" | "cancelled" | "failed";
  answerType?: "yes" | "no" | "irrelevant" | "partial" | "cannot_reveal";
  answer?: string;
}

export interface ProtocolDiscussion {
  id: string;
  authorId: string;
  authorName: string;
  content: string;
  createdAt: number;
}

export interface ProtocolSettlement {
  truth: string;
  keyFacts: string[];
  score: number;
  grade: string;
  gaveUp: boolean;
  missingDetailCount?: number;
  detailPenalty?: number;
  summary: string;
  awards: Array<{
    title: string;
    recipientPlayerId: string;
    recipientName: string;
    reason: string;
  }>;
  endedAt: number;
}

export interface ProtocolRematchState {
  status: "voting" | "generating";
  eligiblePlayerIds: string[];
  acceptedPlayerIds: string[];
}

export interface SnapshotTimelineEntry {
  eventId: number;
  type: EventType;
  createdAt: number;
  payload: Record<string, unknown>;
}

export interface RoomSnapshotPayload {
  room: {
    roomId: string;
    inviteCode: string;
    stage: ProtocolRoomStage;
    hostPlayerId: string;
    source: ProtocolPuzzleSource;
    difficulty: ProtocolDifficulty | null;
    style: ProtocolPuzzleStyle | null;
    hintCount: number;
    roundNumber?: number;
    createdAt: number;
    startedAt: number | null;
  };
  self: {
    playerId: string;
    nickname: string;
  };
  players: ProtocolPlayer[];
  puzzleSurface: {
    id: string;
    title: string;
    surface: string;
  } | null;
  questions: ProtocolQuestion[];
  timeline: SnapshotTimelineEntry[];
  discussions: ProtocolDiscussion[];
  settlement?: ProtocolSettlement;
  rematch?: ProtocolRematchState;
  lastEventId: number;
}

export interface ServerEvent {
  protocolVersion: 1;
  eventId: number;
  type: EventType;
  roomId: string;
  serverTime: number;
  causedByCommandId: string | null;
  payload: Record<string, unknown>;
}

export interface ClientCommand {
  protocolVersion: 1;
  commandId: string;
  type: CommandType;
  roomId: string;
  sessionToken: string;
  clientTime: number;
  payload: Record<string, unknown>;
}

export type TransportStatus =
  | "idle"
  | "checking"
  | "available"
  | "connecting"
  | "reconnecting"
  | "connected"
  | "disconnected"
  | "error";
