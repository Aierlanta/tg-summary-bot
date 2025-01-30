import os
import time
import google.generativeai as genai
from google.api_core import exceptions

MAX_RETRIES = 3
RETRY_DELAY = 2

def init_gemini(api_key):
    """初始化Gemini配置"""
    if not api_key:
        raise ValueError("API密钥不能为空")
    genai.configure(api_key=api_key)

def summarize_text(text, retries=MAX_RETRIES):
    """使用Gemini生成摘要"""
    model = genai.GenerativeModel('gemini-pro')
    prompt = """请为以下聊天记录生成结构化摘要，按时间顺序整理重要信息。格式要求：
    - 使用Markdown格式
    - 包含关键决策、重要事件和待办事项
    - 为每个条目添加对应的消息链接（格式：[时间] 内容 [查看消息](链接)）
    
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
            if response._result.candidates[0].finish_reason == 3:  # SAFETY
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