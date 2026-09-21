import createClient from "openapi-fetch";
import type { paths } from "./schema.gen";

export type { paths, components, operations } from "./schema.gen";

export function createApiClient(baseUrl: string) {
  return createClient<paths>({ baseUrl });
}
