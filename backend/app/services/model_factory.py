from torch import nn
from torchvision import models


SUPPORTED_BACKBONES = {
    "efficientnet_b0": "EfficientNet-B0（轻量，训练快）",
    "resnet50": "ResNet50（稳定，平衡）",
    "inception_v3": "InceptionV3（精度潜力高，训练更慢）",
}


def list_available_backbones():
    """列出所有支持的骨干网络"""
    return [
        {"key": key, "name": name}
        for key, name in SUPPORTED_BACKBONES.items()
    ]


def build_model(backbone: str, num_classes: int, pretrained: bool = True):
    """构建分类模型（迁移学习）

    使用 ImageNet 预训练权重初始化骨干网络，
    替换最后的全连接层为适配当前分类任务的新层。
    InceptionV3 训练时图像尺寸最低要求 299×299。
    """
    if backbone == "efficientnet_b0":
        weights = models.EfficientNet_B0_Weights.DEFAULT if pretrained else None
        try:
            model = models.efficientnet_b0(weights=weights)
        except Exception:
            model = models.efficientnet_b0(weights=None)
        in_features = model.classifier[1].in_features
        model.classifier[1] = nn.Linear(in_features, num_classes)
        return model

    if backbone == "resnet50":
        weights = models.ResNet50_Weights.DEFAULT if pretrained else None
        try:
            model = models.resnet50(weights=weights)
        except Exception:
            model = models.resnet50(weights=None)
        in_features = model.fc.in_features
        model.fc = nn.Linear(in_features, num_classes)
        return model

    if backbone == "inception_v3":
        weights = models.Inception_V3_Weights.DEFAULT if pretrained else None
        try:
            model = models.inception_v3(weights=weights, aux_logits=False)
        except Exception:
            model = models.inception_v3(weights=None, aux_logits=False)
        in_features = model.fc.in_features
        model.fc = nn.Linear(in_features, num_classes)
        return model

    raise ValueError(f"不支持的模型: {backbone}")


def freeze_backbone_layers(model, backbone: str):
    """冻结骨干网络，仅训练分类头（适用于小样本微调场景）"""
    for param in model.parameters():
        param.requires_grad = False

    if backbone == "efficientnet_b0":
        head = model.classifier
    elif backbone == "resnet50":
        head = model.fc
    elif backbone == "inception_v3":
        head = model.fc
    else:
        return

    for param in head.parameters():
        param.requires_grad = True


def find_last_conv_layer(model):
    """遍历模型找到最后一个卷积层，供 Grad-CAM 提取特征图和梯度"""
    target_layer = None
    for module in model.modules():
        if isinstance(module, nn.Conv2d):
            target_layer = module
    if target_layer is None:
        raise RuntimeError("未找到可用于Grad-CAM的卷积层")
    return target_layer
