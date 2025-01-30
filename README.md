# TG Summary Bot

## 简介
TG Summary Bot 是一个用于总结Telegram群组聊天记录的自动化工具。它利用Google Gemini API生成结构化摘要，帮助用户快速了解群组中的重要信息、关键决策和待办事项。

## 安装依赖
确保你已经安装了Python 3.7或更高版本。然后，安装所需的Python库：

```bash
pip install -r requirements.txt
```

## 配置
1. **设置API密钥**：
   - 创建一个 `api_key.txt` 文件，并将你的Google Gemini API密钥粘贴进去。
   - 或者，通过Bot命令 `/setapikey <你的API_KEY>` 设置API密钥。

2. **配置Bot**：
   - 编辑 `config.json` 文件，添加你的Telegram Bot Token：
     ```json
     {
       "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
       "white_list": ["your_username"]
     }
     ```

## 使用方法
1. **启动Bot**：
   ```bash
   python bot.py
   ```
   启动后，Bot会开始监听Telegram群组中的消息，并定时清理日志文件。

2. **Bot命令**：
   - `/start` - 启动Bot。
   - `/setapikey <key>` - 设置Google Gemini API Key。
   - `/addgroup <id>` - 添加群组。
   - `/switchgroup <id>` - 切换当前操作的群组。
   - `/summary <count>` - 生成最近<code>count</code>条消息的摘要。
   - `/help` - 显示帮助信息。

## 功能说明

### gemini_api.py
- **初始化Gemini API**：读取并设置API密钥，配置Gemini生成模型。
- **生成摘要**：接收文本输入，通过Gemini生成结构化摘要，包含关键决策、重要事件和待办事项。

### bot.py
- **消息处理**：记录Telegram群组中的消息，并生成带有链接的日志。
- **命令处理**：处理用户发送的Bot命令，如设置API密钥、添加/切换群组、生成摘要等。
- **定时任务**：每日定时清理临时日志文件，保持系统整洁。

## 日志与调试
日志文件存储在 `./logs` 目录下，包括所有记录的消息和操作日志。可以通过查看日志文件来调试和监控Bot的运行状态。

## 贡献与许可
欢迎任何形式的贡献！请提交Pull Request或创建Issue讨论。项目采用MIT许可证，详情请参阅 `LICENSE` 文件。
