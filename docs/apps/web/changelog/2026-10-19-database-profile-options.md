# 上传规则与提取Skills统一读取数据库包

上传PDF对话框与提取智能体Skills都读取/api/v1/rule-library，只展示已上传Storage资源包；保留客户端过滤以兼容尚未重载的旧API，local://不进入选项。移除本地登记按钮和无用组件；空列表提示先在规则配置智能体发布规则。

查看规则继续按数据库ID请求资源预览，读取已上传ZIP中的真实Prompt/样例；不回退本地文件。已有自定义上传包保留，原项目数据与规则绑定不变。展示版本为ZH2.3.0、ABB1.3.1和XMZ0.2.1；后两者仅上传版本号增加，识别资源不变。

前端类型/lint/build及隔离HTTP浏览器验证通过：三条上传包与一条local混合响应只显示三条，未请求/local、未发送业务写请求。Skills/资源预览/上传选择的桌面与窄屏、空/加载/失败/权限和登录共11截图位于.runtime/profile-catalog-upload/ui。未调用模型或上传真实PDF。

重载8000 API并刷新页面完成切换，后端校验和实际发布见[Server交付](../../../service/server/changelog/2026-10-19-database-profile-catalog.md)。
