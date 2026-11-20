import { useState, type FormEvent } from "react";
import { ApiError, login, register } from "../../services/api";
import ErrorNotice from "../common/ErrorNotice";

interface AuthFormProps {
  onAuthenticated: () => void;
}

export default function AuthForm({ onAuthenticated }: AuthFormProps) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      if (mode === "signup") await register(fullName.trim(), email.trim(), password);
      await login(email.trim(), password);
      onAuthenticated();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  const input = "w-full rounded-lg border border-[#353535] bg-[#262626] px-3 py-2 text-sm text-[#F5F5F5] placeholder:text-[#A3A3A3] focus:border-[#A3A3A3] focus:outline-none";

  return (
    <div className="flex h-screen items-center justify-center bg-[#0D0D0D] text-[#F5F5F5]">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-3 rounded-lg border border-[#353535] bg-[#171717] p-6"
      >
        <h1 className="text-lg font-semibold">
          {mode === "login" ? "Sign in" : "Create account"}
        </h1>
        {mode === "signup" && (
          <input
            className={input}
            placeholder="Full name"
            autoComplete="name"
            minLength={2}
            required
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />
        )}
        <input
          className={input}
          type="email"
          placeholder="Email"
          autoComplete="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        <input
          className={input}
          type="password"
          placeholder={mode === "signup" ? "Password (min 12 characters)" : "Password"}
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          minLength={mode === "signup" ? 12 : undefined}
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        {error && <ErrorNotice message={error} onDismiss={() => setError(null)} />}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-[#F5F5F5] px-3 py-2 text-sm font-medium text-[#0D0D0D] hover:bg-white disabled:opacity-50"
        >
          {busy ? "Please wait…" : mode === "login" ? "Sign in" : "Sign up"}
        </button>
        <button
          type="button"
          className="w-full text-xs text-[#A3A3A3] underline hover:text-[#F5F5F5]"
          onClick={() => {
            setMode(mode === "login" ? "signup" : "login");
            setError(null);
          }}
        >
          {mode === "login" ? "No account? Sign up" : "Have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
