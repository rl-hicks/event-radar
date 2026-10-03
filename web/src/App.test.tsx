import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { AppRoutes } from "./App";
import { AuthProvider } from "./auth";

test("protected app redirects unauthenticated users to sign in", async () => {
  render(
    <MemoryRouter initialEntries={["/app"]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );

  expect(await screen.findByRole("heading", { name: "Sign in" })).toBeInTheDocument();
});

test("landing page does not pretend V1 exists", () => {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );

  expect(screen.getByText(/E0 product foundation/)).toBeInTheDocument();
  expect(screen.queryByText(/Weekend Packet/)).not.toBeInTheDocument();
});
