import { useState, type FormEvent } from "react";
import { useAuth } from "../auth";
import { btnCls, ErrorText, Field, inputCls } from "../components/ui";

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-brand-teal/10 p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-xl bg-white p-6 shadow">
        <div className="flex flex-col items-center gap-2 text-center">
          <img src="/logo.svg" alt="Logo Kampung Adem" className="h-24" />
          <h1 className="text-xl font-semibold text-brand-teal">Kampung Adem</h1>
          <p className="text-sm text-ink-2">Peta panas dan peringatan dini tingkat RW</p>
        </div>
        <Field label="Email">
          <input className={inputCls} type="email" value={email} onChange={(e) => setEmail(e.target.value)} required autoFocus />
        </Field>
        <Field label="Kata sandi">
          <input className={inputCls} type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </Field>
        <ErrorText error={error} />
        <button className={`${btnCls} w-full`} disabled={busy}>
          {busy ? "Memproses..." : "Masuk"}
        </button>
        <p className="text-center text-xs text-ink-3">
          Demo: admin@demo.kampungadem.id / adem-demo-2026
        </p>
      </form>
    </div>
  );
}
