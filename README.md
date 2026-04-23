# 异环薄荷AI —— 基于OpenCV的游戏自动化助手

![GitHub repo size](https://img.shields.io/github/repo-size/daoqi/NTE-ai)
![GitHub](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)

## 📖 项目简介

**异环薄荷AI** 是一款专为开放世界游戏 **《异环》** 开发的自动化辅助工具。核心功能包括**任务自动跳过、自动钓鱼、兑换码一键复制**等，能帮你从重复游戏中解放出来，更轻松地体验核心乐趣。

> 工具通过 **OpenCV** 对游戏画面进行图像识别与模拟操作，不涉及内存读取，用起来也更安心。

## ✨ 功能特点

- 🎯 **任务自动跳过**：通过图像识别自动点击“跳过”、“确认”、“领取”等按钮，并用 **F12** 控制启停。
- 🎣 **AI 自动钓鱼**：智能识别并跟随鱼钩（HS）与鱼漂（DDS）位置，一旦触发即自动收杆。
- 📋 **兑奖码仓库**：一键复制内置或历史兑奖码，省去反复输入的麻烦。
- 📺 **浮动日志窗口**：独立置顶的日志窗口，方便随时查看操作记录。
- 🔄 **自动更新**：支持从 GitHub 拉取新版本（需在 `config.py` 中配置仓库信息）。
- ⚔️ **自动战斗 / 🀄 AI 麻将**：功能开发中，后续版本会陆续推出。

## 🛠️ 技术栈

- **Python 3.9+**
- **PyQt5**：用于构建图形用户界面。
- **OpenCV**：实现游戏画面的图像识别。
- **PyAutoGUI / PyDirectInput**：模拟键盘与鼠标操作。
- **Ultralytics YOLOv8 (规划中)**：为后续接入 YOLO 模型进行目标检测提供基础，提升自动化泛用性。

> 📌 YOLO 模型可用于**精准识别游戏中的各类敌人、资源点、可交互对象**等，让自动化适用性更广、操作更智能。相关内容预计会在后续版本中上线。

## 💻 安装与使用

### 环境准备

确保系统已安装 **Python 3.9+** 并配置好环境变量。

### 步骤 1：下载项目

你可以从以下任一渠道下载：

#### 百度网盘
[点击下载 (提取码：6e19)](https://pan.baidu.com/s/5ThlYNUC5oMZrhF7pjeJc5Q)

#### 迅雷云盘
链接：分享文件：异环薄荷ai
链接：https://pan.xunlei.com/s/VOquI79qBd-6pXpNmJv8TpwMA1?pwd=4ek3
#### 蓝奏云
[点击下载](https://www.ilanzou.com/s/VtD6Tsip)

#### GitHub 直接克隆
```bash
git clone git@github.com:daoqi/NTE-ai.git
cd NTE-ai