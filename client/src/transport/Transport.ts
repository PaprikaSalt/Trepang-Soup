import type {
  AdmissionResponse,
  CommandType,
  EventType,
  PersistedSession,
  ProtocolDifficulty,
  ProtocolPuzzleSource,
  ProtocolPuzzleStyle,
  ResumeResponse,
  ServerEvent,
  TransportStatus,
} from "../protocol/types";

export interface CreateRoomInput {
  nickname: string;
  source: ProtocolPuzzleSource;
  difficulty: ProtocolDifficulty | null;
  style: ProtocolPuzzleStyle | null;
}

export interface JoinRoomInput {
  nickname: string;
  inviteCode: string;
  clientInstanceId: string;
}

export interface Transport {
  onEvent(listener: (event: ServerEvent) => void): () => void;
  onStatus(listener: (status: TransportStatus) => void): () => void;
  healthCheck(): Promise<void>;
  createRoom(input: CreateRoomInput): Promise<AdmissionResponse>;
  joinRoom(input: JoinRoomInput): Promise<AdmissionResponse>;
  resumeSession(session: PersistedSession): Promise<ResumeResponse>;
  connect(session: PersistedSession): Promise<void>;
  sendAndWait(
    commandType: CommandType,
    payload: Record<string, unknown>,
    targetTypes: EventType[],
    timeoutMs?: number,
  ): Promise<ServerEvent>;
  disconnect(): void;
}
