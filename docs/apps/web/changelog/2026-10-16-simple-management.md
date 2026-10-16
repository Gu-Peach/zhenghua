# 三表数据管理界面

前端apis/projects.ts改用生成的Simple*契约，batch_id替代旧结果版本，行编辑仅依据record_version。工作区/图纸由Server项目JSON索引适配，字段转换集中在apis，不在组件拼后端字段。

上传弹窗要求显式选择本地规则，保存失败保留文件/规则选择并重用幂等键。成功只进入项目详情，不再发送Supervisor消息或订阅旧Agent任务。静态AI面板说明提取待接入，输入/新任务禁用；原始PDF通过授权签名访问。

规则库改为登记/删除规则引用和预览Prompt/样例，内部补全显示为Stage2节点。线表编辑仅改单行，冲突保留草稿及幂等键；新增连接直接选择来源/目标图纸和批次，无索引时明确不可新增。工具栏文件按钮合并布局，保持项目树/中间结果/悬浮AI与窄屏排版。

10项浏览器HTTP夹具、typecheck/lint/production build通过；空、加载、失败、无权限、长文本、桌面和390px窄屏截图位于.runtime/simple-management-browser，登录和工作台已视觉核对。旧合约保留为legacy-workbench.fixture.ts，当前默认不运行已移除的Supervisor/旧表功能用例。

真实本地Server/Auth/Storage验收另见[Server交付](../../../service/server/changelog/2026-10-16-simple-management.md)。浏览器截图是显式测试夹具，不是生产回退或真实提取结果；本轮未调用模型。用户需重启8000后端以加载新API后刷新前端。
