import { useEffect, useRef, useState } from "react";
import { LABELS } from "../lib/narration";
import type { Lang, Recap } from "../types";

interface Props {
  recap: Recap | null;
  onClose: () => void;
  lang: Lang;
  /** MP3 of this recap; null when narration is off. */
  audioUrl: string | null;
  /** Called before the recap starts playing, so the insight queue goes quiet. */
  onListen?: () => void;
}

type Playback = "idle" | "playing" | "failed";

export function RecapDialog({ recap, onClose, lang, audioUrl, onListen }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playback, setPlayback] = useState<Playback>("idle");
  const L = LABELS[lang];

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (recap && !d.open) d.showModal();
    if (!recap && d.open) d.close();
    if (!recap) {
      audio.current?.pause();
      setPlayback("idle");
    }
  }, [recap]);

  const toggle = () => {
    if (!audioUrl) return;
    if (playback === "playing") {
      audio.current?.pause();
      setPlayback("idle");
      return;
    }
    onListen?.();
    const a = audio.current ?? (audio.current = new Audio());
    a.onended = () => setPlayback("idle");
    a.onerror = () => setPlayback("failed");
    a.src = audioUrl;
    setPlayback("playing");
    a.play().catch(() => setPlayback("failed"));
  };

  return (
    <dialog ref={ref} className="recap" onClose={onClose}>
      {recap ? (
        <article>
          <header>
            <h2>{recap.title}</h2>
            <span className="badge badge--source">{recap.source === "llm" ? "Foundry" : "template"}</span>
          </header>
          {recap.paragraphs.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
          {recap.key_moments.length ? (
            <ol>
              {recap.key_moments.map((k, i) => (
                <li key={i}>{k}</li>
              ))}
            </ol>
          ) : null}
          <footer className="recap__actions">
            {audioUrl ? (
              <button type="button" className="button" aria-pressed={playback === "playing"} onClick={toggle}>
                {playback === "playing" ? L.stop : L.listen}
              </button>
            ) : null}
            {playback === "failed" ? <span className="recap__note">{L.unavailable}</span> : null}
            <button type="button" className="button" onClick={onClose}>
              Close
            </button>
          </footer>
        </article>
      ) : null}
    </dialog>
  );
}
