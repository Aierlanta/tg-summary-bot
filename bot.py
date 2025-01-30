import os
import logging
import schedule
import time
from datetime import datetime
import threading
import asyncio  # 引入 asyncio 库
import json  # 引入 json 库

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from gemini_api import summarize_text  # 引入Gemini API模块

# 配置日志输出等级，便于调试和记录
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(level别)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

# 用户白名单，只有这里的用户名才具备使用Bot的权限
WHITE_LIST = ["user1", "user2"]

# 存储群组信息的文件路径
GROUPS_FILE = "groups.json"

# 加载群组列表
def load_groups():
    if os.path.exists(GROUPS_FILE):
        try:
            with open(GROUPS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载群组列表失败: {e}")
            return {}
    return {}

# 保存群组列表
def save_groups(groups):
    try:
        with open(GROUPS_FILE, "w", encoding="utf-8") as f:
            json.dump(groups, f, ensure_ascii=False, indent=4)
        logger.info("群组列表已保存")
    except Exception as e:
        logger.error(f"保存群组列表失败: {e}")

# 初始化群组列表
GROUP_LIST = load_groups()

# 固定使用gemini基础模型
API_BASE = "gemini"
API_KEY = ""  # 用户可通过 /setapikey <KEY> 设置
RETRY_LIMIT = 3  # 最多允许对同一次总结操作重试的次数

def clean_txt_files():
    """
    定时任务：清理 ./logs 目录下的txt文件，
    防止日志和临时摘要文件无限增长。
    """
    directory = "./logs"
    if not os.path.exists(directory):
        os.makedirs(directory)
    for filename in os.listdir(directory):
        if filename.endswith(".txt"):
            os.remove(os.path.join(directory, filename))
            logger.info(f"删除文件: {filename}")

def job_scheduler():
    """
    使用 schedule 库进行轮询任务，每天凌晨4点清理txt文件。
    """
    schedule.every().day.at("04:00").do(clean_txt_files)
    while True:
        schedule.run_pending()
        time.sleep(1)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start 指令：简单提示Bot已启动。
    """
    await update.message.reply_text("Bot已启动")

async def set_apikey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /setapikey <你的key>：设置API Key，用于调用Gemini模型。
    """
    global API_KEY
    if context.args:
        API_KEY = context.args[0]
        # 将API_KEY写入文件
        try:
            with open('api_key.txt', 'w') as f:
                f.write(API_KEY)
            await update.message.reply_text("已设置API KEY")
            logger.info("API KEY已更新")
        except Exception as e:
            logger.error(f"写入API KEY失败: {e}")
            await update.message.reply_text("设置API KEY时发生错误，请稍后再试。")
    else:
        await update.message.reply_text("请在命令后输入你的API KEY")

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /summary <条数> 指令：
    1. 检查用户白名单。
    2. 读取指定条数的消息，存储到本地txt文件。
    3. 调用Gemini API生成摘要，失败可重试。
    4. 成功后删除txt文件；失败超过RETRY_LIMIT则停止。
    """
    user = update.message.from_user.username
    if user not in WHITE_LIST:
        await update.message.reply_text("你不在白名单中，无法使用此功能")
        logger.warning(f"非白名单用户尝试使用summary功能: {user}")
        return

    # 获取用户当前群组
    current_group = context.user_data.get('current_group')
    if not current_group:
        await update.message.reply_text("请先使用 /switchgroup <群组名> 切换群组。")
        logger.warning(f"用户 {user} 未设置当前群组")
        return

    # 获取用户指定的消息条数，默认10
    try:
        msg_count = int(context.args[0]) if context.args else 10
    except ValueError:
        msg_count = 10

    directory = "./logs"
    if not os.path.exists(directory):
        os.makedirs(directory)

    # 创建txt文件并记录实际消息
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    file_name = f"summary_{timestamp}.txt"
    file_path = os.path.join(directory, file_name)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            # 读取最新的消息条数
            # 假设日志文件是按时间顺序记录的
            with open(os.path.join(directory, "messages.log"), "r", encoding="utf-8") as log_file:
                lines = log_file.readlines()
                # 过滤当前群组的消息
                group_lines = [line for line in lines if f"[{current_group}]" in line]
                selected_lines = group_lines[-msg_count:]
                for line in selected_lines:
                    f.write(line)
        logger.info(f"实际消息已记录到文件: {file_path}")
    except Exception as e:
        logger.error(f"写入日志文件失败: {e}")
        await update.message.reply_text("无法记录消息，请稍后再试。")
        return

    # 读取文件内容
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"读取日志文件失败: {e}")
        await update.message.reply_text("无法读取消息内容，请稍后再试。")
        return

    # 调用Gemini API进行摘要
    retries = 0
    success = False
    summary_result = ""

    while retries < RETRY_LIMIT and not success:
        try:
            summary_result = summarize_text(content)
            success = True
            logger.info("调用Gemini API成功")
        except Exception as ex:
            retries += 1
            logger.error(f"总结失败: {ex}, 重试 {retries}/{RETRY_LIMIT}")
            await asyncio.sleep(2)  # 异步等待2秒后重试

    if success:
        await update.message.reply_text(f"总结成功:\n{summary_result}")
        # 删除txt文件
        try:
            os.remove(file_path)
            logger.info(f"删除文件: {file_path}")
        except Exception as e:
            logger.error(f"删除文件失败: {e}")
    else:
        await update.message.reply_text("总结多次失败，终止操作并记录错误")
        logger.error(f"总结异常，文件保留以供调查: {file_path}")

async def addgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /addgroup <group_name>：将指定群组添加到内部群组列表。
    """
    user = update.message.from_user.username
    if user not in WHITE_LIST:
        await update.message.reply_text("你不在白名单中，无法使用此功能")
        logger.warning(f"非白名单用户尝试使用addgroup功能: {user}")
        return

    if context.args:
        group_name = " ".join(context.args)
        GROUP_LIST[group_name] = True
        save_groups(GROUP_LIST)
        await update.message.reply_text(f"已添加群组: {group_name}")
        logger.info(f"群组已添加: {group_name}")
    else:
        await update.message.reply_text("请在命令后输入要添加的群组名称或ID")
        logger.warning("addgroup命令缺少群组名称或ID")

async def switchgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /switchgroup <group_name>：切换当前操作的群组。
    """
    user = update.message.from_user.username
    if user not in WHITE_LIST:
        await update.message.reply_text("你不在白名单中，无法使用此功能")
        logger.warning(f"非白名单用户尝试使用switchgroup功能: {user}")
        return

    if context.args:
        group_name = " ".join(context.args)
        if group_name in GROUP_LIST:
            # 保存用户当前群组设置
            user_data = context.user_data
            user_data['current_group'] = group_name
            await update.message.reply_text(f"已切换到群组: {group_name}")
            logger.info(f"用户 {user} 切换到群组: {group_name}")
        else:
            await update.message.reply_text("群组不存在，请先添加该群组。")
            logger.warning(f"用户 {user} 尝试切换到不存在的群组: {group_name}")
    else:
        await update.message.reply_text("请在命令后输入要切换的群组名称或ID")
        logger.warning("switchgroup命令缺少群组名称或ID")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /help 指令：列出所有可用的命令。
    """
    help_text = (
        "/start - 启动 Bot\n"
        "/setapikey <key> - 设置 Gemini API Key\n"
        "/addgroup <group_name> - 添加群组\n"
        "/switchgroup <group_name> - 切换当前群组\n"
        "/summary <消息条数> - 生成消息摘要\n"
        "/help - 显示帮助信息"
    )
    await update.message.reply_text(help_text)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    捕获所有非命令消息并记录到日志文件。
    """
    user = update.message.from_user.username
    text = update.message.text
    timestamp = update.message.date.strftime('%Y-%m-%d %H:%M:%S')
    group = update.effective_chat.title  # 获取群组名称
    log_entry = f"[{timestamp}] [{group}] [{user}] {text}\n"
    directory = "./logs"
    if not os.path.exists(directory):
        os.makedirs(directory)
    file_path = os.path.join(directory, "messages.log")
    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
        logger.info(f"记录消息到文件: {file_path}")
    except Exception as e:
        logger.error(f"写入消息文件失败: {e}")

def main():
    """
    初始化并启动Bot，注册命令处理器和消息处理器。
    """
    bot_token = "YOUR_TELEGRAM_BOT_TOKEN"  # 替换为实际Token
    application = ApplicationBuilder().token(bot_token).build()

    # 注册命令处理器
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("setapikey", set_apikey_command))
    application.add_handler(CommandHandler("addgroup", addgroup_command))
    application.add_handler(CommandHandler("switchgroup", switchgroup_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("help", help_command))  # 注册 /help 命令

    # 注册消息处理器，用于捕获并记录实际消息
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))

    # 设置 Bot 的命令列表
    application.bot.set_my_commands([
        ('start', '启动 Bot'),
        ('setapikey', '设置 Gemini API Key'),
        ('addgroup', '添加群组'),
        ('switchgroup', '切换当前群组'),
        ('summary', '生成消息摘要'),
        ('help', '显示帮助信息'),
    ])

    # 创建调度线程，每天清理txt文件
    schedule_thread = threading.Thread(target=job_scheduler, daemon=True)
    schedule_thread.start()

    # 启动Bot
    logger.info("Bot开始轮询...")
    application.run_polling()

def run_bot_forever():
    """
    异常退出后自动重启Bot，确保可持续运行。
    """
    while True:
        try:
            main()
        except Exception as e:
            logger.error(f"Bot异常退出: {e}，5秒后重试...")
            time.sleep(5)

if __name__ == "__main__":
    run_bot_forever()