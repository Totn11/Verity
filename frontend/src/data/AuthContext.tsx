import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  getCurrentSession,
  signIn as requestSignIn,
  signOut as requestSignOut,
  type AuthenticatedUser,
} from "../services/authApiService";

type AuthContextValue = {
  status: "checking" | "authenticated" | "unauthenticated";
  user: AuthenticatedUser | null;
  initialError: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthContextValue["status"]>("checking");
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [initialError, setInitialError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getCurrentSession().then((session) => {
      if (!active) return;
      setUser(session);
      setStatus("authenticated");
    }).catch((error: unknown) => {
      if (!active) return;
      if (error instanceof Error && error.message !== "Sign in is required.") {
        setInitialError(error.message);
      }
      setStatus("unauthenticated");
    });
    return () => {
      active = false;
    };
  }, []);

  const value = useMemo<AuthContextValue>(() => ({
    status,
    user,
    initialError,
    signIn: async (email, password) => {
      const authenticatedUser = await requestSignIn(email, password);
      setUser(authenticatedUser);
      setInitialError(null);
      setStatus("authenticated");
    },
    signOut: async () => {
      await requestSignOut();
      setUser(null);
      setStatus("unauthenticated");
    },
  }), [status, user, initialError]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used inside AuthProvider.");
  return context;
}
