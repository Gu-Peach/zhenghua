# Explain 回复逐字显示与Markdown

2026-10-17，用户反馈回复一次出现且Markdown标记原样显示。

## 修改

新增useTypewriterText展示缓冲及TypewriterAnswer。SSE仍即时接收，界面按帧展示约75码点/秒，积压较多时提速，最高300码点/秒；completed或缓存全文只更新目标文本，不跳过缓冲。Unicode码点避免拆开UTF-16代理对。停止时冻结已经显示的文本，重试重新建立缓冲，关闭卸载取消动画；提供“立即显示已收到内容”。prefers-reduced-motion下立即显示，本轮不会因偏好切换回退到旧前缀。

解释正文使用react-markdown与remark-gfm渲染标题、列表、粗体、行内代码/代码块及表格。不执行原始HTML，不渲染模型给出的图片，链接使用组件默认URL过滤及新窗口隔离；原页/跨页图纸继续来自已有结构化检索。依赖及pnpm锁文件同步。

逐字变化也触发原有自动跟随滚动，用户上滚时不强制回到底部。Explain浮窗改为按需加载，Markdown依赖留在独立分包：主包约398KB、Explain约164KB（压缩前），不让依赖进入初始主包。

## 验证

全部26项浏览器回归通过：Explain共11项（原有7项加新增4项）及15项管理场景。新增覆盖一次大块delta、仅completed全文、减少动态效果/安全Markdown、停止冻结/重试/emoji代理对。typecheck、ESLint与production build通过，构建无大于500KB分包提示。

桌面与390px窄屏截图已检查，包含Markdown、长文本、缺图、工具记录、登录和工作台；产物位于被忽略的.runtime/simple-management-browser。没有修改后端/Prompt/数据库契约、调用真实模型/数据库、或启动/停止用户的8000/8100服务。无需重启后端，开发前端刷新后打开新解释即可；生产环境需部署新构建。
