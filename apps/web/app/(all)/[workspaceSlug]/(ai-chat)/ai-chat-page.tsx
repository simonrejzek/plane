/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useMemo, useRef } from "react";
import { useNavigate, useParams } from "react-router";
import { PageHead } from "@/components/core/page-title";

/**
 * In-shell Pilot AI — embeds self-hosted PI UI while keeping the Business
 * App Rail (Projects / Wiki / AI) like app.plane.so.
 *
 * Cloud uses a commercial React Pilot tree against pi.plane.so. Self-host
 * serves a PI-compatible UI from the plane-pi service on the same routes.
 *
 * Iframe src is fixed per workspace so chat navigation does not remount
 * Pilot; the embed posts path updates back to the shell.
 *
 * Routes: /:workspaceSlug/ai-chat/*  (and /pi-chat/* alias)
 */
export default function AiChatPage() {
  const params = useParams();
  const navigate = useNavigate();
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const slug = params.workspaceSlug?.toString() ?? "";

  // splat: "", "new", or "{chatId}"
  const splat = (params["*"] ?? params.chatId ?? "").toString().replace(/^\/+|\/+$/g, "");
  const initialChatId = useRef(splat && splat !== "new" ? splat : undefined);

  const src = useMemo(() => {
    const q = new URLSearchParams();
    q.set("embed", "1");
    if (slug) q.set("workspace", slug);
    if (initialChatId.current) q.set("chat_id", initialChatId.current);
    return `/cosmic-pilot/ui?${q.toString()}`;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- stable per workspace mount
  }, [slug]);

  const onMessage = useCallback(
    (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return;
      const data = event.data;
      if (!data || data.source !== "plane-pilot") return;

      if (data.type === "navigate" && typeof data.path === "string" && data.path.startsWith("/")) {
        if (window.location.pathname !== data.path) {
          navigate(data.path, { replace: Boolean(data.replace) });
        }
      }
    },
    [navigate]
  );

  useEffect(() => {
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [onMessage]);

  return (
    <>
      <PageHead title="AI" />
      <div className="relative flex h-full min-h-0 w-full flex-1 flex-col overflow-hidden">
        <iframe
          ref={iframeRef}
          title="Plane Intelligence"
          src={src}
          className="absolute inset-0 h-full w-full border-0 bg-surface-1"
          allow="clipboard-read; clipboard-write"
        />
      </div>
    </>
  );
}
