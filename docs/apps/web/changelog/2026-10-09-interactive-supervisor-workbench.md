# 2026-10-09 交互式 Supervisor 工作台

## 范围

- 为 `apps/web` 增加交互式 Mock 工作流，旧 `frontend/` 和后端保持不变；
- 顶层增加项目图纸文件夹与 ZH/ABB 规则库视图；
- 仅跨页索引终点支持悬浮高亮和点击跳转到目标业务图纸；
- 右侧 AI 面板改为 Supervisor 请求入口与流式监工区，持续展示主 Agent 思考、工具返回、子 Agent 调用和最终结果，不再展示伪造问答。
- 将图纸库、规则库移动到项目顶部导航；将重新处理入口改为 PDF 上传；线表修复改为自然语言请求，并提供“模拟链路”开关触发 Mock Supervisor 调度。
- 模拟开关默认关闭；首次加载不展示预置历史事件。关闭时上传只登记项目 PDF 和排队状态，开启后从 Stage 1 开始运行。
- 思考文本以淡化逐字流式输出；当前子 Agent 名称加粗，运行中显示圆形等待标记，完成后显示勾选，再进入下一阶段。
- 项目树按处理阶段增量呈现：上传后先出现源文件；Stage 1 完成后再展开工作区和拆分页，之后依序更新 Agent 阶段状态。

## Mock 流程

- PDF 选择后模拟 Stage 1 页面分类、Stage 2 当前页扫描和 Stage 3 跨页补全事件；
- 修复元数据包含线号、答案是否提供、修复目标和问题归因；
- 有答案时直接 patch 当前 Mock 线表；无答案时按同页/跨页索引路由到 Stage 2/Stage 3；
- 规则问题生成待审核候选规则，保留固定案例回归和人工审核门禁，不发布生产 Profile。

## API 边界

- 项目、连接、运行事件、图纸库、规则库、Supervisor 事件流继续由 `src/apis` 适配；
- `VITE_USE_MOCKS=false` 的 Supervisor POST/SSE 与库查询地址仅为前端接入预留，后端端点、DTO、鉴权和持久化仍待联调。

## 验证

```text
corepack pnpm typecheck:web  PASS
corepack pnpm lint:web       PASS
corepack pnpm build:web      PASS
Playwright desktop flows     PASS
Playwright viewport checks   PASS (1680x1000, 390x844)
```

已覆盖初始空态、上传排队及“等待模拟”状态、Stage 1 前隐藏工作区、Stage 1 后显示工作区与拆分页、Agent 等待/完成图标和 Stage 1/2/3 顺序；修复链路覆盖答案直接写回、同页 Stage 2、跨页 Stage 3、大模型幻觉归因和规则候选。并覆盖跨页 hover/click、桌面/窄屏无横向溢出和浏览器控制台无错误。
