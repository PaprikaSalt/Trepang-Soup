import { CLIENT_VERSION, PROTOCOL_VERSION } from "../protocol/types";
import type {
  AdmissionResponse,
  ClientCommand,
  CommandType,
  EventType,
  PersistedSession,
  ResumeResponse,
  ServerEvent,
  TransportStatus,
} from "../protocol/types";
import type { CreateRoomInput, JoinRoomInput, Transport } from "./Transport";

interface CommandWaiter {
  targetTypes: Set<EventType>;
  resolve: (event: ServerEvent) => void;
  reject: (error: Error) => void;
  timer: number;
}

export class TransportError extends Error {
  constructor(
    message: string,
    readonly code = "TRANSPORT_ERROR",
  ) {
    super(message);
    this.name = "TransportError";
  }
}

function commandId(prefix: string): string {
  return `cmd_${prefix}_${crypto.randomUUID().replace(/-/g, "")}`;
}

function serverMessage(body: unknown, fallback: string): string {
  if (!body || typeof body !== "object") return fallback;
  const value = body as Record<string, unknown>;
  if (typeof value.message === "string") return value.message;
  if (typeof value.detail === "string") return value.detail;
  if (value.detail && typeof value.detail === "object") {
    const detail = value.detail as Record<string, unknown>;
    if (typeof detail.message === "string") return detail.message;
  }
  return fallback;
}

export class ServerTransport implements Transport {
  private socket: WebSocket | null = null;
  private session: PersistedSession | null = null;
  private intentionallyClosedSockets = new WeakSet<WebSocket>();
  private eventListeners = new Set<(event: ServerEvent) => void>();
  private statusListeners = new Set<(status: TransportStatus) => void>();
  private waiters = new Map<string, CommandWaiter>();

  constructor(private readonly baseUrl: string) {}

  onEvent(listener: (event: ServerEvent) => void): () => void {
    this.eventListeners.add(listener);
    return () => this.eventListeners.delete(listener);
  }

  onStatus(listener: (status: TransportStatus) => void): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  async healthCheck(): Promise<void> {
    this.emitStatus("checking");
    try {
      const response = await fetch(`${this.baseUrl}/health`, {
        signal: AbortSignal.timeout(4_000),
      });
      if (!response.ok) throw new TransportError("服务端健康检查失败。");
      this.emitStatus("available");
    } catch (error) {
      this.emitStatus("error");
      throw this.normalizeError(error, "无法连接后端服务。");
    }
  }

  async createRoom(input: CreateRoomInput): Promise<AdmissionResponse> {
    return this.request<AdmissionResponse>(
      "/api/v1/rooms",
      {
        method: "POST",
        body: JSON.stringify(input),
      },
      // AI rooms perform generation plus an independent quality review.
      300_000,
    );
  }

  async joinRoom(input: JoinRoomInput): Promise<AdmissionResponse> {
    return this.request<AdmissionResponse>("/api/v1/rooms/join", {
      method: "POST",
      body: JSON.stringify(input),
    });
  }

  async resumeSession(session: PersistedSession): Promise<ResumeResponse> {
    return this.request<ResumeResponse>("/api/v1/sessions/resume", {
      method: "POST",
      body: JSON.stringify({
        roomId: session.roomId,
        sessionToken: session.sessionToken,
        lastEventId: session.lastEventId,
      }),
    });
  }

  async connect(session: PersistedSession): Promise<void> {
    this.disconnect();
    this.session = session;
    this.emitStatus("connecting");

    const wsUrl = new URL(this.baseUrl);
    wsUrl.protocol = wsUrl.protocol === "https:" ? "wss:" : "ws:";
    wsUrl.pathname = `/api/v1/rooms/${session.roomId}/ws`;
    wsUrl.search = "";

    await new Promise<void>((resolve, reject) => {
      const socket = new WebSocket(wsUrl);
      this.socket = socket;
      let connected = false;
      const timer = window.setTimeout(() => {
        if (connected) return;
        socket.close();
        this.emitStatus("error");
        reject(new TransportError("连接房间超时。", "CONNECTION_TIMEOUT"));
      }, 8_000);

      socket.onopen = () => {
        const hello: ClientCommand = {
          protocolVersion: PROTOCOL_VERSION,
          commandId: commandId("hello"),
          type: "session.hello",
          roomId: session.roomId,
          sessionToken: session.sessionToken,
          clientTime: Date.now(),
          payload: {
            // Admission always asks for a snapshot; resume may replay from the saved event.
            lastEventId: session.lastEventId,
            clientVersion: CLIENT_VERSION,
          },
        };
        socket.send(JSON.stringify(hello));
      };

      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(String(message.data)) as ServerEvent;
          this.handleEvent(event);
          if (!connected && (event.type === "session.rejected" || event.type === "protocol.error")) {
            const detail = event.payload.error as Record<string, unknown> | undefined;
            window.clearTimeout(timer);
            this.intentionallyClosedSockets.add(socket);
            socket.close(1008, "session rejected");
            this.emitStatus("error");
            reject(
              new TransportError(
                typeof detail?.message === "string" ? detail.message : "房间会话已失效。",
                typeof detail?.code === "string" ? detail.code : "SESSION_REJECTED",
              ),
            );
            return;
          }
          if (!connected) {
            connected = true;
            window.clearTimeout(timer);
            this.emitStatus("connected");
            resolve();
          }
        } catch {
          if (!connected) {
            window.clearTimeout(timer);
            reject(new TransportError("服务端返回了无法解析的消息。", "INVALID_MESSAGE"));
          }
        }
      };

      socket.onerror = () => {
        if (!connected) {
          window.clearTimeout(timer);
          this.emitStatus("error");
          reject(new TransportError("WebSocket 连接失败。", "WEBSOCKET_ERROR"));
        }
      };

      socket.onclose = () => {
        window.clearTimeout(timer);
        const isCurrentSocket = this.socket === socket;
        if (isCurrentSocket) this.socket = null;
        // A delayed close from the previous socket must not overwrite the state
        // of a newly established connection.
        if (isCurrentSocket && !this.intentionallyClosedSockets.has(socket)) {
          this.emitStatus("disconnected");
        }
        if (!connected) reject(new TransportError("房间连接已关闭。", "CONNECTION_CLOSED"));
        if (isCurrentSocket) {
          this.rejectWaiters(new TransportError("连接中断，操作没有完成。", "CONNECTION_CLOSED"));
        }
      };
    });
  }

  async sendAndWait(
    commandType: CommandType,
    payload: Record<string, unknown>,
    targetTypes: EventType[],
    timeoutMs = 15_000,
  ): Promise<ServerEvent> {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN || !this.session) {
      throw new TransportError("尚未连接房间。", "NOT_CONNECTED");
    }

    const id = commandId(commandType.replace(".", "_"));
    const result = new Promise<ServerEvent>((resolve, reject) => {
      const timer = window.setTimeout(() => {
        this.waiters.delete(id);
        reject(new TransportError("服务器响应超时，请稍后重试。", "COMMAND_TIMEOUT"));
      }, timeoutMs);
      this.waiters.set(id, {
        targetTypes: new Set(targetTypes),
        resolve,
        reject,
        timer,
      });
    });

    const command: ClientCommand = {
      protocolVersion: PROTOCOL_VERSION,
      commandId: id,
      type: commandType,
      roomId: this.session.roomId,
      sessionToken: this.session.sessionToken,
      clientTime: Date.now(),
      payload,
    };
    this.socket.send(JSON.stringify(command));
    return result;
  }

  disconnect(): void {
    if (this.socket) {
      this.intentionallyClosedSockets.add(this.socket);
      this.socket.close(1000, "client disconnect");
      this.socket = null;
    }
    this.rejectWaiters(new TransportError("连接已关闭。", "DISCONNECTED"));
  }

  private async request<T>(path: string, init: RequestInit, timeoutMs = 8_000): Promise<T> {
    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        headers: {
          "Content-Type": "application/json",
          "X-Protocol-Version": String(PROTOCOL_VERSION),
          ...init.headers,
        },
        signal: AbortSignal.timeout(timeoutMs),
      });
      const body = (await response.json()) as unknown;
      if (!response.ok) {
        throw new TransportError(serverMessage(body, `请求失败（${response.status}）。`), `HTTP_${response.status}`);
      }
      return body as T;
    } catch (error) {
      throw this.normalizeError(error, "无法连接后端服务。");
    }
  }

  private handleEvent(event: ServerEvent): void {
    for (const listener of this.eventListeners) listener(event);

    const id = event.causedByCommandId;
    if (!id) return;
    const waiter = this.waiters.get(id);
    if (!waiter) return;

    if (event.type === "command.rejected" || event.type === "protocol.error") {
      window.clearTimeout(waiter.timer);
      this.waiters.delete(id);
      const error = event.payload.error as Record<string, unknown> | undefined;
      waiter.reject(
        new TransportError(
          typeof error?.message === "string" ? error.message : "服务器拒绝了这个操作。",
          typeof error?.code === "string" ? error.code : "COMMAND_REJECTED",
        ),
      );
      return;
    }

    if (waiter.targetTypes.has(event.type)) {
      window.clearTimeout(waiter.timer);
      this.waiters.delete(id);
      waiter.resolve(event);
    }
  }

  private emitStatus(status: TransportStatus): void {
    for (const listener of this.statusListeners) listener(status);
  }

  private rejectWaiters(error: Error): void {
    for (const waiter of this.waiters.values()) {
      window.clearTimeout(waiter.timer);
      waiter.reject(error);
    }
    this.waiters.clear();
  }

  private normalizeError(error: unknown, fallback: string): TransportError {
    if (error instanceof TransportError) return error;
    if (error instanceof Error && error.name === "TimeoutError") {
      return new TransportError("连接后端超时。", "REQUEST_TIMEOUT");
    }
    return new TransportError(fallback);
  }
}
