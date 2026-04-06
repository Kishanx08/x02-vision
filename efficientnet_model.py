"""
EfficientNet-B4 Image Classifier for x02 Vision Guard v2
Trained on: Hentai, NSFW Real, SFW Anime, SFW Real

Model: EfficientNet-B4 (PyTorch)
Input: 380×380 RGB images
Output: 4 classes with confidence scores
"""

import torch
import torch.nn as nn
from torchvision import models
import numpy as np
from PIL import Image
from torchvision import transforms
from typing import List


class X02VisionGuardV2(nn.Module):
    """
    EfficientNet-B4 based image classifier for x02.me content moderation
    
    Classes:
    0: hentai (explicit anime)
    1: nsfw_real (real explicit)
    2: sfw_anime (safe anime)
    3: sfw_real (safe real images)
    """
    
    def __init__(self, num_classes=4, pretrained=True):
        super(X02VisionGuardV2, self).__init__()
        
        self.num_classes = num_classes
        
        # Load pre-trained EfficientNet-B4
        self.model = models.efficientnet_b4(weights='DEFAULT' if pretrained else None)
        
        # Freeze backbone layers initially
        for param in self.model.features.parameters():
            param.requires_grad = False
        
        # Replace classifier head
        num_features = self.model.classifier[1].in_features
        self.model.classifier = nn.Sequential(
            nn.Dropout(0.3),
            nn.Linear(num_features, 512),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(512, 256),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(256, num_classes)
        )
        
        # Class names
        self.class_names = ['hentai', 'nsfw_real', 'sfw_anime', 'sfw_real']
        
        # Input size for EfficientNet-B4
        self.input_size = 380
        self.transform = transforms.Compose([
            transforms.Resize((self.input_size, self.input_size)),
            transforms.CenterCrop(self.input_size),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])
        self._active_device = None
    
    def forward(self, x):
        """
        Forward pass
        
        Args:
            x: Input tensor (batch_size, 3, 380, 380)
            
        Returns:
            Logits for 4 classes
        """
        return self.model(x)
    
    def _ensure_ready(self, device='cpu'):
        """Keep model in eval mode on the target device without repeated transfers."""
        self.eval()
        if self._active_device != device:
            self.to(device)
            self._active_device = device

    def _load_image(self, image_path_or_pil):
        """Load a PIL image from a path or normalize an existing PIL image."""
        if isinstance(image_path_or_pil, str):
            return Image.open(image_path_or_pil).convert('RGB')
        return image_path_or_pil.convert('RGB')

    def _build_prediction(self, probs):
        """Convert a probability vector into the public response schema."""
        probs = np.asarray(probs)

        hentai_score = float(probs[0] * 100)
        nsfw_real_score = float(probs[1] * 100)
        sfw_anime_score = float(probs[2] * 100)
        sfw_real_score = float(probs[3] * 100)
        nsfw_score = hentai_score + nsfw_real_score

        if nsfw_score < 40:
            recommendation = "allow"
        elif nsfw_score < 80:
            recommendation = "soft_flag"
        else:
            recommendation = "hard_block"

        return {
            "model": "x02_vision_v2_efficientnet_b4",
            "confidence": float(np.max(probs) * 100),
            "nsfw_score": min(nsfw_score, 100.0),
            "classes": {
                "hentai": hentai_score,
                "nsfw_real": nsfw_real_score,
                "sfw_anime": sfw_anime_score,
                "sfw_real": sfw_real_score
            },
            "primary_class": self.class_names[int(np.argmax(probs))],
            "thresholds": {
                "soft_flag": 40,
                "hard_block": 80
            },
            "recommendation": recommendation
        }

    def predict_batch(self, images: List, device='cpu'):
        """Predict on a batch of images for faster GIF/video inference."""
        self._ensure_ready(device)

        pil_images = [self._load_image(image) for image in images]
        batch_tensor = torch.stack([self.transform(image) for image in pil_images]).to(device)

        with torch.no_grad():
            logits = self.forward(batch_tensor)
            probabilities = torch.softmax(logits, dim=1)

        probs_batch = probabilities.cpu().numpy()
        return [self._build_prediction(probs) for probs in probs_batch]

    def predict(self, image_path_or_pil, device='cpu'):
        """
        Predict on single image
        
        Args:
            image_path_or_pil: Path to image or PIL Image
            device: 'cpu' or 'cuda'
            
        Returns:
            Dictionary with scores and recommendation
        """
        return self.predict_batch([image_path_or_pil], device=device)[0]
    
    def unfreeze_backbone(self):
        """Unfreeze backbone for fine-tuning (after initial training)"""
        for param in self.model.features.parameters():
            param.requires_grad = True
    
    def freeze_backbone(self):
        """Freeze backbone layers"""
        for param in self.model.features.parameters():
            param.requires_grad = False
    
    def save_model(self, path):
        """Save model weights"""
        torch.save(self.state_dict(), path)
        print(f"Model saved to {path}")
    
    def load_model(self, path, device='cpu'):
        """Load model weights"""
        self.load_state_dict(torch.load(path, map_location=device))
        self.to(device)
        print(f"Model loaded from {path}")


def get_model(num_classes=4, pretrained=True, device='cpu'):
    """
    Get EfficientNet-B4 model
    
    Args:
        num_classes: Number of output classes (default 4)
        pretrained: Use pretrained weights (default True)
        device: Device to load model on (default 'cpu')
        
    Returns:
        Model on specified device
    """
    model = X02VisionGuardV2(num_classes=num_classes, pretrained=pretrained)
    model.to(device)
    return model
