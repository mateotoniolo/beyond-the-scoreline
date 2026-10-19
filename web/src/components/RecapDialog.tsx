import { useEffect, useRef } from "react";
import type { Recap } from "../types";

interface Props {
  recap: Recap | null;
  onClose: () => void;
}

export function RecapDialog({ recap, onClose }: Props) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (recap && !d.open) d.showModal();
    if (!recap && d.open) d.close();
  }, [recap]);
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
          <button type="button" className="button" onClick={onClose}>
            Close
          </button>
        </article>
      ) : null}
    </dialog>
  );
}
