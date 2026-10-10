import { Check, Circle, XCircle } from "lucide-react";
import type { StageEvent } from "@/apis/types";

export function StageTimeline({ events }: { events: StageEvent[] }) {
  return (
    <section className="stage-timeline">
      <header><div><span className="section-kicker">RUN EVENTS</span><h3>处理过程</h3></div><span className="version-label">运行记录 #RUN-20261008-014</span></header>
      {events.length ? <ol>{events.map((event) => (
        <li key={event.id} className={`timeline-item timeline-${event.status}`}>
          <span className="timeline-icon">{event.status === "done" ? <Check size={16} /> : event.status === "failed" ? <XCircle size={16} /> : event.status === "active" ? <Circle size={13} className="agent-wait-circle" /> : <Circle size={13} />}</span>
          <div className="timeline-copy"><span>{event.stage}</span><strong>{event.title}</strong><p>{event.detail}</p></div>{event.timestamp ? <time>{event.timestamp}</time> : null}
        </li>
      ))}</ol> : <div className="timeline-empty"><Circle size={18} /><strong>尚无处理事件</strong><span>运行任务后，阶段事件会显示在此处。</span></div>}
    </section>
  );
}
