/**
 * API Client — communicates with the FastAPI backend.
 *
 * In dev: Vite proxy forwards /api → http://localhost:8000
 * In prod: VITE_API_URL points to the deployed backend
 */

export const API_BASE = import.meta.env.VITE_API_URL
    ? `${import.meta.env.VITE_API_URL}/api`
    : "/api";

export function getWsUrl(path: string): string {
    if (import.meta.env.VITE_API_URL) {
        // Production: convert https://foo.com → wss://foo.com/ws/...
        const url = import.meta.env.VITE_API_URL as string;
        const wsUrl = url.replace(/^http/, "ws");
        return `${wsUrl}${path}`;
    }
    // Dev: use current host (Vite proxy handles /ws)
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}${path}`;
}

// ── Types ───────────────────────────────────────────────────────────────────

export interface User {
    id: string;
    username: string;
    email?: string;
    created_at: string;
    total_sessions: number;
    best_time_ms: number;
}

export interface LeaderboardEntry {
    rank: number;
    user_id: string;
    username: string;
    duration_ms: number;
    date: string;
}

export interface LeaderboardResponse {
    entries: LeaderboardEntry[];
    total_players: number;
}

export interface UserRankResponse {
    user_id: string;
    username: string;
    rank: number | null;
    message: string;
}

// ── Auth ────────────────────────────────────────────────────────────────────

export async function registerUser(
    username: string,
    email: string,
    password: string
): Promise<User> {
    const res = await fetch(`${API_BASE}/users/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, email, password }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Registration failed" }));
        throw new Error(err.detail || "Registration failed");
    }
    return res.json();
}

export async function loginUser(
    email: string,
    password: string
): Promise<User> {
    const res = await fetch(`${API_BASE}/users/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Invalid email or password" }));
        throw new Error(err.detail || "Invalid email or password");
    }
    return res.json();
}

// ── Leaderboard ─────────────────────────────────────────────────────────────

export async function getLeaderboard(): Promise<LeaderboardResponse> {
    const res = await fetch(`${API_BASE}/leaderboard`);
    if (!res.ok) throw new Error("Failed to fetch leaderboard");
    return res.json();
}

export async function getUserRank(userId: string): Promise<UserRankResponse> {
    const res = await fetch(`${API_BASE}/leaderboard/${userId}/rank`);
    if (!res.ok) throw new Error("Failed to fetch rank");
    return res.json();
}

// ── Local Storage Helpers ───────────────────────────────────────────────────

const USER_KEY = "noblink-user";

export function saveUser(user: User): void {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getStoredUser(): User | null {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
        return JSON.parse(raw);
    } catch {
        return null;
    }
}

export function clearStoredUser(): void {
    localStorage.removeItem(USER_KEY);
}
