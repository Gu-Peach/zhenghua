# 项目全量XLSX导出

新增`GET /api/v1/projects/{project_id}/export.xlsx`，API2.9.0。路由负责JWT/UUID、二进制响应及UTF-8下载头，ProjectExport应用服务负责读取/版本校验与生成。CORS暴露Content-Disposition供独立前端取得中文文件名。

固定当前项目批次，按来源PDF物理页、row_order、ID稳定排序，分页读取全部正式业务行及所需字段；不接受搜索/工作区/任意数据库字段参数，不导出未确认重扫候选。完成前对比完整行ID/record_version清单、项目更新状态/索引/批次，并再次检查所有权。项目处理态、版本/范围变化、权限失效均不返回不完整文件。空结果只输出13列表头。

电压等级读取evidence.voltage_level，与terminal_strip独立；页码使用来源业务页。标准库ElementTree和ZIP在线程中编译所需OOXML，所有单元格为文本，前导零、加减号/等号保持且不执行公式。缺失值为空、0保留；非法XML字符/超Excel文本长度报422，不静默截断。黄色表头、冻结首行、筛选、按内容估算行高/列宽、换行和边框适合核对。内存响应private/no-store，不写数据库/Storage。

11项新增导出API用例，连同管理/Explain/重扫API共37项通过，Ruff与2源码mypy通过。合成XLSX经openpyxl只读校验字段/样式和artifact-tool导入作布局检查；artifact预览可能自动解释数字字符串，文本标记以原OOXML和独立reader逐字核验，未据此修改数据。未连接实际业务库或导出真实数据。

OpenAPI与Web生成Client已同步；重载8000即可加载导出，Explain新增权限DTO还需8100同步加载。无数据库迁移/新依赖/Worker变化，见[ADR-0035](../../../adr/0035-project-xlsx-export.md)。
