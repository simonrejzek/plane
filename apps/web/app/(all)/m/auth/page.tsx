/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 *
 * Mobile WebView auth page used by the official Plane mobile app.
 * Path: /m/auth
 */

import { useEffect, useRef, useState } from "react";
import { observer } from "mobx-react";
import { useSearchParams } from "react-router";
import { Eye, EyeOff } from "lucide-react";
// plane imports
import { API_BASE_URL } from "@plane/constants";
import { Button } from "@plane/propel/button";
import { Input } from "@plane/ui";
// services
import { AuthService } from "@/services/auth.service";

const authService = new AuthService();

/**
 * Deep-link scheme the official Plane iOS/Android app listens for after login.
 * When a session token is present, hand control back to the native app.
 */
const MOBILE_APP_SCHEME = "app.plane.so";

function MobileAuthPage() {
  const [searchParams] = useSearchParams();
  const formRef = useRef<HTMLFormElement | null>(null);

  const emailParam = searchParams.get("email") || "";
  const errorCode = searchParams.get("error_code");
  const errorMessage = searchParams.get("error_message");
  const sessionToken = searchParams.get("token");

  const [email, setEmail] = useState(emailParam);
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [csrfToken, setCsrfToken] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [step, setStep] = useState<"email" | "password">(emailParam ? "password" : "email");

  useEffect(() => {
    void authService
      .requestCSRFToken()
      .then((res) => {
        if (res?.csrf_token) setCsrfToken(res.csrf_token);
      })
      .catch(() => {
        // page can still try; form may fail without CSRF
      });
  }, []);

  // After successful mobile login the API redirects back here with ?token=
  useEffect(() => {
    if (!sessionToken) return;
    // Hand off to the native app
    window.location.replace(`${MOBILE_APP_SCHEME}://?token=${sessionToken}`);
  }, [sessionToken]);

  const errorText = (() => {
    if (!errorCode && !errorMessage) return null;
    if (errorMessage === "USER_NOT_ONBOARDED") {
      return "This account has not completed onboarding on the web app yet. Open Plane in a browser, finish setup, then try again.";
    }
    if (errorMessage === "USER_DOES_NOT_EXIST" || errorMessage === "AUTHENTICATION_FAILED_SIGN_IN") {
      return "Invalid email or password.";
    }
    if (errorMessage === "INSTANCE_NOT_CONFIGURED") {
      return "This Plane instance is not fully set up yet.";
    }
    return errorMessage || `Sign-in failed (${errorCode}).`;
  })();

  const continueToPassword = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) return;
    setStep("password");
  };

  const submitPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formRef.current || !password) return;
    setSubmitting(true);
    // ensure latest csrf
    try {
      if (!csrfToken) {
        const res = await authService.requestCSRFToken();
        if (res?.csrf_token) {
          setCsrfToken(res.csrf_token);
          const el = formRef.current.querySelector<HTMLInputElement>("input[name=csrfmiddlewaretoken]");
          if (el) el.value = res.csrf_token;
        }
      }
    } catch {
      // continue
    }
    formRef.current.submit();
  };

  return (
    <div className="relative flex min-h-screen w-screen flex-col bg-surface-1">
      <div className="flex flex-1 flex-col items-center justify-center px-6 py-10">
        <div className="mb-8 text-center">
          <div className="text-h4-semibold text-primary">Plane</div>
          <p className="mt-1 text-body-xs-regular text-tertiary">Sign in to continue in the app</p>
        </div>

        <div className="w-full max-w-sm space-y-4">
          <div className="space-y-1 text-center">
            <h1 className="text-h3-semibold text-primary">Log in</h1>
          </div>

          {errorText && (
            <div className="rounded-md border border-danger-subtle bg-danger-subtle px-3 py-2 text-body-xs-regular text-danger-primary">
              {errorText}
            </div>
          )}

          {sessionToken ? (
            <div className="rounded-md border border-subtle bg-layer-1 px-3 py-4 text-center text-body-xs-regular text-secondary">
              Signed in. Returning to the Plane app…
            </div>
          ) : step === "email" ? (
            <form className="space-y-3" onSubmit={continueToPassword}>
              <div className="space-y-1">
                <label className="text-caption-sm-medium text-secondary" htmlFor="mobile-email">
                  Email
                </label>
                <Input
                  id="mobile-email"
                  type="email"
                  autoComplete="email"
                  autoFocus
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@company.com"
                  className="w-full"
                />
              </div>
              <Button type="submit" variant="primary" className="w-full" size="lg">
                Continue
              </Button>
            </form>
          ) : (
            <form
              ref={formRef}
              className="space-y-3"
              method="POST"
              action={`${API_BASE_URL}/auth/mobile/sign-in/`}
              onSubmit={(e) => void submitPassword(e)}
            >
              <input type="hidden" name="csrfmiddlewaretoken" value={csrfToken} />
              <input type="hidden" name="email" value={email} />

              <div className="space-y-1">
                <label className="text-caption-sm-medium text-secondary" htmlFor="mobile-email-ro">
                  Email
                </label>
                <Input
                  id="mobile-email-ro"
                  type="email"
                  value={email}
                  disabled
                  className="w-full"
                  onChange={() => undefined}
                />
                <button
                  type="button"
                  className="text-caption-sm-regular text-link-primary hover:underline"
                  onClick={() => {
                    setStep("email");
                    setPassword("");
                  }}
                >
                  Change email
                </button>
              </div>

              <div className="space-y-1">
                <label className="text-caption-sm-medium text-secondary" htmlFor="mobile-password">
                  Password
                </label>
                <div className="relative">
                  <Input
                    id="mobile-password"
                    name="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    autoFocus
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter password"
                    className="w-full pr-10"
                  />
                  <button
                    type="button"
                    className="absolute top-1/2 right-3 -translate-y-1/2 text-tertiary"
                    onClick={() => setShowPassword((v) => !v)}
                    tabIndex={-1}
                  >
                    {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
              </div>

              <Button type="submit" variant="primary" className="w-full" size="lg" loading={submitting}>
                Log in
              </Button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

export default observer(MobileAuthPage);
