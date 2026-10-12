# 真实模型工作台联调

用户已授权使用现有 Agent 8100、真实模型及一次性账号/项目验收。不停止已有 Worker 或独立审校进程，不修改 Schema、Agent 核心或原 test0 项目。

## 已验证

- 真实 Auth/DB/Storage/API/浏览器增改删、权限、版本冲突、幂等及事务失败回滚已通过，前一批 CRUD 临时数据已清理。
- 真实账号浏览器读取 Bucket 三阶段 Prompt、样例图片/描述/expected，图纸库索引及资源刷新已通过。截图位于忽略目录 `.runtime/real-browser/`。
- 真实浏览器上传现有 5 页 `test0.pdf`，完成首页类型检测（zh）及正常用户确认，通过现有 Worker 执行三阶段并落库。
- 本次提取为 `SUCCEEDED`、error=null；数据库有 5 张图纸和 13 条连接。Render、Stage 1、Stage 2、跨页任务、Stage 3、Validation 完成事件齐全；Stage 1 事件标记 tree_published=true。
- 提取从创建到终态约 226 秒；费用未取得。本次证明链路与持久化，不代表逐字段准确率验收。
- 续跑脚本新增 `--resume-project`：只允许 `live-web-…@example.invalid` 验收账号的已有成功提取项目，动态查询完成的提取 run，使用原用户身份恢复浏览器订阅并进入纠错，不重复上传/提取。密码只在内存中重新生成；自建 API/Web 即使清理异常也会退出。
- 本轮重新执行 24 项默认 Server API 测试、Python lint 与 JavaScript 语法检查通过；续跑路径尚未真实执行。

## 未完成及续跑

原浏览器验收进程已退出，无提取完成/纠错截图，不能声明浏览器整体验收通过。接下来需验证：已有结果刷新与阶段卡片、手工注错、Supervisor 纠错 proposal、确认前不提交、用户确认后稳定 ID 更新、归因展示。

续跑所需 Docker 配置读取被当前沙箱拒绝；提权命令未执行，自动审批服务因自身模型令牌权限返回 HTTP 403，无法完成审批。这不是操作安全性否决。未绕过审批，未新建模型任务。

一次性项目及账号仍保留，供续跑：项目 `633ecd53-f4a7-50f9-be33-cc78cd4f7916`，成功提取 run `0d049b10-10b7-4e53-a55f-9a963453c107`。原 test0 项目 `3d66b325-bfe1-5227-9d95-0f22260fd0b0` 未改。续跑命令见 Server README；终态后脚本使用 Server 删除策略清理本次临时数据，存在活跃 run 时保留并报告。
