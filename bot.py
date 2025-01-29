import os
import logging
import schedule
import time
from datetime import datetime
import threading
import requests

from telegram import Update
from telegram.ext import (
    Updater,
    CommandHandler,
    CallbackContext,
)

from gemini_api import summarize_text  # 引入Gemini API模块

logging.basicConfig(level=logging.INFO)

# 用户白名单
WHITE_LIST = ["user1", "user2"]

# 群组列表
GROUP_LIST = {}

# 仅支持 gemini 基础
API_BASE = "gemini"
API_KEY = ""  # 用户可通过 /setapikey <KEY> 设置
RETRY_LIMIT = 3

def clean_txt_files():
    """
    定时任务：清理 ./logs 目录下的txt文件，防止日志和临时摘要文件无限增长。
    """
    directory = "./logs"
    if not os.path.exists(directory):
        os.makedirs(directory)
    for filename in os.listdir(directory):
        if filename.endswith(".txt"):
            os.remove(os.path.join(directory, filename))

def job_scheduler():
    """
    使用 schedule 库进行轮询任务，每天凌晨4点清理txt文件。
    """
    schedule.every().day.at("04:00").do(clean_txt_files)
    while True:
        schedule.run_pending()
        time.sleep(1)

def start_command(update: Update, context: CallbackContext):
    """
    /start 指令：简单提示Bot已启动。
    """
    update.message.reply_text("Bot已启动")

def set_apikey_command(update: Update, context: CallbackContext):
    """
    /setapikey <你的key>：设置API Key，用于调用Gemini模型。
    """
    global API_KEY
    if context.args:
        API_KEY = context.args[0]
        # 将API_KEY写入文件
        with open('api_key.txt', 'w') as f:
            f.write(API_KEY)
        update.message.reply_text("已设置API KEY")
    else:
        update.message.reply_text("请在命令后输入你的API KEY")

def summary_command(update: Update, context: CallbackContext):
    """
    /summary <条数> 指令：
    1. 检查用户白名单。
    2. 读取指定条数的消息，存储到本地txt文件。
    3. 调用Gemini API生成摘要，失败可重试。
    4. 成功后删除txt文件；失败超过RETRY_LIMIT则停止。
    """
    user = update.message.from_user.username
    if user not in WHITE_LIST:
        update.message.reply_text("你不在白名单中，无法使用此功能")
        return

    # 获取用户指定的消息条数，默认10
    try:
        msg_count = int(context.args[0]) if context.args else 10
    except ValueError:
        msg_count = 10

    directory = "./logs"
    if not os.path.exists(directory):
        os.makedirs(directory)

    # 创建txt文件并记录模拟消息
    file_path = os.path.join(
        directory,
        f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    )
    with open(file_path, "w", encoding="utf-8") as f:
        for i in range(msg_count):
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{user}] [message_{i}]\n")

    # 读取文件内容
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 调用Gemini API进行摘要
    retries = 0
    success = False
    summary_result = ""

    while retries < RETRY_LIMIT and not success:
        try:
            summary_result = summarize_text(content)
            success = True
        except Exception as ex:
            retries += 1
            logging.error(f"总结失败: {ex}, 重试 {retries}/{RETRY_LIMIT}")

    if success:
        update.message.reply_text(f"总结成功:\n{summary_result}")
        if os.path.exists(file_path):
            os.remove(file_path)
    else:
        update.message.reply_text("总结多次失败，终止操作并记录错误")
        logging.error(f"总结异常，文件保留以供调查: {file_path}")

def addgroup_command(update: Update, context: CallbackContext):
    """
    /addgroup <group_name>：将指定群组添加到内部群组列表。
    """
    if context.args:
        group_name = " ".join(context.args)
        GROUP_LIST[group_name] = True
        update.message.reply_text(f"已添加群组: {group_name}")
    else:
        update.message.reply_text("请在命令后输入要添加的群组名称或ID")

def main():
    """
    初始化并启动Bot，注册命令处理器。
    """
    bot_token = "YOUR_TELEGRAM_BOT_TOKEN"  # 替换为实际Token
    updater = Updater(bot_token, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start_command))
    dp.add_handler(CommandHandler("setapikey", set_apikey_command))
    dp.add_handler(CommandHandler("summary", summary_command))
    dp.add_handler(CommandHandler("addgroup", addgroup_command))

    # 创建调度线程，每天清理txt文件
    schedule_thread = threading.Thread(target=job_scheduler, daemon=True)
    schedule_thread.start()

    # 启动Bot轮询
    updater.start_polling()
    updater.idle()

def run_bot_forever():
    """
    异常退出后自动重启Bot，确保可持续运行。
    """
    while True:
        try:
            main()
        except Exception as e:
            logging.error(f"Bot异常退出: {e}，5秒后重试...")
            time.sleep(5)

if __name__ == "__main__":
    run_bot_forever()