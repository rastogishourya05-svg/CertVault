"use client";
import { useEffect, useRef, useState } from "react";
import { Mic, Square } from "lucide-react";
import { Button } from "./ui/button";
import { api } from "@/lib/api";

type Phase = "idle" | "starting" | "recording" | "sending";
let activeCancel: (() => void) | null = null;

function takeMicrophone(cancel: () => void) {
  activeCancel?.();
  activeCancel = cancel;
}
function releaseMicrophone(owner: (() => void) | null) {
  if (activeCancel === owner) activeCancel = null;
}

export function Dictation({
  label,
  limit,
  compact = false,
  apply,
}: {
  label: string;
  limit: number;
  compact?: boolean;
  apply: (value: string) => void;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState("");
  const version = useRef(0),
    cleanup = useRef<() => void>(() => {}),
    finish = useRef<() => void>(() => {});
  const owner = useRef<(() => void) | null>(null);
  useEffect(
    () => () => {
      version.current++;
      cleanup.current();
      releaseMicrophone(owner.current);
    },
    [],
  );
  function cancel() {
    version.current++;
    cleanup.current();
    cleanup.current = () => {};
    releaseMicrophone(owner.current);
    setPhase("idle");

    setError("");
  }
  async function record() {
    takeMicrophone(cancel);
    owner.current = cancel;
    const run = ++version.current;
    setError("");
    setPhase("starting");
    try {
      if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext)
        throw Error("Microphone unavailable. You can type instead.");
      const status = await api<{ configured: boolean }>(
        "/account/voice/status",
      );
      if (version.current !== run) return;
      if (!status.configured)
        throw Error(
          "Voice input needs an ElevenLabs key on the server. You can still type.",
        );
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1 },
        video: false,
      });
      const stopTracks = () => stream.getTracks().forEach((t) => t.stop());
      if (version.current !== run) {
        stopTracks();
        return;
      }
      cleanup.current = stopTracks;
      const context = new AudioContext({ sampleRate: 16000 });
      const clock: { timer?: ReturnType<typeof setTimeout> } = {};
      const stop = () => {
        clearTimeout(clock.timer);
        stopTracks();
        if (context.state !== "closed") void context.close().catch(() => {});
      };
      cleanup.current = stop;
      await context.audioWorklet.addModule("/dictation.js");
      if (version.current !== run) return;
      const node = new AudioWorkletNode(context, "certvault-dictation");
      const source = context.createMediaStreamSource(stream);
      const chunks: ArrayBuffer[] = [];
      let count = 0;
      finish.current = () => {
        if (version.current !== run) return;
        finish.current = () => {};
        node.port.onmessage = null;
        stop();
        cleanup.current = () => {};
        if (!count) {
          setError("No audio recorded. Try again or type instead.");
          setPhase("idle");
          return;
        }
        void send(new Blob(chunks, { type: "application/octet-stream" }), run);
      };
      node.port.onmessage = ({ data }: { data: Int16Array }) => {
        if (version.current !== run) return;
        const part = data.slice(0, 240000 - count);
        chunks.push(part.buffer);
        count += part.length;
        if (count >= 240000) finish.current();
      };
      source.connect(node);
      node.connect(context.destination);
      await context.resume();
      if (version.current !== run) return;
      setPhase("recording");
      clock.timer = setTimeout(() => finish.current(), 15000);
    } catch (e) {
      if (version.current === run) {
        cleanup.current();
        cleanup.current = () => {};
        setError(e instanceof Error ? e.message : "Microphone unavailable.");
        setPhase("idle");
      }
    }
  }
  async function send(audio: Blob, run: number) {
    const controller = new AbortController();
    cleanup.current = () => controller.abort();
    setPhase("sending");
    setError("");
    try {
      const response = await fetch("/api/account/voice/transcribe", {
        method: "POST",
        headers: {
          "Content-Type": "application/octet-stream",
          "X-CertVault-Voice-Consent": "send-recording",
        },
        body: audio,
        signal: controller.signal,
      });
      const result = await response.json();
      if (!response.ok)
        throw Error(result.detail || "Transcription unavailable.");
      if (run !== version.current) return;
      const value = result.text?.trim();
      if (!value || value.length > limit) throw Error("Try a shorter recording or type in the field.");
      apply(value);
    } catch (e) {
      if (run === version.current)
        setError(e instanceof Error ? e.message : "Transcription unavailable.");
    } finally {
      if (run === version.current) {
        cleanup.current = () => {};
        releaseMicrophone(owner.current);
        setPhase("idle");
      }
    }
  }
  return (
    <div className="dictation">
      {phase === "idle" && (
        <Button type="button" variant="outline" aria-label={`Dictate ${label}`} title={`Dictate ${label} using ElevenLabs`} onClick={record}>
          <Mic size={17} aria-hidden="true" />{!compact && `Dictate ${label}`}
        </Button>
      )}
      {phase === "starting" && <span role="status">Opening microphone…</span>}
      {phase === "recording" && (
        <Button type="button" aria-label="Stop recording" title="Stop and transcribe" onClick={() => finish.current()}>
          <Square size={16} aria-hidden="true" /> Stop
        </Button>
      )}
      {phase === "sending" && <span role="status">Transcribing…</span>}
      {phase !== "idle" && (
        <Button type="button" variant="outline" onClick={cancel}>Cancel dictation</Button>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
