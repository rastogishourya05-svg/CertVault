"use client";
import { useEffect, useRef, useState } from "react";
import { Button } from "./ui/button";
import { api } from "@/lib/api";

type Phase = "idle" | "starting" | "recording" | "ready" | "sending" | "review";
export function Dictation({
  label,
  limit,
  apply,
}: {
  label: string;
  limit: number;
  apply: (value: string) => void;
}) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState(""),
    [text, setText] = useState("");
  const version = useRef(0),
    cleanup = useRef<() => void>(() => {}),
    finish = useRef<() => void>(() => {});
  const clip = useRef<Blob | null>(null);
  useEffect(
    () => () => {
      version.current++;
      cleanup.current();
      clip.current = null;
    },
    [],
  );
  function cancel() {
    version.current++;
    cleanup.current();
    cleanup.current = () => {};
    clip.current = null;
    setPhase("idle");
    setText("");
    setError("");
  }
  async function record() {
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
        version.current++;
        node.port.onmessage = null;
        stop();
        cleanup.current = () => {};
        if (!count) {
          setError("No audio recorded. Try again or type instead.");
          setPhase("idle");
          return;
        }
        clip.current = new Blob(chunks, { type: "application/octet-stream" });
        setPhase("ready");
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
  async function send() {
    if (!clip.current) return;
    const run = ++version.current;
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
        body: clip.current,
        signal: controller.signal,
      });
      const result = await response.json();
      if (!response.ok)
        throw Error(result.detail || "Transcription unavailable.");
      if (run !== version.current) return;
      clip.current = null;
      setText(result.text);
      setPhase("review");
    } catch (e) {
      if (run === version.current) {
        setError(e instanceof Error ? e.message : "Transcription unavailable.");
        setPhase("ready");
      }
    }
  }
  return (
    <div className="dictation">
      {phase === "idle" && (
        <Button type="button" variant="outline" onClick={record}>
          Dictate {label}
        </Button>
      )}
      {phase === "starting" && <span role="status">Opening microphone…</span>}
      {phase === "recording" && (
        <>
          <span role="status">Recording locally · 15 seconds maximum</span>
          <Button type="button" onClick={() => finish.current()}>
            Stop recording
          </Button>
        </>
      )}
      {phase === "ready" && (
        <Button type="button" onClick={send}>
          Send recording to ElevenLabs
        </Button>
      )}
      {phase === "sending" && <span role="status">Transcribing…</span>}
      {phase === "review" && (
        <>
          <label>
            Review dictation
            <input value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          {text.trim().length > limit && (
            <span>Shorten to {limit} characters.</span>
          )}
          <Button
            type="button"
            disabled={!text.trim() || text.trim().length > limit}
            onClick={() => {
              apply(text.trim());
              cancel();
            }}
          >
            Use for {label}
          </Button>
        </>
      )}
      {phase !== "idle" && (
        <Button type="button" variant="outline" onClick={cancel}>
          Cancel dictation
        </Button>
      )}
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
