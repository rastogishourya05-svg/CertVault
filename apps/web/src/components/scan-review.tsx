"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Button } from "./ui/button";
import { Dictation } from "./dictation";

const prompts = {
  summary: "What happened?",
  attention: "What needs attention?",
  missing: "Why is a certificate missing?",
  open: "Show saved items",
};
type Intent = keyof typeof prompts;
export function ScanReview({ id }: { id: string }) {
  const [answer, setAnswer] = useState("");
  const [intent, setIntent] = useState<Intent>("summary");
  const [busy, setBusy] = useState(false);
  useEffect(() => () => window.speechSynthesis?.cancel(), []);
  async function ask(choice: Intent) {
    if (busy) return;
    window.speechSynthesis?.cancel();
    setBusy(true);
    setIntent(choice);
    setAnswer("");
    try {
      const result = await api<{ answer: string }>(
        `/account/pipeline/jobs/${id}/explain`,
        "POST",
        { intent: choice },
      );
      setAnswer(result.answer);
    } catch {
      setAnswer(
        "Scan review is unavailable. Try again after refreshing Activity.",
      );
    } finally {
      setBusy(false);
    }
  }
  function dictate(text: string) {
    if (/miss|didn.t|not find|not found|where is/i.test(text))
      void ask("missing");
    else if (/attention|approval|review|why/i.test(text)) void ask("attention");
    else if (/show|open|vault/i.test(text)) void ask("open");
    else if (/summary|happened|scan|result/i.test(text)) void ask("summary");
    else setAnswer("Choose one of the questions above to review this scan.");
  }
  return (
    <details>
      <summary>Talk me through my latest scan</summary>
      <div className="automation-actions">
        {(Object.keys(prompts) as Intent[]).map((choice) => (
          <Button
            type="button"
            variant="outline"
            disabled={busy}
            key={choice}
            onClick={() => void ask(choice)}
          >
            {prompts[choice]}
          </Button>
        ))}
      </div>
      <Dictation label="scan question" limit={240} apply={dictate} />
      <p role="status">{busy ? "Checking this scan…" : answer}</p>
      {answer && (
        <div className="automation-actions">
          {"speechSynthesis" in window && (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                window.speechSynthesis.cancel();
                window.speechSynthesis.speak(
                  new SpeechSynthesisUtterance(answer),
                );
              }}
            >
              Read answer aloud
            </Button>
          )}
          {intent === "open" && <a href="#private-vault">Open My vault</a>}
          {intent === "attention" && (
            <a href="#approvals">Open Approval inbox</a>
          )}
          {intent === "missing" && (
            <a href="#mailboxes">Check mailbox and scan range</a>
          )}
        </div>
      )}
    </details>
  );
}
