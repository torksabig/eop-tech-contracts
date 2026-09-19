/** Demo auth only — client-side credential check. Not for production. */

export type Role = "owner" | "member";

export type SessionUser = {
  email: string;
  role: Role;
  firm: string;
};

type SeedUser = SessionUser & {
  password: string;
};

const SESSION_KEY = "eop-tech-contracts-session-v1";

/** Seeded demo accounts. Password is demo-only and checked in the browser. */
const SEED_USERS: SeedUser[] = [
  {
    email: "thiidenlampi@gmail.com",
    password: "12345",
    role: "owner",
    firm: "demo-firm",
  },
];

export function authenticate(
  email: string,
  password: string,
): SessionUser | null {
  const normalized = email.trim().toLowerCase();
  const match = SEED_USERS.find(
    (u) => u.email.toLowerCase() === normalized && u.password === password,
  );
  if (!match) return null;
  return { email: match.email, role: match.role, firm: match.firm };
}

export function loadSession(): SessionUser | null {
  try {
    const raw = localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as SessionUser;
    if (
      !parsed ||
      typeof parsed.email !== "string" ||
      typeof parsed.firm !== "string" ||
      (parsed.role !== "owner" && parsed.role !== "member")
    ) {
      return null;
    }
    // Re-validate against seed so revoked accounts drop out
    const stillValid = SEED_USERS.some(
      (u) => u.email.toLowerCase() === parsed.email.toLowerCase(),
    );
    if (!stillValid) {
      clearSession();
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function persistSession(user: SessionUser) {
  localStorage.setItem(SESSION_KEY, JSON.stringify(user));
}

export function clearSession() {
  localStorage.removeItem(SESSION_KEY);
}

export function savedStorageKey(email: string) {
  const safe = email.trim().toLowerCase().replace(/[^a-z0-9@._-]/g, "_");
  return `eop-tech-contracts-saved-v1:${safe}`;
}
