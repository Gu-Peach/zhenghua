# agent_test ZH端子特征与跨页区域核读

2026-10-22，按用户要求完成本地ZH2.6.0代码、提示词和案例编辑；设计见[区域核读方案](../zh-marker-verification-plan.md)。该版本尚未真实模型实测，不能沿用2.5.0运行结果作为验收。

## 最终流程

整页初扫（放线段、端点、原理号、引用分型、跨页区域框）→从原图按区域分组裁剪→同窗跨页引用批量核读→程序解析地址/唯一目标页索引→目标整页逐连接补全→确定性校验和保存。

初扫同时定位，不恢复独立source_reference_locate/read。新核读是source_marker_verify，每个来源窗口一次请求，结构错误最多沿用两次Schema尝试。初扫、目标补全仍用现有调用入口；通过可选Profile资源启用，其他Profile无此资源时保持原流程。

40%明确为整页宽、高各40%，即面积16%；对应同显示尺寸约2.5倍局部细节。框包含箭头与完整地址/信号，窗口至少40%，大框适当扩展，相邻能容纳的合并，分散者分窗；靠近页边平移。裁剪原始图像后应用现有2048长边与总像素预算，不对整页缩略图插值放大。目标图继续完整输入。

## 端点判据

观察002C03/11、003C01/02/11、004C01/04，增加terminal_features.md：X/XD/XA排号与数字接点、元件针脚、柜框真实接口、岸电插座U/V/W/N/PE、N-BAR/PE-BAR。-FC11/-XA/-S11等标签必须与实际接点绑定；框体、+位置、普通导线节点、机械联动虚线和元件关联页表分别处理，不能只见文字或圆点就停止。

002C03的X3↔XD21和002C11右侧+07-XD1用于解释最近本页端点；003C01的XA/XD10和N/PE、003C02/004C04的出页段用于说明不能穿过最近端子去借FC关联地址。它们是观察后的规则说明，新增模型示例仍仅来自原003C01。

## 代码与证据

- domain/models/extraction_stages.py：MarkerRegion、程序所有的MarkerVerification；PageScanRequest支持诊断目录与窗口边界取消检查。
- domain/models/marker_verification.py：批量ref_id/连接归属/结果种类/地址/信号/basis模型及窗口配置。
- infrastructure/document/marker_verification.py：分组、原像素裁图、窗口上下文、精确ID绑定、受限合并与诊断保存。
- infrastructure/zh_vlm_stages.py：整页初扫后按配置调用批量核读，图片预算及原有Schema重试复用；三种操作加载共享端子特征。
- application/segment_contract.py及profiles/zh/references.py：未通过核读引用不可进入路由，地址解析不再跳过异常前缀搜索后缀，避免098.M-+...被解析成当前002.C。
- profile2.6.0/manifest19：新增source_marker_verification资源；已确认起点、原理号、方向和同页终点保持冻结。

核读可改引用字面文字/信号和未知出页边界；不新增连接、不改端点。缺框/丢失或重复ID/未确认归属/非导线引用/看不清/调用失败均留下依据，禁止回退未核验初扫地址。发现本段先到同页端子时只阻断错误跨页并标复核，不借局部图补造同页end。程序核验的是模型结构与声明，仍不能保证视觉追线一定正确。

运行目录/source-marker-verification/物理页/保存初扫快照、窗口输入JSON与原图裁剪PNG、窗口结果或失败类型、核读后快照；正常模型日志含stage=source_marker_verify和source-marker:pN-window-K。references.marker_verification保存原地址与核读地址及依据。起点与终点坐标保持各自整页坐标，局部框只用于本轮地址读取。

## 案例和验证状态

保留原003C01整页15条出页与2条同页正例、4个补全任务（3目标图共享）。新增2张原始003C01局部裁剪：前两组10条、右侧5条。引用原值来自已有确认Expected，不创造新端点；新增框与核读说明由本轮编辑、待用户复核。仅制作并查看了真实图像裁剪资产，没有执行提取、回归测试、lint/类型或真实模型调用。原2.5.0结果目录保留，本轮不修改正式服务、数据库规则或业务结果。

使用命令见agent_test/extraction_agent/profiles/zh/README.md；新输出目录用zh_260，避免混用此前checkpoint。新增校验会增加模型调用数和耗时，实际效果待用户实测。
