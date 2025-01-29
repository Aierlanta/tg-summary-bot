import os
import google.generativeai as genai
import json

def load_api_key():
    """
    从api_key.txt文件中加载API密钥。
    """
    try:
        with open('api_key.txt', 'r') as f:
            return f.read().strip()
    except Exception as e:
        raise Exception(f"无法读取API密钥: {str(e)}")

def init_gemini():
    """
    初始化Gemini生成模型，配置API密钥。
    """
    api_key = load_api_key()
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.0-flash-exp')

def summarize_text(text):
    """
    使用Gemini模型生成文本摘要。

    参数:
        text (str): 需要摘要的文本内容。

    返回:
        str: 生成的摘要结果。
    """
    try:
        model = init_gemini()
        prompt = f"""
        请总结以下内容：
        {text}
        """
        response = model.generate_content(prompt)
        summary = response.text.strip()
        return summary
    except Exception as e:
        raise Exception(f"调用Gemini API失败: {str(e)}")