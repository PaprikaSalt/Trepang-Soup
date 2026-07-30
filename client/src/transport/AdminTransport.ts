import { argon2id } from "hash-wasm";

import { PROTOCOL_VERSION } from "../protocol/types";

export interface LibraryPuzzle {
  id: string;
  title: string;
  surface: string;
  truth: string;
  keyFacts: string[];
  active: boolean;
  createdAt: number;
  updatedAt: number;
}

export interface PuzzleWrite {
  title: string;
  surface: string;
  truth: string;
  keyFacts: string[];
  active: boolean;
}

interface PasswordKdf {
  name: "argon2id";
  salt: string;
  timeCost: number;
  memoryCost: number;
  parallelism: number;
  hashLength: number;
}

interface AdminChallenge {
  challengeId: string;
  nonce: string;
  issuedAt: number;
  expiresAt: number;
  mac: "hmac-sha256";
  passwordKdf: PasswordKdf;
}

interface AdminLoginResponse {
  accessToken: string;
  tokenType: "Bearer";
  expiresAt: number;
}

interface PuzzleListResponse {
  items: LibraryPuzzle[];
  total: number;
}

export class AdminTransportError extends Error {
  constructor(
    message: string,
    readonly status = 0,
  ) {
    super(message);
    this.name = "AdminTransportError";
  }
}

function decodeBase64(value: string): Uint8Array {
  const padded = value + "=".repeat((4 - (value.length % 4)) % 4);
  const binary = window.atob(padded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function toHex(value: ArrayBuffer): string {
  return Array.from(new Uint8Array(value), (byte) => byte.toString(16).padStart(2, "0")).join("");
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

export class AdminTransport {
  private accessToken = "";
  private expiresAt = 0;

  constructor(private readonly baseUrl: string) {}

  async login(password: string): Promise<void> {
    const challenge = await this.request<AdminChallenge>("/api/v1/admin/challenge");
    const kdf = challenge.passwordKdf;

    // 密码只参与本机 Argon2id 派生，网络上发送的是一次性挑战响应。
    const verifier = await argon2id({
      password,
      salt: decodeBase64(kdf.salt),
      iterations: kdf.timeCost,
      memorySize: kdf.memoryCost,
      parallelism: kdf.parallelism,
      hashLength: kdf.hashLength,
      outputType: "binary",
    });
    const message = new TextEncoder().encode(
      `${challenge.challengeId}\n${challenge.nonce}\n${challenge.issuedAt}`,
    );
    const hmacKey = await crypto.subtle.importKey(
      "raw",
      verifier,
      { name: "HMAC", hash: "SHA-256" },
      false,
      ["sign"],
    );
    const response = toHex(await crypto.subtle.sign("HMAC", hmacKey, message));
    const result = await this.request<AdminLoginResponse>("/api/v1/admin/login", {
      method: "POST",
      body: JSON.stringify({
        challengeId: challenge.challengeId,
        timestamp: challenge.issuedAt,
        response,
      }),
    });
    this.accessToken = result.accessToken;
    this.expiresAt = result.expiresAt;
  }

  async listPuzzles(): Promise<LibraryPuzzle[]> {
    const response = await this.authorizedRequest<PuzzleListResponse>("/api/v1/admin/puzzles");
    return response.items;
  }

  createPuzzle(puzzle: PuzzleWrite): Promise<LibraryPuzzle> {
    return this.authorizedRequest<LibraryPuzzle>("/api/v1/admin/puzzles", {
      method: "POST",
      body: JSON.stringify(puzzle),
    });
  }

  updatePuzzle(puzzleId: string, puzzle: PuzzleWrite): Promise<LibraryPuzzle> {
    return this.authorizedRequest<LibraryPuzzle>(
      `/api/v1/admin/puzzles/${encodeURIComponent(puzzleId)}`,
      {
        method: "PUT",
        body: JSON.stringify(puzzle),
      },
    );
  }

  async deletePuzzle(puzzleId: string): Promise<void> {
    await this.authorizedRequest<void>(
      `/api/v1/admin/puzzles/${encodeURIComponent(puzzleId)}`,
      { method: "DELETE" },
    );
  }

  clearSession(): void {
    this.accessToken = "";
    this.expiresAt = 0;
  }

  hasSession(): boolean {
    return Boolean(this.accessToken) && this.expiresAt > Math.floor(Date.now() / 1_000);
  }

  private async authorizedRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
    if (!this.accessToken || this.expiresAt <= Math.floor(Date.now() / 1_000)) {
      this.clearSession();
      throw new AdminTransportError("管理员登录已过期，请重新解锁题库。", 401);
    }
    try {
      return await this.request<T>(path, {
        ...init,
        headers: {
          Authorization: `Bearer ${this.accessToken}`,
          ...init.headers,
        },
      });
    } catch (error) {
      if (error instanceof AdminTransportError && error.status === 401) this.clearSession();
      throw error;
    }
  }

  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    try {
      const response = await fetch(`${this.baseUrl}${path}`, {
        ...init,
        headers: {
          "Content-Type": "application/json",
          "X-Protocol-Version": String(PROTOCOL_VERSION),
          ...init.headers,
        },
        signal: AbortSignal.timeout(15_000),
      });
      if (response.status === 204) return undefined as T;
      const body = (await response.json()) as unknown;
      if (!response.ok) {
        throw new AdminTransportError(
          serverMessage(body, `请求失败（${response.status}）。`),
          response.status,
        );
      }
      return body as T;
    } catch (error) {
      if (error instanceof AdminTransportError) throw error;
      if (error instanceof Error && error.name === "TimeoutError") {
        throw new AdminTransportError("连接题库服务超时，请稍后重试。");
      }
      throw new AdminTransportError("无法连接题库服务。");
    }
  }
}

const SERVER_URL = (import.meta.env.VITE_SERVER_URL || "http://127.0.0.1:8787").replace(/\/+$/, "");

// 单例让令牌在应用运行期间跨页面复用，但关闭程序后不会留下管理员凭据。
export const adminTransport = new AdminTransport(SERVER_URL);
