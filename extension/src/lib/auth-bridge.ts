export const MDTERO_ACCOUNT_URL = "https://mdtero.com/auth?source=extension";

const TRUSTED_SITE_ORIGINS = new Set([
  "https://mdtero.com",
  "https://www.mdtero.com"
]);

const TRUSTED_LOCAL_DEV_HOST_PATTERNS = [
  /^localhost$/i,
  /^127\.0\.0\.1$/i
];

export interface MdteroAuthBridgeEvent {
  currentOrigin: string;
  eventOrigin: string;
  data: unknown;
}

export interface MdteroAuthTokenPayload {
  type: "mdtero.auth.token";
  token: string;
  email: string;
  source: "extension";
  issuedAt: number;
}

export function isMdteroAuthTokenPayload(data: unknown): data is MdteroAuthTokenPayload {
  return Boolean(
    data &&
      typeof data === "object" &&
      "type" in data &&
      "token" in data &&
      "email" in data &&
      (data as Record<string, unknown>).type === "mdtero.auth.token" &&
      (data as Record<string, unknown>).source === "extension" &&
      typeof (data as Record<string, unknown>).token === "string" &&
      typeof (data as Record<string, unknown>).email === "string" &&
      typeof (data as Record<string, unknown>).issuedAt === "number" &&
      (data as Record<string, unknown>).token &&
      (data as Record<string, unknown>).email &&
      isFreshAuthBridgeTimestamp(Number((data as Record<string, unknown>).issuedAt))
  );
}

export function isFreshAuthBridgeTimestamp(issuedAt: number, now = Date.now()): boolean {
  if (!Number.isFinite(issuedAt)) {
    return false;
  }
  const ageMs = Math.abs(now - issuedAt);
  return ageMs <= 60_000;
}

export function isTrustedMdteroOrigin(origin: string): boolean {
  try {
    const url = new URL(origin);
    if (TRUSTED_SITE_ORIGINS.has(url.origin)) {
      return true;
    }
    return (
      url.protocol === "http:" &&
      TRUSTED_LOCAL_DEV_HOST_PATTERNS.some((pattern) => pattern.test(url.hostname))
    );
  } catch {
    return false;
  }
}

export function shouldAcceptMdteroAuthMessage(event: MdteroAuthBridgeEvent): boolean {
  if (!isTrustedMdteroOrigin(event.currentOrigin)) {
    return false;
  }
  if (!isTrustedMdteroOrigin(event.eventOrigin)) {
    return false;
  }
  if (event.currentOrigin !== event.eventOrigin) {
    return false;
  }
  return isMdteroAuthTokenPayload(event.data);
}
