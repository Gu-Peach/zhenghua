该阶段用于验证主agent接收到pdf之后调用profile_detection获取类型的链路

链路需要包括以下步骤：

1. 主agent接收到pdf之后主agent的思考
2. 输出调用了profile_detection agent
3. profile_detection agent返回类型
4. 主agent输出获取到了xxx类型给用户确认，如果没获取到，向用户询问
5. 验证类型是否正确

执行方式见 [README.md](./README.md)，脚本为 `run_acceptance.py`。本组只验收类型识别与用户确认，不启动三阶段提取；“主 Agent 的思考”按可见的简短计划和调度事件检查。
