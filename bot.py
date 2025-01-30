import os
import logging
import asyncio
import json
import schedule
import time
from datetime import datetime

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from gemini_api import summarize_text, init_gemini  # 导入Gemini API相关函数

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

async def clean_txt_files_async():
    directory = "./logs"
    os.makedirs(directory, exist_ok=True)
    for filename in os.listdir(directory):
        if filename.endswith(".txt"):
            try:
                os.remove(os.path.join(directory, filename))
                logger.info(f"删除文件: {filename}")
            except Exception as e:
                logger.error(f"删除文件失败: {e}")
    await asyncio.sleep(0)

async def job_scheduler_async():
    schedule.every().day.at("04:00").do(lambda: asyncio.create_task(clean_txt_files_async()))
    while True:
        schedule.run_pending()
        await asyncio.sleep(1)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot已启动")

async def setapikey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username
    if user not in WHITE_LIST:
        await update.message.reply_text("你不在白名单中，无法使用此功能")
        return
        
    if context.args:
        API_KEY = context.args[0]
        try:
            with open('api_key.txt', 'w', encoding='utf-8') as f:
                f.write(API_KEY)
            # 验证API是否可用
            try:
                init_gemini()
                await update.message.reply_text("API KEY已设置并验证成功")
                logger.info(f"用户 {user} 设置了新的API KEY")
            except Exception as e:
                logger.error(f"API KEY验证失败: {e}")
                await update.message.reply_text(f"API KEY设置失败: {str(e)}")
        except Exception as e:
            logger.error(f"写入API KEY失败: {e}")
            await update.message.reply_text("保存API KEY时发生错误")
    else:
        await update.message.reply_text("请在命令后输入API KEY")

async def addgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username
    if user not in WHITE_LIST:
        await update.message.reply_text("你不在白名单中，无法使用此功能")
        return
    if context.args:
        group_name = " ".join(context.args)
        GROUP_LIST[group_name] = True
        save_groups(GROUP_LIST)
        await update.message.reply_text(f"已添加群组: {group_name}")
    else:
        await update.message.reply_text("缺少群组名称参数")

async def switchgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username
    if user not in WHITE_LIST:
        await update.message.reply_text("你不在白名单中，无法使用此功能")
        return
    if context.args:
        group_name = " ".join(context.args)
        if group_name in GROUP_LIST:
            context.user_data['current_group'] = group_name
            await update.message.reply_text(f"已切换到群组: {group_name}")
        else:
            await update.message.reply_text("群组不存在，请先添加该群组")
    else:
        await update.message.reply_text("缺少群组名称参数")

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
            group_lines = [ln for ln in lines if f"[{current_group}]" in ln]
            selected_lines = group_lines[-msg_count:]
            if not selected_lines:
                await update.message.reply_text("未找到相关消息记录")
                return
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(selected_lines)
    except Exception as e:
        logger.error(f"处理日志文件失败: {e}")
        await update.message.reply_text("读取消息记录失败")
        return

    retries = 0
    success = False
    summary_result = ""
    
    # 读取文件内容
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        logger.error(f"读取临时文件失败: {e}")
        await update.message.reply_text("处理消息内容失败")
        return

    # 调用Gemini API进行摘要
    await update.message.reply_text("正在生成摘要，请稍候...")
    while retries < RETRY_LIMIT and not success:
        try:
            summary_result = summarize_text(content)
            success = True
            logger.info(f"成功为群组 {current_group} 生成摘要")
        except Exception as e:
            retries += 1
            logger.error(f"摘要生成失败 (尝试 {retries}/{RETRY_LIMIT}): {e}")
            if retries < RETRY_LIMIT:
                await asyncio.sleep(2)
            else:
                await update.message.reply_text(f"生成摘要失败: {str(e)}")
                return

    if success:
        await update.message.reply_text(f"摘要生成完成:\n\n{summary_result}")
        try:
            os.remove(file_path)
            logger.info(f"清理临时文件: {file_path}")
        except Exception as e:
            logger.error(f"删除临时文件失败: {e}")
    else:
        await update.message.reply_text("生成摘要失败，请稍后重试")
        logger.error(f"摘要生成失败，临时文件保留于: {file_path}")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "/start - 启动 Bot\n"
        "/setapikey <key> - 设置 Gemini API Key\n"
        "/addgroup <group_name> - 添加群组\n"
        "/switchgroup <group_name> - 切换当前群组\n"
        "/summary <条数> - 生成消息摘要\n"
        "/help - 帮助信息"
    )
    await update.message.reply_text(text)

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.username
    text = update.message.text
    chat_title = update.effective_chat.title
    timestamp = update.message.date.strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"[{timestamp}] [{chat_title}] [{user}] {text}\n"
    directory = "./logs"
    os.makedirs(directory, exist_ok=True)
    file_path = os.path.join(directory, "messages.log")
    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(log_entry)
    except Exception as e:
        logger.error(f"写入消息文件失败: {e}")

async def set_my_commands(application):
    await application.bot.set_my_commands([
        ("start", "启动 Bot"),
        ("setapikey", "设置 Gemini API Key"),
        ("addgroup", "添加群组"),
        ("switchgroup", "切换当前群组"),
        ("summary", "生成消息摘要"),
        ("help", "帮助信息"),
    ])

async def main_async():
    bot_token = config.get("bot_token")
    if not bot_token:
        logger.error("未配置 bot_token")
        return
    application = ApplicationBuilder().token(bot_token).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("setapikey", setapikey_command))
    application.add_handler(CommandHandler("addgroup", addgroup_command))
    application.add_handler(CommandHandler("switchgroup", switchgroup_command))
    application.add_handler(CommandHandler("summary", summary_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    await set_my_commands(application)
    asyncio.create_task(job_scheduler_async())
    logger.info("Bot开始轮询...")
    try:
        await application.run_polling()
    except Exception as e:
        logger.error(f"Bot运行时出现异常: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        logger.info("Bot已停止")
    except Exception as e:
        logger.error(f"Unhandled exception: {e}")