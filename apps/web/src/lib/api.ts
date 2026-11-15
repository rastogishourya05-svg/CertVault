export type { Certificate } from "./generated";
export type Connection = {
  id: string;
  provider: "gmail" | "outlook";
  active: number;
  created: string;
};
export type ImportItem = {
  id: string;
  title: string;
  issuer: string;
  declared_size: number;
  status: string;
  certificate_id: string | null;
};
export type Notice = {
  id: string;
  message: string;
  read: number;
  created: string;
};
export type Audit = { id: string; event: string; created: string };
export type Settings = {
  threshold_mib: number;
  name: string;
  hard_cap_mib: number;
};
export type Share = {
  id: string;
  certificate_id: string;
  title: string;
  expires: number;
  revoked: number;
};
export type Profile = {
  enabled: boolean;
  slug: string;
  name: string;
  featured: string[];
};
export type Draft = {
  id: string;
  certificate_id: string;
  tone: string;
  content: string;
  created: string;
};
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const result = await fetch(`/api${path}`, {
    method,
    credentials: "same-origin",
    headers:
      body instanceof FormData ? {} : { "Content-Type": "application/json" },
    body:
      body instanceof FormData
        ? body
        : body === undefined
          ? undefined
          : JSON.stringify(body),
  });
  if (!result.ok) {
    const error = await result
      .json()
      .catch(() => ({ detail: "The service is unavailable. Please retry." }));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : "Please check the entered values and try again.",
    );
  }
  return result.json() as Promise<T>;
}
