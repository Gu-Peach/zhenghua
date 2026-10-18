import { memo, useEffect } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useTypewriterText } from "@/hooks/useTypewriterText";

const plugins = [remarkGfm];
const MarkdownBody = memo(function MarkdownBody({ text }: { text: string }) {
  return <Markdown skipHtml remarkPlugins={plugins} disallowedElements={["img", "input"]} unwrapDisallowed components={{
    a: ({ href, children }) => href ? <a href={href} target="_blank" rel="noopener noreferrer">{children}</a> : <span>{children}</span>,
  }}>{text}</Markdown>;
});

export function TypewriterAnswer({ text, running, halted, onProgress, onReady }: { text: string; running: boolean; halted: boolean; onProgress: () => void; onReady?: (ready: boolean) => void }) {
  const { text: visible, typing, finish } = useTypewriterText(text, halted);
  useEffect(() => { onProgress(); }, [visible, onProgress]);
  useEffect(() => { onReady?.(!running && !typing); }, [running, typing, onReady]);
  return <>
    <div className="explain-answer" aria-label="解释回复" aria-busy={running || typing} data-typing={typing}>
      <MarkdownBody text={visible} />
      {typing || running ? <span className="explain-cursor" aria-hidden="true" /> : null}
    </div>
    {typing ? <button type="button" className="explain-show-all" onClick={finish}>立即显示已收到内容</button> : null}
  </>;
}
