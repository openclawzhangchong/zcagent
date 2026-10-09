import { request } from "../request";
import type { Branding } from "../../branding/runtime";

export type { Branding };

export const brandingApi = {
  get: () => request<Branding>("/branding"),
  save: (payload: Branding) =>
    request<Branding>("/branding", {
      method: "PUT",
      body: JSON.stringify(payload),
    }),
};
