import os
import asyncio
import google.generativeai as genai

# 全局模型实例（避免重复初始化）
_model = None

async def load_api_key():
    """异步加载API密钥"""
    try:
        with open('api_key.txt', 'r') as f:
            return f.read().strip()
    except Exception as e:
        raise Exception(f"无法读取API密钥: {str(e)}")

async def init_gemini():
    """异步初始化模型（单例模式）"""
    global _model
    if not _model:
        api_key = await load_api_key()
        genai.configure(api_key=api_key)
        _model = genai.GenerativeModel('gemini-2.0-flash-exp')
    return _model

async def summarize_text(text):
    """异步文本摘要"""
    try:
        model = await init_gemini()
        prompt = f"请总结以下内容：\n{text}"
        
        # 将同步API调用转移到线程池执行
        response = await asyncio.to_thread(
            model.generate_content,
            prompt
        )
        
        return response.text.strip()
    except Exception as e:
        raise Exception(f"摘要生成失败: {str(e)}")