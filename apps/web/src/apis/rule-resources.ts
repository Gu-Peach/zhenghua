import type { RulePackage } from "./projects";

export interface RuleExampleImage { path: string; url?: string; role: string; note: string }
export interface RuleExample { id: string; title: string; description: string; images: RuleExampleImage[]; expected?: string; input?: string }
export interface RuleStage { title: string; prompt: string; description: string; readme: string; examples: RuleExample[] }

function record(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
function parsed(content?: string): Record<string, unknown> {
  try { return record(JSON.parse(content ?? "{}") as unknown); } catch { return {}; }
}
function text(value: unknown): string { return typeof value === "string" ? value : ""; }

/** Match immutable package paths; never turn an untrusted manifest path into a request URL. */
export function ruleStages(data: RulePackage): RuleStage[] {
  const files = new Map(data.files.map(file => [file.path, file.content]));
  const images = new Map(data.images.map(image => [image.path, image.url]));
  const resources = record(parsed(files.get("profile.json")).resources);
  const wiringRoot = text(resources.wiring_examples) || "resources/wiring_examples";
  const classificationRoot = text(resources.classification_examples) || "resources/classification_examples";
  return [
    { title: "Stage 1 页面分类", promptKey: "classification_prompt", root: classificationRoot, section: "cases" },
    { title: "Stage 2 当前页扫描", promptKey: "page_scan_prompt", root: wiringRoot, section: "stage2_cases" },
    { title: "Stage 3 跨页补全", promptKey: "cross_page_prompt", root: wiringRoot, section: "stage3_cases" },
  ].map(stage => {
    const manifest = parsed(files.get(`${stage.root}/manifest.json`));
    const list = manifest[stage.section];
    const cases = Array.isArray(list) ? list : [];
    const examples = cases.map((value: unknown, index) => {
      const item = record(value);
      const id = text(item.id) || `case-${index + 1}`;
      const expectedPath = text(item.expected) || `${id}/expected.json`;
      return {
        id, title: text(item.title) || id, description: text(item.description) || text(item.note),
        images: (Array.isArray(item.images) ? item.images : []).map((image: unknown) => {
          const entry = record(image);
          const path = `${stage.root}/${text(entry.path)}`;
          return { path, url: images.get(path), role: text(entry.role), note: text(entry.note) };
        }),
        expected: files.get(`${stage.root}/${expectedPath}`),
        input: text(item.input) ? files.get(`${stage.root}/${text(item.input)}`) : undefined,
      };
    });
    return { title: stage.title, prompt: files.get(text(resources[stage.promptKey]) || `resources/${stage.promptKey}.md`) ?? "本资源包未提供对应阶段规则", description: text(manifest.description), readme: files.get(`${stage.root}/README.md`) ?? "", examples };
  });
}
