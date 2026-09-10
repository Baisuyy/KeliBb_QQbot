# KeliBb_QQbot

基于 [QQ官方机器人 SDK (botpy)](https://bot.q.qq.com/wiki/develop/api/) 的 QQ 群聊/私聊机器人「可丽堡堡」喵～

## 功能特性

- 私聊(C2C)、群@、私信三种消息通道
- AI 对话，猫娘人格，带搜索触发能力（联网搜索）
- 多款命令（见下方命令列表）
- 上下文管理与 Token 压缩（基于 tiktoken）
- 会话持久化、跨天压缩
- 定时服务器健康巡检与告警推送
- 日记与 WordPress 发布、TTS 语音合成等

## 环境依赖

- Python 3.9+
- 依赖包见 `requirements.txt`

```bash
pip install -r requirements.txt
```

## 配置

在 `modules/config.py` 中填写：

| 配置项 | 说明 |
| --- | --- |
| `APP_ID` / `APP_SECRET` | QQ 开放平台机器人凭证 |
| `AI_API_URL` / `AI_API_KEY` / `AI_MODEL` | 大模型 API（OpenAI 兼容接口，流式） |
| `ADMIN_OPENID` | 管理员 openid（用于告警、管理员命令） |
| `EXEC_USER` | `/exec` 执行命令使用的非 root 用户 |
| `WP_*` | WordPress 发布凭据 |
| `TTS_*` | TTS 语音合成配置 |

## 运行

```bash
python bot.py
```

## 命令

| 命令 | 说明 |
| --- | --- |
| `/status` | 查看服务器状态 |
| `/help` | 显示帮助 |
| `/clear` | 清空对话记忆 |
| `/myid` | 获取你的 openid |
| `/name [名称]` | 设置/查看你的名称 |
| `/testalert` | 测试告警通道 |
| `/restart` | 重启机器人（仅管理员） |
| `/exec <命令>` | 以非 root 用户执行命令（仅管理员） |
| `/wp 标题 \| 内容` | 发布文章到 WordPress（仅管理员） |
| `/diary` | 生成今日对话日记（仅管理员） |
| `/tts <内容>` | 将文本转为语音发送（需配置 TTS） |