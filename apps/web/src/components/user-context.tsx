"use client";

import { createContext, useContext } from "react";
import type { User } from "@/lib/types";

const CurrentUserContext = createContext<User | null>(null);

export function UserProvider({ user, children }: { user: User | null; children: React.ReactNode }) {
  return <CurrentUserContext.Provider value={user}>{children}</CurrentUserContext.Provider>;
}

export function useCurrentUser(): User | null {
  return useContext(CurrentUserContext);
}
