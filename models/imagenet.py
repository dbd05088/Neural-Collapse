import os
import sys
# main.py의 상위 디렉토리 경로를 계산합니다.
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)

# 상위 디렉토리를 sys.path에 추가합니다.
sys.path.append(parent_dir)

import torch
import torch.nn as nn
from models.layers import ConvBlock, InitialBlock, FinalBlock


class BasicBlock(nn.Module):
    expansion = 1

    def __init__(
        self, opt, inplanes, planes, stride=1, downsample=None, groups=1, base_width=64
    ):
        super(BasicBlock, self).__init__()
        # Save the pre-relu feature map for the attention module
        self.return_prerelu = False
        self.prerelu = None
        
        if base_width != 64:
            raise ValueError("BasicBlock only supports groups=1 and base_width=64")

        # Both self.conv1 and self.downsample layers downsample the input when stride != 1
        self.conv1block = ConvBlock(
            opt=opt,
            in_channels=inplanes,
            out_channels=planes,
            kernel_size=3,
            stride=stride,
            padding=1,
        )
        self.conv2block = ConvBlock(
            opt=opt, in_channels=planes, out_channels=planes, kernel_size=3, padding=1
        )
        self.downsample = downsample
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        identity = x
        out = self.conv1block(x)
        out = self.conv2block(out)
        if self.downsample is not None:
            identity = self.downsample(x)
        out = out + identity
        if self.return_prerelu:
            self.prerelu = out
        out = self.relu(out)
        return out


class Bottleneck(nn.Module):
    # Bottleneck in torchvision places the stride for downsampling at 3x3 convolution(self.conv2)
    # while original implementation places the stride at the first 1x1 convolution(self.conv1)
    # according to "Deep residual learning for image recognition"https://arxiv.org/abs/1512.03385.
    # This variant is also known as ResNet V1.5 and improves accuracy according to
    # https://ngc.nvidia.com/catalog/model-scripts/nvidia:resnet_50_v1_5_for_pytorch.

    expansion = 4

    def __init__(
        self, opt, inplanes, planes, stride=1, downsample=None, groups=1, base_width=64
    ):
        super(Bottleneck, self).__init__()
        # Save the pre-relu feature map for the attention module
        self.return_prerelu = False
        self.prerelu = None
        
        width = int(planes * (base_width / 64.0)) * groups
        # Both self.conv2 and self.downsample layers downsample the input when stride != 1
        self.conv1block = ConvBlock(
            opt=opt, in_channels=inplanes, out_channels=width, kernel_size=1
        )
        self.conv2block = ConvBlock(
            opt=opt,
            in_channels=width,
            out_channels=width,
            kernel_size=3,
            stride=stride,
            groups=groups,
            padding=1,
        )
        self.conv3block = ConvBlock(
            opt=opt,
            in_channels=width,
            out_channels=planes * self.expansion,
            kernel_size=1,
        )
        self.relu = nn.ReLU(inplace=True)
        self.downsample = downsample
        self.stride = stride

    def forward(self, x):
        identity = x

        out = self.conv1block(x)
        out = self.conv2block(out)
        out = self.conv3block(out)

        if self.downsample is not None:
            identity = self.downsample(x)

        out = out + identity
        if self.return_prerelu:
            self.prerelu = out
        out = self.relu(out)
        return out


class ResidualBlock(nn.Module):
    def __init__(self, opt, block, inChannels, outChannels, depth, stride=1):
        super(ResidualBlock, self).__init__()
        if stride != 1 or inChannels != outChannels * block.expansion:
            downsample = ConvBlock(
                opt=opt,
                in_channels=inChannels,
                out_channels=outChannels * block.expansion,
                kernel_size=1,
                stride=stride,
                padding=0,
                bias=False,
            )
        else:
            downsample = None
        self.blocks = nn.Sequential()
        self.blocks.add_module(
            "block0", block(opt, inChannels, outChannels, stride, downsample)
        )
        inChannels = outChannels * block.expansion
        
        self.inplanes = outChannels * block.expansion
        
        for i in range(1, depth):
            self.blocks.add_module(
                "block{}".format(i), block(opt, inChannels, outChannels)
            )

    def forward(self, x, features=None, get_features=False, detached=False):
        return self.blocks([x, features, get_features, detached])[:2]


class ResNetBase(nn.Module):
    def __init__(
        self, opt, block, layers, zero_init_residual=False, groups=1, width_per_group=64
    ):
        super(ResNetBase, self).__init__()
        self.inplanes = 64
        self.opt = opt
        self.groups = groups
        self.base_width = width_per_group
        self.initial = InitialBlock(
            opt, self.inplanes, kernel_size=7, stride=2, padding=3, bias=False
        )
        '''
        self.inplanes = planes * block.expansion
        for _ in range(1, blocks):
            layers.append(
                block(
                    opt=opt,
                    inplanes=self.inplanes,
                    planes=planes,
                    groups=self.groups,
                    base_width=self.base_width,
                )
            )

        '''
        self.maxpool = nn.MaxPool2d(kernel_size=3,  stride=2, padding=1)
        self.group1 = ResidualBlock(opt, block, self.inplanes, 64 * block.expansion, layers[0])
        self.group2 = ResidualBlock(opt, block, self.inplanes, 128 * block.expansion, layers[1])
        self.group3 = ResidualBlock(opt, block, self.inplanes, 256 * block.expansion, layers[2])
        self.group4 = ResidualBlock(opt, block, self.inplanes, 512 * block.expansion, layers[3])
        '''
        self.group1 = ResidualBlock(
            opt, block, 64, 64, num_blocks[0], stride=1
        )  # For ResNet-S, convert this to 20,20
        self.group2 = ResidualBlock(
            opt, block, 64 * block.expansion, 128, num_blocks[1], stride=2
        )  # For ResNet-S, convert this to 20,40
        self.group3 = ResidualBlock(
            opt, block, 128 * block.expansion, 256, num_blocks[2], stride=2
        )  # For ResNet-S, convert this to 40,80
        self.group4 = ResidualBlock(
            opt, block, 256 * block.expansion, 512, num_blocks[3], stride=2
        )  # For ResNet-S, convert this to 80,160
        '''
        
        '''
        self.group1 = self._make_layer(
            opt=opt, block=block, planes=64, blocks=layers[0]
        )
        self.group2 = self._make_layer(
            opt=opt, block=block, planes=128, blocks=layers[1], stride=2
        )
        self.group3 = self._make_layer(
            opt=opt, block=block, planes=256, blocks=layers[2], stride=2
        )
        self.group4 = self._make_layer(
            opt=opt, block=block, planes=512, blocks=layers[3], stride=2
        )
        '''
        self.avgpool = nn.AdaptiveAvgPool2d((1, 1))
        self.dim_out = in_channels = 512 * block.expansion
        self.fc = FinalBlock(opt=opt, in_channels=512 * block.expansion)

        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, mode="fan_out", nonlinearity="relu")
            elif isinstance(m, (nn.BatchNorm2d, nn.GroupNorm)):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)

        # Zero-initialize the last BN in each residual branch,
        # so that the residual branch starts with zeros, and each residual block behaves like an identity.
        # This improves the model by 0.2~0.3% according to https://arxiv.org/abs/1706.02677
        if zero_init_residual:
            for m in self.modules():
                if isinstance(m, Bottleneck):
                    nn.init.constant_(m.bn3.weight, 0)
                elif isinstance(m, BasicBlock):
                    nn.init.constant_(m.bn2.weight, 0)

    def _make_layer(self, opt, block, planes, blocks, stride=1):
        downsample = None
        if stride != 1 or self.inplanes != planes * block.expansion:
            downsample = ConvBlock(
                opt=opt,
                in_channels=self.inplanes,
                out_channels=planes * block.expansion,
                kernel_size=1,
                stride=stride,
            )

        layers = []
        layers.append(
            block(
                opt=opt,
                inplanes=self.inplanes,
                planes=planes,
                stride=stride,
                downsample=downsample,
                groups=self.groups,
                base_width=self.base_width,
            )
        )
        self.inplanes = planes * block.expansion
        for _ in range(1, blocks):
            layers.append(
                block(
                    opt=opt,
                    inplanes=self.inplanes,
                    planes=planes,
                    groups=self.groups,
                    base_width=self.base_width,
                )
            )

        return nn.Sequential(*layers)

    def _forward_impl(self, x, get_feature, get_features):
        # See note [TorchScript super()]
        x = self.initial(x)
        x = self.maxpool(x)

        out1 = self.group1(x)
        out2 = self.group2(out1)
        out3 = self.group3(out2)
        out4 = self.group4(out3)

        out5 = self.avgpool(out4)
        feature = torch.flatten(out5, 1)
        out = self.fc(feature)
        if get_feature:
            return out, feature
        elif get_features:
            features = [out1, out2, out3, out4, out5]
            return out, features
        else:
            return out

    def forward(self, x, get_feature=False, get_features=False):
        return self._forward_impl(x, get_feature=get_feature, get_features=get_features)


def ResNet(opt):
    if opt.depth == 18:
        model = ResNetBase(opt, BasicBlock, [2, 2, 2, 2])
    elif opt.depth == 34:
        model = ResNetBase(opt, BasicBlock, [3, 4, 6, 3])
    elif opt.depth == 50 and opt.model == "ResNet":
        model = ResNetBase(opt, Bottleneck, [3, 4, 6, 3])
    elif opt.depth == 101 and opt.model == "ResNet":
        model = ResNetBase(opt, Bottleneck, [3, 4, 23, 3])
    elif opt.depth == 152:
        model = ResNetBase(opt, Bottleneck, [3, 8, 36, 3])
    elif opt.depth == 50 and opt.model == "ResNext":
        # Assumes a ResNeXt-50 32x4d model
        model = ResNetBase(opt, Bottleneck, [3, 4, 6, 3], groups=32, width_per_group=4)
    elif opt.depth == 101 and opt.model == "ResNext":
        # Assumes a ResNeXt-101 32x8d model
        model = ResNetBase(opt, Bottleneck, [3, 4, 23, 3], groups=32, width_per_group=8)
    elif opt.depth == 50 and opt.model == "WideResNet":
        model = ResNetBase(opt, Bottleneck, [3, 4, 6, 3], width_per_group=128)
    elif opt.depth == 101 and opt.model == "WideResNet":
        model = ResNetBase(opt, Bottleneck, [3, 4, 23, 3], width_per_group=128)
    else:
        assert opt.depth in ["18", "34", "50", "101", "152"] and opt.model in [
            "ResNet",
            "ResNext",
            "WideResNet",
        ]
    return model
