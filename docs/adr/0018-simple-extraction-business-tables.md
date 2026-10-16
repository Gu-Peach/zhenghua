# ADR-0018：三张精简提取业务表（待接入）

状态：Accepted（用户2026-10-14随后授权直接删除旧业务表）。最初仅交付SQL，随后在本地数据库部署三表及旧表清理；应用适配待完成。

2026-10-14后续用户明确授权：旧业务数据无需迁移，后续重新上传，先删除截图旧业务对象并落地新表。执行目标限定为本地supabase_db_zhenghua_test，不涉及其他Docker数据库；保留6张agent_*、Auth与Storage数据。旧项目/文件被Agent外键引用，显式解除3条跨模块外键；成员访问函数改为新项目所有者判断，旧Storage项目策略替换为新项目策略。新增清理migration采用RESTRICT，不使用无边界CASCADE；应用接口适配仍未实施。

## 范围

2026-10-16更新：按用户限定范围，Server/Web数据管理已适配新三表，batch_id/record_version和项目JSON索引契约见ADR-0020；原始PDF上传只保存，不触发Agent。以下旧应用依赖说明为10月14日部署时的状态，Agent正式提取仍待接入。

核心提取业务数据拟集中为public.extraction_profiles、public.extraction_projects、public.extraction_connection_rows。使用独立表名，使用户可先创建核对；现有projects与wiring_connection_rows视图保持，不通过删除底层表腾出名称。Auth与已决定暂留的agent_*表不属于这三张业务表。

规则表只保存key/version/checksum和资源引用，Prompt/图片继续放文件或私有Storage。项目直接外键关联规则，保存所有者、源PDF路径和图纸索引JSON，不增加项目结果关联表。连接表保存可查询的线表列、来源/目标业务页及PDF物理页、批次和页内项标识、复核状态及可选证据JSON。

本方案仅支持项目所有者访问，暂不迁移多人项目成员权限。原workspaces/drawings/document_files目录和预览能力需由图纸索引JSON适配；当前前端、Server结果CRUD/RPC、Agent结果提交仍依赖旧表，未适配前不可删除旧表。既有数据迁移、手工编辑审计与历史结果选择需要单独实现；当前批次字段保存多次运行，不自动决定哪批为当前结果。

## 数据约束与权限

规则引用对已登录用户可读，仅创建者可维护；项目仅所有者可读写，连接权限经project_id跟随项目。项目外键关联规则，连接外键关联项目；规则被项目引用时拒绝删除，删除项目会级联删除其连接，但Storage对象需要应用一致性策略。唯一键为project_id+batch_id+source_pdf_page_number+page_item_id，保留同一原理号的不同分支；并发页写入需在应用事务中upsert和处理删除项，不把唯一键等同于完整恢复算法。

公共三表updated_at由触发器维护，连接record_version更新时递增。创建迁移只新增对象；后续清理迁移明确列出18张旧表和1个视图，用RESTRICT删除并在事务中校验保留数据。清理不可逆，旧业务数据不迁移；三表回滚需另写迁移，不能恢复已删除旧数据。

## 验证

已在本地supabase_db_zhenghua_test执行：三表从不存在开始创建，带旧业务数据执行两次回滚演练后原子创建/清理/登记并提交。验证所有者可读写、跨用户不可读/写、匿名不可读、record_version更新、页级幂等唯一键；测试行均回滚。保留6张Agent表及Auth用户/Storage对象的行数和内容摘要不变，提交后旧业务对象为0，新三表均为空。未运行应用端到端验证；旧前端/Server/Agent RPC依赖旧schema，不能使用，需后续适配。详见Server实际清理记录。
