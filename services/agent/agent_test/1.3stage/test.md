该阶段测试主agent接收到pdf，调用profile_detection和三阶段agent提取数据存放到supabase的链路

链路包括：

1. 主agent接收到pdf之后主agent的思考
2. 输出调用了profile_detection agent
3. profile_detection agent返回类型
4. 主agent输出获取到了xxx类型给用户确认，如果没获取到，向用户询问
5. 验证类型是否正确
6. 主agent调用三阶段agent提取数据
7. 每一阶段的agent在执行是主agent给出反馈xxx正在执行
8. 三阶段agent每一个阶段都会将对应的返回数据存放至数据库中
9. 主agent告诉用户已处理完毕
