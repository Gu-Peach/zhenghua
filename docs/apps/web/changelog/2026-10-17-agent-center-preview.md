# 智能体中心与图纸校验工作台

2026-10-17。依据：[ADR-0027](../../../adr/0027-agent-center-and-preview-workbench.md)。本轮只修改前端和文档，不改后端/数据库/提取规则，不启停用户8000/8100。

## 智能体中心

用户菜单新增“智能体中心”，保护路由/agents和/agents/:agentId展示Extraction、Explain、Profile三张卡片。状态读取既有capabilities，只表示能力已接入/待接入，不代表运行时健康。接口没有Agent独立版本时显示“未提供独立版本”，不推测值。

同日后续按用户明确指定，三Agent展示版本统一设置为`1.0.0`，替换上述缺失版本提示并同步页面说明。该值为前端维护的展示版本；Skill继续读取各规则包的实际版本，后端运行元数据不变。追加4项智能体中心离线浏览器冒烟（含桌面/窄屏截图、Skill原版本、失败/鉴权）、TypeScript、lint和生产构建均通过。

提取Agent详情复用原规则引用登记、删除与资源查看；统一展示为zh_extraction等Skill名称，仍使用真实规则ID/key/版本。可查看分类、初扫、内部跨页补全Prompt及图像样例。名称迁移仅影响界面，不将现有Profile偷偷转换成新的运行时Skill格式。Explain详情说明工作台来源解释入口，Profile界面尚未接入时如实显示。

## 校验工作台

项目导航只保留“线表工作区/图纸预览”，旧规则库迁入智能体中心。默认线表充满中间区域，移除线号显示列及下方图纸区域；分页、编辑、项目导航、上传/提取和Explain浮窗保留。

图纸预览模式保持同一线表数据和分页，仅显示页码、原理号、起点端子、终点端子、电流。右侧上原页，下方按跨页终点跳转显示目标页；同页连接在原页显示两端。窄屏改为上下布局，表格内部允许水平滚动。

选中端子时依据独立端点{x,y,pdf_page_number}标出起点/终点，图像和标记处于同一缩放容器。无效、缺失、所属页不匹配时不猜位置并显示说明。源图/目标图分开处理失败，目标失败保留原图。查询身份包含所选连接、版本、端点及目标页，旧请求取消/隔离；切换范围或分页清除旧标记。保留图片过期刷新与缩放。

新增apis/agents.ts及drawing-evidence.ts负责界面DTO/坐标校验，useConnectionPreview隔离异步读取，组件不直接写请求URL。旧DrawingDirectory文件保留为兼容组件，不再作为项目导航入口。

## 验证

新增12项浏览器场景，连同21项管理、11项Explain，共44项离线回归通过。覆盖五列/全量切换、同页/跨页、归一化坐标与缩放、缺失/非法/错页坐标、404、旧响应隔离、卡片/Skill资源/元数据缺口、能力接口失败、鉴权及窄屏。

TypeScript、ESLint、production build及diff检查通过。截图检查含full-table-desktop、cross-page-markers-desktop、agent-center-desktop、preview-narrow、agent-center-narrow以及既有登录/项目截图，保存在被忽略的.runtime/simple-management-browser；全量分页按钮与浮动入口的最后一次检查在.runtime/final-preview-check。

没有调用真实数据库/Storage/模型或修改数据。实际Agent运行健康、独立版本和Profile Agent交互仍未由现有接口提供；真实工程图人工校验未代跑。开发前端刷新可见，后端无需重启。
