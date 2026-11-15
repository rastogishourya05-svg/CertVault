"use client";
import { Button } from "@/components/ui/button";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return (
    <main className="welcome">
      <h1>Something interrupted your workspace.</h1>
      <p className="muted">Your data has not been changed. Please try again.</p>
      <Button onClick={reset}>Try again</Button>
    </main>
  );
}
