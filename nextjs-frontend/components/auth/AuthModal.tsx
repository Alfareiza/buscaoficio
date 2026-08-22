"use client";

import type { ReactNode } from "react";

import { Dialog, DialogContent, DialogTrigger } from "@/components/ui/dialog";
import { AuthCard } from "./AuthCard";

interface AuthModalProps {
  /** Renders as the Dialog's trigger (uncontrolled usage). Omit when driving
   * `open`/`onOpenChange` from a parent instead. */
  trigger?: ReactNode;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** Passed straight through to AuthCard — see its googleAuthorizeUrl doc.
   * This is a client component, so it can't read the server-only
   * API_BASE_URL env var itself; whoever renders the modal (a server
   * component) needs to supply it. */
  googleAuthorizeUrl: string;
}

/** Reusable passwordless auth modal — same flow as /login's AuthCard, just
 * without the two-column wave-art shell (modals stay compact). Not wired to
 * a trigger anywhere in the app yet; drop it in wherever a "sign in" action
 * needs to happen without a full page navigation. */
export function AuthModal({
  trigger,
  open,
  onOpenChange,
  googleAuthorizeUrl,
}: AuthModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
      <DialogContent className="max-w-md p-0">
        <AuthCard
          mode="modal"
          googleAuthorizeUrl={googleAuthorizeUrl}
          onSuccess={() => onOpenChange?.(false)}
        />
      </DialogContent>
    </Dialog>
  );
}
