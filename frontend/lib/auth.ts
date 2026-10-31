// Google sign-in (Auth.js / next-auth v4, JWT sessions, no database). Used only to identify the user who
// manages their own Groq key; the rest of the app works signed out.
import { createHash } from "node:crypto";
import type { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";

const clientId = process.env.GOOGLE_CLIENT_ID ?? "";
const clientSecret = process.env.GOOGLE_CLIENT_SECRET ?? "";

export const googleConfigured = Boolean(clientId && clientSecret);

export const authOptions: NextAuthOptions = {
  providers: googleConfigured ? [GoogleProvider({ clientId, clientSecret })] : [],
  session: { strategy: "jwt" },
  // Without NEXTAUTH_SECRET, derive one from the server-only API_KEY so sessions still work (and never crash the app).
  secret: process.env.NEXTAUTH_SECRET || sessionSecretFallback(),
};

function sessionSecretFallback(): string {
  const apiKey = process.env.API_KEY ?? "";
  return apiKey ? createHash("sha256").update(`nextauth:${apiKey}`).digest("hex") : "docintel-dev-only-secret";
}
