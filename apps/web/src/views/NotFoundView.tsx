import { FileQuestion } from "lucide-react";
import { Link } from "react-router-dom";

export function NotFoundView() {
  return <main className="not-found"><FileQuestion size={36} /><h1>页面不存在</h1><p>当前地址没有对应的项目页面。</p><Link to="/projects/peru-tpp-1-sts">返回项目工作台</Link></main>;
}
