import createClient from "openapi-fetch";
import type { paths } from "./schema.gen";

export type { paths, components, operations } from "./schema.gen";

const authenticatedFetch: typeof fetch = (input, init) => {
  const headers = new Headers(init?.headers);
  if (typeof window !== "undefined") {
    const token = window.localStorage.getItem("reimburst.access_token");
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  return fetch(input, { ...init, headers });
};

export function createApiClient(baseUrl: string) {
  return createClient<paths>({ baseUrl, fetch: authenticatedFetch });
}
