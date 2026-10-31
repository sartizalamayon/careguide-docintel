"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

export type ReviewAction = "save" | "approve";

const COPY: Record<ReviewAction, { title: string; description: string; confirm: string }> = {
  save: { title: "Save corrections", description: "Your name is stored with every change.", confirm: "Save corrections" },
  approve: { title: "Approve invoice", description: "Approving marks this invoice as checked.", confirm: "Approve" },
};

interface ActionDialogProps {
  action: ReviewAction | null;
  reviewer: string;
  pending: boolean;
  onConfirm: (reviewer: string, note: string) => void;
  onClose: () => void;
}

function ActionForm({ action, reviewer, pending, onConfirm, onClose }: ActionDialogProps & { action: ReviewAction }) {
  const [name, setName] = useState(reviewer);
  const [note, setNote] = useState("");
  const copy = COPY[action];
  const valid = name.trim().length > 0;

  return (
    <form
      className="grid gap-4"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) onConfirm(name.trim(), note.trim());
      }}
    >
      <DialogHeader>
        <DialogTitle>{copy.title}</DialogTitle>
        <DialogDescription>{copy.description}</DialogDescription>
      </DialogHeader>
      <div className="grid gap-1.5">
        <Label htmlFor="reviewer-name">Your name</Label>
        <Input id="reviewer-name" value={name} maxLength={80} autoFocus onChange={(e) => setName(e.target.value)} />
      </div>
      <div className="grid gap-1.5">
        <Label htmlFor="reviewer-note">Note (optional)</Label>
        <Textarea id="reviewer-note" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
      </div>
      <DialogFooter>
        <Button type="button" variant="outline" onClick={onClose}>Cancel</Button>
        <Button type="submit" disabled={!valid || pending}>{copy.confirm}</Button>
      </DialogFooter>
    </form>
  );
}

export function ActionDialog(props: ActionDialogProps) {
  const { action, onClose } = props;
  return (
    <Dialog open={action !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>{action && <ActionForm {...props} action={action} />}</DialogContent>
    </Dialog>
  );
}
