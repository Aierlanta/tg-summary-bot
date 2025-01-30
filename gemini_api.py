import os
import time
import google.generativeai as genai
from google.api_core import exceptions
import logging

# 初始化日志系统
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)  # 全局定义 logger

MAX_RETRIES = 3
RETRY_DELAY = 2
API_KEY = ""

def init_gemini():
    global API_KEY, logger  # 明确声明使用全局 logger
    
    try:
        # 尝试从文件读取 API KEY（如果内存中没有）
        if not API_KEY and os.path.exists("api_key.txt"):
            with open("api_key.txt", "r") as f:
                API_KEY = f.read().strip()
        
        # 最终验证
        if not API_KEY:
            logger.error("未找到有效的 API_KEY")  # 使用 logger 记录错误
            raise ValueError("未找到有效的 API_KEY")
        
        # 配置 Gemini
        import google.generativeai as genai
        genai.configure(api_key=API_KEY)
        logger.info("✅ Gemini API 初始化成功")  # 成功日志
        
    except Exception as e:
        logger.error(f"Gemini 初始化失败: {e}")  # 明确使用 logger
        raise

def summarize_text(text, retries=MAX_RETRIES):
    """使用Gemini生成摘要"""
    model = genai.GenerativeModel('gemini-2.0-flash-thinking-exp-01-21')
    prompt = """请为以下聊天记录生成结构化摘要，按时间顺序整理重要信息。格式要求：
    - 使用Markdown格式
    - 包含关键决策、重要事件和待办事项
    - 为每个条目添加对应的消息链接（格式：[时间] 内容 (链接)）
    
    聊天记录：
    {content}
    """
    
    for attempt in range(retries):
        try:
            response = model.generate_content(
                prompt.format(content=text),
                generation_config=genai.types.GenerationConfig(
                    temperature=0.3,
                    top_p=0.9
                )
            )
            
            # 检查响应安全限制
            if response._result.candidates[0].finish_reason == 0:  # stop
                raise exceptions.GoogleAPIError("内容被安全过滤器拦截")
                
            return response.text
            
        except exceptions.TooManyRequests:
            wait_time = RETRY_DELAY ** (attempt + 1)
            time.sleep(wait_time)
        except exceptions.InvalidArgument as e:
            raise ValueError(f"无效请求参数: {str(e)}") from e
        except exceptions.PermissionDenied as e:
            raise PermissionError(f"API密钥无效: {str(e)}") from e
        except Exception as e:
            if attempt == retries - 1:
                raise RuntimeError(f"生成失败，最终错误: {str(e)}") from e
            time.sleep(RETRY_DELAY)
    
    return "摘要生成失败，请检查网络连接或稍后重试"