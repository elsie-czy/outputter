"""
可插拔的图片生成接口
支持多种图片生成服务（即梦、LiblibAI、SiliconFlow 等）
"""
import os
from abc import ABC, abstractmethod


class ImageGeneratorBase(ABC):
    """图片生成基类"""
    
    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> dict:
        """
        生成图片
        
        Args:
            prompt: 图片描述
            **kwargs: 其他参数（尺寸、风格等）
            
        Returns:
            {
                "ok": bool,
                "url": str,  # 图片 URL
                "error": str,  # 错误信息
            }
        """
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """检查服务是否可用"""
        pass


class JimengGenerator(ImageGeneratorBase):
    """即梦/LiblibAI/SiliconFlow 图片生成"""

    def __init__(self):
        from scripts.image_generator import generate_images_from_prompt, is_image_generation_enabled
        self._generate = generate_images_from_prompt
        self._enabled = is_image_generation_enabled()

    def generate(self, prompt: str, **kwargs) -> dict:
        if not self._enabled:
            return {"ok": False, "url": None, "error": "图片生成未启用"}

        try:
            result = self._generate(prompt, **kwargs)
            if result and len(result) > 0:
                return {"ok": True, "url": result[0], "error": None}
            return {"ok": False, "url": None, "error": "生成失败"}
        except Exception as e:
            return {"ok": False, "url": None, "error": str(e)}

    def is_available(self) -> bool:
        return self._enabled


class MockGenerator(ImageGeneratorBase):
    """Mock 图片生成（用于测试或降级）"""
    
    def generate(self, prompt: str, **kwargs) -> dict:
        return {
            "ok": True,
            "url": "https://placeholder.com/768x1024?text=Mock",
            "error": None,
        }
    
    def is_available(self) -> bool:
        return True


def get_image_generator() -> ImageGeneratorBase:
    """
    获取图片生成器（工厂函数）
    根据环境变量选择实现
    """
    provider = os.getenv("IMAGE_PROVIDER", "jimeng").strip().lower()

    if provider in ("jimeng", "siliconflow", "liblib"):
        return JimengGenerator()
    elif provider == "mock":
        return MockGenerator()
    else:
        valid = "jimeng, siliconflow, liblib, mock"
        raise RuntimeError(
            f"未知的 IMAGE_PROVIDER: {provider}，有效值: {valid}。"
            f"请检查 .env 文件中的 IMAGE_PROVIDER 配置。"
        )


def generate_images_for_task(deconstruct_result: dict) -> dict:
    """
    为任务生成图片
    
    Args:
        deconstruct_result: 拆文结果
        
    Returns:
        {
            "ok": bool,
            "images": {"cover": url, "scene1": url, ...},
            "error": str,
        }
    """
    generator = get_image_generator()
    
    if not generator.is_available():
        return {"ok": False, "images": {}, "error": "图片生成服务不可用"}
    
    # 从拆文结果中提取配图提示词
    prompts = deconstruct_result.get("配图提示词", [])
    if not prompts:
        # 兼容飞书缓存格式：生成配图提示词1~5
        for i in range(1, 6):
            p = deconstruct_result.get(f"生成配图提示词{i}", "")
            if p and str(p).strip():
                prompts.append(str(p).strip())
    if not prompts:
        storyboard = deconstruct_result.get("visual_storyboard") or deconstruct_result.get("视觉分镜") or []
        if isinstance(storyboard, list):
            for frame in storyboard[:5]:
                if not isinstance(frame, dict):
                    continue
                p = (
                    frame.get("英文画面提示词")
                    or frame.get("english_prompt")
                    or frame.get("prompt")
                    or frame.get("画面主体")
                )
                if p and str(p).strip():
                    prompts.append(str(p).strip())
    if not prompts:
        return {"ok": False, "images": {}, "error": "无配图提示词"}
    
    images = {}
    errors = []
    
    # 生成封面图（第一张）
    if len(prompts) > 0:
        result = generator.generate(prompts[0])
        if result["ok"]:
            images["cover"] = result["url"]
        else:
            errors.append(f"封面图生成失败: {result['error']}")
    
    # 生成其他配图（最多4张）
    for i, prompt in enumerate(prompts[1:5], 1):
        result = generator.generate(prompt)
        if result["ok"]:
            images[f"scene{i}"] = result["url"]
        else:
            errors.append(f"配图{i}生成失败: {result['error']}")
    
    return {
        "ok": len(images) > 0,
        "images": images,
        "error": "; ".join(errors) if errors else None,
    }
