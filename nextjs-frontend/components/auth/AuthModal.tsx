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
}

/** Reusable passwordless auth modal — same flow as /login's AuthCard, just
 * without the two-column wave-art shell (modals stay compact). Not wired to
 * a trigger anywhere in the app yet; drop it in wherever a "sign in" action
 * needs to happen without a full page navigation. */
export function AuthModal({ trigger, open, onOpenChange }: AuthModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {trigger && <DialogTrigger asChild>{trigger}</DialogTrigger>}
      <DialogContent className="max-w-md p-0">
        <AuthCard mode="modal" onSuccess={() => onOpenChange?.(false)} />
      </DialogContent>
    </Dialog>
  );
}
