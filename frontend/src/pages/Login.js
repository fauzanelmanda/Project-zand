import React, { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatApiErrorDetail } from "@/lib/api";
import { KeyRound, Loader2, Car } from "lucide-react";

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("fauzan.elmanda@gmail.com");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (user && user !== null) navigate("/");
  }, [user, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(formatApiErrorDetail(err.response?.data?.detail) || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="absolute inset-0 overflow-hidden">
        <div className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-blue-100/60 blur-3xl" />
        <div className="absolute -bottom-24 -left-24 h-96 w-96 rounded-full bg-blue-50 blur-3xl" />
      </div>
      <div className="relative w-full max-w-md">
        <div className="mb-8 flex flex-col items-center text-center">
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-blue-600 text-white shadow-lg shadow-blue-600/20">
            <KeyRound className="h-7 w-7" />
          </div>
          <h1 className="font-heading text-3xl font-extrabold tracking-tight text-slate-900">
            Masuk ke ARMI Rental
          </h1>
          <p className="mt-2 text-sm text-slate-500">Sistem Manajemen Rental Kendaraan</p>
        </div>

        <form
          onSubmit={handleSubmit}
          className="rounded-2xl border border-slate-200 bg-white p-6 shadow-[0_2px_20px_rgba(0,0,0,0.04)] sm:p-8"
        >
          <div className="space-y-4">
            <div>
              <Label htmlFor="email" className="text-slate-700">Email</Label>
              <Input
                id="email"
                type="email"
                data-testid="login-email-input"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="nama@email.com"
                className="mt-1.5 h-11"
                required
              />
            </div>
            <div>
              <Label htmlFor="password" className="text-slate-700">Kata Sandi</Label>
              <Input
                id="password"
                type="password"
                data-testid="login-password-input"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="mt-1.5 h-11"
                required
              />
            </div>
            {error && (
              <div data-testid="login-error" className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600">
                {error}
              </div>
            )}
            <Button
              type="submit"
              data-testid="login-submit-button"
              disabled={loading}
              className="h-11 w-full bg-blue-600 text-base font-semibold hover:bg-blue-700"
            >
              {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : "Masuk ke Sistem"}
            </Button>
          </div>
        </form>
        <div className="mt-6 flex items-center justify-center gap-2 text-xs text-slate-400">
          <Car className="h-4 w-4" /> ARMI Rental Management &copy; 2026
        </div>
      </div>
    </div>
  );
}
