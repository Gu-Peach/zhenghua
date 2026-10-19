import { request } from "./client";

export interface AgentInfo { id: string; name: string; code: string; description: string; status: string; version: string; available: boolean }
const definitions = [
  { id: "extraction", name: "图纸提取智能体", code: "Extraction Agent", description: "分类图纸、提取连接并完成跨页补全，使用数据库中已上传的提取 Skills。" },
  { id: "explain", name: "来源解释智能体", code: "Explain Agent", description: "检索线表与图纸，解释信息来源；按要求生成修改对照，确认后保存。" },
  { id: "profile", name: "规则配置智能体", code: "Profile Agent", description: "通过对话和样图逐步建立分页、提取与跨页补全规则，确认读图结果后手动发布。" },
];

export async function agentCatalog(): Promise<AgentInfo[]> {
  const capabilities = await request<Record<string, boolean>>("/api/v1/capabilities");
  return definitions.map(item => ({ ...item, available: capabilities[item.id] === true,
    status: capabilities[item.id] === true ? "已接入" : "待接入", version: "1.0.0" }));
}

export function skillName(profileKey: string): string {
  return profileKey.endsWith("_extraction") ? profileKey : `${profileKey}_extraction`;
}
