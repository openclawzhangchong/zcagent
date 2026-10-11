import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

vi.mock("../../context/ThemeContext", () => ({
  useTheme: () => ({ isDark: false }),
}));

const calls: Array<[string, string]> = [];

vi.mock("../../api/modules/auth", () => ({
  authApi: {
    getAuthStatus: () => Promise.resolve({ setup_required: false }),
    getLocalRecovery: () =>
      Promise.resolve({ available: true, username: "admin" }),
    getOauthStatus: () => Promise.resolve({ providers: [] }),
    getCaptcha: () => Promise.resolve({ provider: "none" }),
    localReset: (username: string, password: string) => {
      calls.push([username, password]);
      return Promise.resolve({ username, reset: true });
    },
  },
}));

vi.mock("../../utils/locale", () => ({
  applyGuestLocale: () => Promise.resolve(),
  applyUserLocale: () => Promise.resolve(),
}));

vi.mock("./CaptchaField", () => ({
  default: () => null,
}));

import LoginPage from "./index";

describe("Login local password recovery", () => {
  it("names the existing account and resets it without a terminal", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    );

    const hint = await screen.findByTestId("login-existing-install-hint");
    expect(hint.textContent).toContain("admin");

    await user.click(screen.getByTestId("login-forgot-password-toggle"));
    const form = await screen.findByTestId("login-local-reset");

    // The whole point: no shell command on a machine that can just do it.
    expect(form.textContent).not.toMatch(/octop user passwd/);

    const passwordFields = Array.from(
      form.querySelectorAll<HTMLInputElement>("input"),
    ).filter((el) => el.type === "password");
    const [newPassword, confirm] = passwordFields;

    await user.type(newPassword, "abc");
    await user.type(confirm, "different");
    expect(form.textContent).toMatch(/do not match|不一致/);
    expect(
      screen.getByRole("button", { name: /Reset password|重置密码/ }),
    ).toBeDisabled();

    await user.clear(newPassword);
    await user.clear(confirm);
    await user.type(newPassword, "Passw0rd123");
    await user.type(confirm, "Passw0rd123");
    const submit = screen.getByRole("button", {
      name: /Reset password|重置密码/,
    });
    expect(submit).toBeEnabled();
    await user.click(submit);

    await waitFor(() => {
      expect(calls).toEqual([["admin", "Passw0rd123"]]);
    });
  });
});
