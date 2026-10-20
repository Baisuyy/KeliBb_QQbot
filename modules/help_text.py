def get_help(is_group: bool) -> str:
    if is_group:
        return "🐱 可丽堡堡喵！\n## 可用命令\n- `/status` 查看服务器状态\n- `/models` 查询/切换AI模型（仅管理员）\n- `/help` 显示本帮助\n- `/clear` 清空对话记忆\n- `/myid` 获取你的 openid\n- `/name [名称]` 设置/查看你的名称\n- `/testalert` 测试告警通道\n- `/restart` 重启机器人（仅管理员）\n- `/exec <命令>` 以非root用户执行命令（仅管理员）\n- `/wp 标题 | 内容` 发布文章到 WordPress（仅管理员）\n- `/diary` 生成今日对话日记（仅管理员）\n\n💬 直接发文字（不带 `/`）即可和我聊天～"
    else:
        return "🐱 可丽堡堡喵！\n可用命令：\n* /status 查看服务器状态\n* /models 查询/切换AI模型（仅管理员）\n* /help 显示本帮助\n* /clear 清空对话记忆\n* /myid 获取你的 openid\n* /name [名称] 设置/查看你的名称\n* /testalert 测试告警通道\n* /restart 重启机器人（仅管理员）\n* /exec <命令> 以非root用户执行命令（仅管理员）\n* /wp 标题 | 内容 发布文章到 WordPress（仅管理员）\n* /diary 生成今日对话日记（仅管理员）\n\n直接发文字（不带 /）即可和我聊天～"
