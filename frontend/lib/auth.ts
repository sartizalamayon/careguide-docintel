// Google sign-in (Auth.js / next-auth v4, JWT sessions, no database). Used only to identify the user who
// manages their own Groq key; the rest of the app works signed out.
import type { NextAuthOptions } from "next-auth";
import GoogleProvider from "next-auth/providers/google";

const clientId = process.env.GOOGLE_CLIENT_ID ?? "";
const clientSecret = process.env.GOOGLE_CLIENT_SECRET ?? "";

export const googleConfigured = Boolean(clientId && clientSecret);

export const authOptions: NextAuthOptions = {
  providers: googleConfigured ? [GoogleProvider({ clientId, clientSecret })] : [],
  session: { strategy: "jwt" },
  // A fixed fallback keeps `npm run dev` working before NEXTAUTH_SECRET is set; production must set it.
  secret: process.env.NEXTAUTH_SECRET ?? (process.env.NODE_ENV === "production" ? undefined : "docintel-dev-only-secret"),
};
