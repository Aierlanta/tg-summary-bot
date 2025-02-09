import os
import logging
import json
import schedule
import time
import threading
from datetime import datetime

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    Application
)

from gemini_api import summarize_text, init_gemini

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)



def load_config(config_file="config.json"):
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"{config_file} 文件不存在。")
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)

config = load_config()

WHITE_LIST = config.get("white_list", [])
GROUPS_FILE = "groups.json"
RETRY_LIMIT = 3
API_KEY = ""

def load_groups():
    if os.path.exists(GROUPS_FILE):
        try:
            with open(GROUPS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载群组列表失败: {e}")
            return {}
    return {}

def save_groups(groups):
    try:
        with open(GROUPS_FILE, "w", encoding="utf-8") as f:
            json.dump(groups, f, ensure_ascii=False, indent=4)
        logger.info("群组列表已保存")
    except Exception as e:
        logger.error(f"保存群组列表失败: {e}")

GROUP_LIST = load_groups()

def clean_txt_files():
    """定时清理临时文件"""
    directory = "./logs"
    if not os.path.exists(directory):
        os.makedirs(directory)
    for filename in os.listdir(directory):
        if filename.endswith(".txt"):
            try:
                os.remove(os.path.join(directory, filename))
                logger.info(f"删除文件: {filename}")
            except Exception as e:
                logger.error(f"删除文件失败: {e}")

def run_schedule():
    """调度任务线程"""
    schedule.every().day.at("04:00").do(clean_txt_files)
    while True:
        schedule.run_pending()
        time.sleep(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    await update.message.reply_text("Bot已启动")

async def setapikey(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global API_KEY
    user = update.effective_user.username
    
    if user not in WHITE_LIST:
        await update.message.reply_text("❌ 你不在白名单中")
        return
        
    if not context.args:
        await update.message.reply_text("⚠️ 请在命令后输入API KEY")
        return
        
    try:
        # 更新全局变量
        API_KEY = context.args[0]
        
        # 持久化保存
        with open('api_key.txt', 'w') as f:
            f.write(API_KEY)
            
        # 初始化 Gemini（无需传参）
        init_gemini()  # 修改后不再需要参数
        await update.message.reply_text("✅ API KEY 设置成功")
        logger.info(f"用户 {user} 更新了API KEY")
        
    except Exception as e:
        await update.message.reply_text(f"❌ 设置失败: {str(e)}")
        logger.error(f"API KEY 设置错误: {e}")

async def addgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /addgroup 命令"""
    user = update.message.from_user.username
    if user not in WHITE_LIST:
        await update.message.reply_text("你不在白名单中，无法使用此功能")
        return
        
    if context.args:
        group_name = " ".join(context.args)
        GROUP_LIST[group_name] = True
        save_groups(GROUP_LIST)
        await update.message.reply_text(f"已添加群组: {group_name}")
        logger.info(f"用户 {user} 添加了群组 {group_name}")
    else:
        await update.message.reply_text("请在命令后输入群组名称")

async def switchgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /switchgroup 命令"""
    user = update.message.from_user.username
    if user not in WHITE_LIST:
        await update.message.reply_text("你不在白名单中，无法使用此功能")
        return
        
    if context.args:
        group_name = " ".join(context.args)
        if group_name in GROUP_LIST:
            context.user_data['current_group'] = group_name
            await update.message.reply_text(f"已切换到群组: {group_name}")
            logger.info(f"用户 {user} 切换到群组 {group_name}")
        else:
            await update.message.reply_text("群组不存在，请先添加该群组")
    else:
        await update.message.reply_text("请在命令后输入群组名称")

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /summary 命令"""
    user = update.message.from_user.username
    if user not in WHITE_LIST:
        await update.message.reply_text("你不在白名单中，无法使用此功能")
        return

    current_group = context.user_data.get('current_group')
    if not current_group:
        await update.message.reply_text("请先使用 /switchgroup <群组名> 切换群组")
        return

    try:
        msg_count = int(context.args[0]) if context.args else 10
    except ValueError:
        msg_count = 10

    directory = "./logs"
    os.makedirs(directory, exist_ok=True)
    file_name = f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    file_path = os.path.join(directory, file_name)

    try:
        with open(os.path.join(directory, "messages.log"), "r", encoding="utf-8") as lf:
            lines = lf.readlines()
            # 更精确的群组匹配逻辑
            group_lines = [
                ln for ln in lines 
                if f"[{current_group}] " in ln  # 添加空格避免部分匹配
            ]
            logger.info(f"当前筛选群组: {current_group}")
            logger.info(f"匹配到的日志行示例: {group_lines[:3]}")  # 打印前3条匹配记录
            selected_lines = group_lines[-msg_count:]
            
            if not selected_lines:
                await update.message.reply_text("未找到相关消息记录")
                return
                
        # 保存原始记录并生成带链接的版本
        with open(file_path, "w", encoding="utf-8") as f:
            # 提取关键信息并格式化
            formatted_lines = []
            for line in selected_lines:
                try:
                    parts = line.split("] ")
                    timestamp = parts[0][1:]
                    chat = parts[1][1:]
                    user = parts[2][5:]
                    link = parts[3][6:]
                    content = "] ".join(parts[4:]).strip()
                    formatted_lines.append(
                        f"{timestamp} {user}：{content}（[查看消息]({link})）\n"
                    )
                except Exception as e:
                    logger.warning(f"解析日志行失败: {line} - {str(e)}")
            
            if not formatted_lines:
                await update.message.reply_text("有效消息内容为空")
                return
                
            f.writelines(formatted_lines)
    except Exception as e:
        logger.error(f"处理日志文件失败: {e}")
        await update.message.reply_text("读取消息记录失败")
        return

    await update.message.reply_text("正在生成摘要，请稍候...")
    retries = 0
    while retries < RETRY_LIMIT:
        try:
            # 读取临时文件内容
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            if not content:
                await update.message.reply_text("无可用内容进行摘要")
                return
                
            summary_result = summarize_text(content)

            # 分割消息
            max_message_length = 4000  # Telegram 消息长度限制
            if len(summary_result) > max_message_length:
                parts = [summary_result[i:i + max_message_length] for i in range(0, len(summary_result), max_message_length)]
                for part in parts:
                    await update.message.reply_text(f"摘要生成完成:\n\n{part}")
            else:
                await update.message.reply_text(f"摘要生成完成:\n\n{summary_result}")

            try:
                os.remove(file_path)
                logger.info(f"清理临时文件: {file_path}")
            except Exception as e:
                logger.error(f"删除临时文件失败: {e}")
            return
        except Exception as e:
            retries += 1
            logger.error(f"摘要生成失败 (尝试 {retries}/{RETRY_LIMIT}): {e}")
            if "Message is too long" in str(e):
                await update.message.reply_text("摘要内容过长，请减少消息数量后重试")
                return
            time.sleep(2)
    
    await update.message.reply_text("生成摘要失败，请稍后重试")
    logger.error(f"摘要生成失败，临时文件保留于: {file_path}")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理普通消息"""
    if not update.message or not update.effective_chat:
        logger.warning("收到无效消息类型")
        return

    user = update.effective_user.username if update.effective_user else "未知用户"
    text = update.message.text
    chat = update.effective_chat
    timestamp = update.message.date.strftime('%Y-%m-%d %H:%M:%S')
    
    # 生成消息链接
    message_id = update.message.message_id
    chat_id = str(abs(chat.id))
    # 如果chat_id以"100"开头，去掉这个前缀
    if chat_id.startswith('100'):
        chat_id = chat_id[3:]
    link = f"https://t.me/c/{chat_id}/{message_id}"
    
    directory = "./logs"
    os.makedirs(directory, exist_ok=True)
    file_path = os.path.join(directory, "messages.log")
    
    try:
        log_entry = (
            f"[{timestamp}] "
            f"[{chat.id}] "
            f"[UID:{user}] "
            f"[LINK:{link}] "
            f"{text}\n"
        )
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
        logger.debug(f"已记录消息: {chat.id}")
    except Exception as e:
        logger.error(f"写入消息文件失败: {e}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /help 命令"""
    text = (
        "/start - 启动 Bot\n"
        "/setapikey <key> - 设置 API Key\n"
        "/addgroup <name> - 添加群组\n"
        "/switchgroup <name> - 切换群组\n"
        "/summary <count> - 生成摘要\n"
        "/help - 显示帮助信息"
    )
    await update.message.reply_text(text)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """全局错误处理"""
    logger.error(f"处理更新时发生异常: {context.error}", exc_info=True)
    
    if update.effective_message:
        await update.effective_message.reply_text(
            "处理请求时发生错误，请联系管理员"
        )

def main():
    """主函数"""
    bot_token = config.get("bot_token")
    if not bot_token:
        logger.error("未配置 bot_token")
        return

    # 创建应用
    application = Application.builder().token(bot_token).build()
    application.add_error_handler(error_handler)  # 添加这行

    # 注册命令处理器
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setapikey", setapikey))
    application.add_handler(CommandHandler("addgroup", addgroup))
    application.add_handler(CommandHandler("switchgroup", switchgroup))
    application.add_handler(CommandHandler("summary", summary))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # 启动调度任务线程
    schedule_thread = threading.Thread(target=run_schedule, daemon=True)
    schedule_thread.start()

    # 启动 Bot
    logger.info("Bot开始轮询...")
    application.run_polling()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("收到停止信号，Bot已关闭")
    except Exception as e:
        logger.error(f"运行时错误: {e}")