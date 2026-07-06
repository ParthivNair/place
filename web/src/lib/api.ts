/* Typed fetch client for the Place API (backend/place/api/routes/*).
   With NEXT_PUBLIC_MOCK=1 every function serves canon fixtures from
   ./mock instead of fetching — same signatures, simulated latency. */

import type {
  ClaimOut,
  EventIn,
  EventOut,
  FeedResponse,
  PlacePage,
  PlaceSearchResult,
  PushSubscriptionIn,
  SavedItem,
  SaveIn,
  SaveKind,
  TripIn,
  TripOut,
  UserOut,
  VerdictIn,
  VerdictOut,
} from "./types";
import { EVENT_ALIASES } from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const MOCK = process.env.NEXT_PUBLIC_MOCK === "1";
const MOCK_LATENCY_MS = 200;

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    credentials: "include",
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`;
    try {
      const body: unknown = await res.json();
      if (
        typeof body === "object" &&
        body !== null &&
        typeof (body as { detail?: unknown }).detail === "string"
      ) {
        detail = (body as { detail: string }).detail;
      }
    } catch {
      // non-JSON error body; keep the status text
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

function post<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) qs.set(key, String(value));
  }
  return qs.toString();
}

async function mocked<T>(value: T): Promise<T> {
  await new Promise((resolve) => setTimeout(resolve, MOCK_LATENCY_MS));
  return value;
}

// Lazy so real builds never bundle the fixtures.
function fixtures() {
  return import("./mock");
}

// ---------------------------------------------------------------------------
// feed / places
// ---------------------------------------------------------------------------

export async function getFeed(params: {
  lat: number;
  lng: number;
  radius_km?: number;
  activity?: string;
  dog_ok?: boolean;
  kid_ok?: boolean;
  limit?: number;
}): Promise<FeedResponse> {
  if (MOCK) return mocked((await fixtures()).mockFeed);
  return request<FeedResponse>(`/feed?${query(params)}`);
}

export async function searchPlaces(params: {
  lat: number;
  lng: number;
  radius_km?: number;
  activity?: string;
  q?: string;
  limit?: number;
}): Promise<PlaceSearchResult[]> {
  if (MOCK) return mocked((await fixtures()).mockSearchResults);
  return request<PlaceSearchResult[]>(`/places/search?${query(params)}`);
}

export async function getPlace(id: string): Promise<PlacePage> {
  if (MOCK) return mocked((await fixtures()).mockPlaceHighRocks);
  return request<PlacePage>(`/places/${id}`);
}

export async function getAffordanceClaims(id: string): Promise<ClaimOut[]> {
  if (MOCK) return mocked((await fixtures()).mockClaimsHighRocksSwim);
  return request<ClaimOut[]>(`/affordances/${id}/claims`);
}

// ---------------------------------------------------------------------------
// saves / trips / verdicts / events
// ---------------------------------------------------------------------------

export interface SaveAck {
  affordance_id: string;
  kind: SaveKind;
  saved: boolean;
}

export async function listSaves(): Promise<SavedItem[]> {
  if (MOCK) return mocked((await fixtures()).mockSaves);
  return request<SavedItem[]>("/saves");
}

export async function addSave(save: SaveIn): Promise<SaveAck> {
  if (MOCK) {
    return mocked({ affordance_id: save.affordance_id, kind: save.kind, saved: true });
  }
  return post<SaveAck>("/saves", save);
}

export async function removeSave(affordance_id: string, kind: SaveKind): Promise<void> {
  if (MOCK) return mocked(undefined);
  return request<void>(`/saves?${query({ affordance_id, kind })}`, {
    method: "DELETE",
  });
}

export async function createTrip(trip: TripIn): Promise<TripOut> {
  if (MOCK) {
    const { mockTrip } = await fixtures();
    return mocked({
      ...mockTrip,
      affordance_id: trip.affordance_id,
      planned_date: trip.planned_date,
    });
  }
  return post<TripOut>("/trips", trip);
}

export async function postVerdict(verdict: VerdictIn): Promise<VerdictOut> {
  if (MOCK) {
    const { mockVerdict } = await fixtures();
    return mocked({ ...mockVerdict, claim_id: verdict.claim_id, verdict: verdict.verdict });
  }
  return post<VerdictOut>("/verdicts", verdict);
}

export async function postEvent(event: EventIn): Promise<EventOut> {
  if (MOCK) {
    return mocked({
      id: 101,
      etype: EVENT_ALIASES[event.etype] ?? event.etype,
      affordance_id: event.affordance_id,
    });
  }
  return post<EventOut>("/events", event);
}

// ---------------------------------------------------------------------------
// auth / push
// ---------------------------------------------------------------------------

export async function requestMagicLink(email: string): Promise<{ sent: boolean }> {
  if (MOCK) return mocked({ sent: true });
  return post<{ sent: boolean }>("/auth/magic-link", { email });
}

export async function verifyToken(token: string): Promise<UserOut> {
  if (MOCK) return mocked((await fixtures()).mockUser);
  return post<UserOut>("/auth/verify", { token });
}

export async function getMe(): Promise<UserOut> {
  if (MOCK) return mocked((await fixtures()).mockUser);
  return request<UserOut>("/auth/me");
}

export async function getVapidPublicKey(): Promise<string> {
  if (MOCK) return mocked((await fixtures()).mockVapidPublicKey);
  const { public_key } = await request<{ public_key: string }>("/push/vapid-public-key");
  return public_key;
}

export async function subscribePush(sub: PushSubscriptionIn): Promise<{ stored: boolean }> {
  if (MOCK) return mocked({ stored: true });
  return post<{ stored: boolean }>("/push/subscribe", sub);
}
