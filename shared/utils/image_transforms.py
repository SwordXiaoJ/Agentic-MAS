# Copyright AGNTCY Contributors
# SPDX-License-Identifier: Apache-2.0

import io
import base64
from typing import List, Tuple
from PIL import Image, ImageFilter, ImageEnhance
import numpy as np


class ImageTransformer:
    """Utility for applying augmentations to images"""

    @staticmethod
    def rotate(image: Image.Image, degrees: float) -> Image.Image:
        """Rotate image by degrees"""
        return image.rotate(degrees, expand=True, fillcolor=(0, 0, 0))

    @staticmethod
    def gaussian_blur(image: Image.Image, sigma: float = 1.0) -> Image.Image:
        """Apply Gaussian blur"""
        return image.filter(ImageFilter.GaussianBlur(radius=sigma))

    @staticmethod
    def adjust_brightness(image: Image.Image, factor: float) -> Image.Image:
        """Adjust brightness (factor > 1 = brighter, < 1 = darker)"""
        enhancer = ImageEnhance.Brightness(image)
        return enhancer.enhance(factor)

    @staticmethod
    def center_crop_and_resize(image: Image.Image, crop_ratio: float = 0.9) -> Image.Image:
        """Center crop to crop_ratio and resize back to original size"""
        original_size = image.size
        width, height = original_size

        new_width = int(width * crop_ratio)
        new_height = int(height * crop_ratio)

        left = (width - new_width) // 2
        top = (height - new_height) // 2
        right = left + new_width
        bottom = top + new_height

        cropped = image.crop((left, top, right, bottom))
        return cropped.resize(original_size, Image.Resampling.LANCZOS)

    @staticmethod
    def image_to_base64(image: Image.Image, format: str = "JPEG") -> str:
        """Convert PIL Image to base64 string"""
        buffer = io.BytesIO()
        image.save(buffer, format=format)
        return base64.b64encode(buffer.getvalue()).decode()

    @staticmethod
    def base64_to_image(b64_string: str) -> Image.Image:
        """Convert base64 string to PIL Image"""
        image_bytes = base64.b64decode(b64_string)
        return Image.open(io.BytesIO(image_bytes))

    @classmethod
    def apply_transform(cls, image: Image.Image, transform_name: str) -> Image.Image:
        """Apply named transform to image"""
        transforms = {
            "rotate_15": lambda img: cls.rotate(img, 15),
            "rotate_neg15": lambda img: cls.rotate(img, -15),
            "blur_sigma1": lambda img: cls.gaussian_blur(img, 1.0),
            "brightness_1.1": lambda img: cls.adjust_brightness(img, 1.1),
            "brightness_0.9": lambda img: cls.adjust_brightness(img, 0.9),
            "center_crop_90": lambda img: cls.center_crop_and_resize(img, 0.9),
        }

        if transform_name not in transforms:
            raise ValueError(f"Unknown transform: {transform_name}")

        return transforms[transform_name](image)

    @classmethod
    def get_standard_augmentations(cls) -> List[str]:
        """Get list of standard augmentation names"""
        return ["rotate_15", "blur_sigma1", "brightness_1.1"]


async def apply_transforms_to_url(image_url: str, transform_names: List[str]) -> List[Tuple[str, str]]:
    """
    Apply transforms to an image URL and return base64 encoded results.
    Returns list of (base64_image, transform_name) tuples.
    """
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(image_url) as response:
            image_bytes = await response.read()
            image = Image.open(io.BytesIO(image_bytes))

    results = []
    transformer = ImageTransformer()

    for transform_name in transform_names:
        transformed = transformer.apply_transform(image, transform_name)
        b64 = transformer.image_to_base64(transformed)
        results.append((b64, transform_name))

    return results
