# GCR101 跨项目关联 Mock

## 行为

- 在项目顶部“答案对比”旁增加“关联项目”；大车卷盘GCR101显示关联图谱，其他图纸显示空态。
- 目录增加Mock文件夹，内含“低压配电系统（Mock）”与“照明配电系统（Mock）”；支持搜索、展开工作区/模拟图纸、跳转和刷新。
- 0261映射X1:1/2/3到XD10:13/14/15；0262映射X21:1/2到XD21:7/20；0263映射X22:1/2到XD22:90/N-BAR，各组含PE，共10条。
- 关系图节点可点击，明细可按线号筛选并直接定位模拟目标页；Mock工作台可返回真实GCR101。URL保留目标图纸和关系视图，支持浏览器前进后退。
- 模拟工作台只读，没有编辑、删除、重扫、导出或伪造PDF入口。只读取真实来源项目确认当前访问权限/定位GCR101，不请求Mock项目的业务API；来源加载、失败、无权限时不展示关联事实。
- 响应式布局：桌面横向节点与连接线，窄屏纵向排列；端子明细区域横向滚动，长项目名限行并保留标题提示。

## 文件

- `apps/web/src/apis/mock/project-relations.ts`：两个模拟项目、类型化端子对和页级路径。
- `RelatedProjects.tsx`：图谱、线号筛选、端子对应表。
- `MockRelatedWorkspace.tsx`：只读模拟项目与真实来源权限/回跳。
- `ProjectView.tsx`、`ProjectTree.tsx`、`styles.css`：增量接入现有导航、目录和样式，保留工作区原有未提交改动。

## 验收

- `npm run lint` 通过。
- `npm run build`（含 `tsc -b` 类型检查）通过；Vite仍提示主包大于500kB，不影响构建。
- `node node_modules/@playwright/test/cli.js test tests/project-relations.spec.ts tests/simple-management.spec.ts tests/answer-comparison.spec.ts --workers=2`：46项通过，含6项新检查。
- 核验图谱10行映射、两个目标项目往返、目录直达/选页、刷新/后退、非GCR101空态、加载/503/403、其他项目无Mock目录、长文本/390px键盘导航及无页面横向溢出。
- 桌面/390px关联页与登录页截图已查看；截图为忽略的`.runtime/simple-management-browser/`诊断产物，不提交。
- HTTP夹具确认模拟项目不产生业务请求，关联操作不写入。未访问或修改实际数据库/Storage，未调用模型、启动任务或重启用户服务。

## 使用与限制

刷新现有Web，选择大车卷盘项目的GCR101，再打开“关联项目”。本轮没有真实跨项目关系存储，模拟项目和外部图纸页码只用于交互演示。设计见[关联演示](../project-relations-mock.md)，不将演示关系覆盖到现有提取结果。
