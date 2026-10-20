# Explain调用诊断边界

旧错误只记录分类/turn，无法回溯原始SSE error；真实项目请求未经本轮授权不能外发。用户仅批准3次无项目数据探针，已经完成；后续验证仅Fake。

Explain专用Gateway适配器为每次invoke/stream生成诊断UUID，记录文本字符数、图片数/编码体积、工具定义体积、工具轮次/历史条数、耗时、usage及finish_reason。错误仅保存稳定错误码、符号型provider_code/type和由技术关键词匹配的分类，不保存原始provider_message、请求/回答正文、工具参数、图片、URL或凭据。未知上游原因保持unknown，不猜测OOM。

诊断保存在忽略的.runtime/explain-diagnostics，复用唯一文件原子写入；落盘失败不阻断业务。错误编号加入已有安全message，公开错误码/DTO不变；终端日志仅编号和统计。普通模型调用、工具权限、重试策略及实际Profile不变。新代码加载后用户正常请求发生失败才能取得对应统计，历史失败无法还原。
