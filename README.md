# 📦 TG-Discord-Aggregator

> **一个强大的 Telegram 消息聚合与转发工具，支持 R2 图床与多路复用。**

本项目旨在将分散在不同 Telegram 群组、频道或话题（Topics）的消息，**聚合**并转发到 Discord Webhook。它完美解决了跨平台图片存储、头像同步及相册合并问题，是管理跨平台社区消息的理想方案。

---

## ✨ 核心特性

- **🖼️ 智能图床聚合**：自动截获 Telegram 图片并转存至 Cloudflare R2，生成永久链接。彻底解决 Discord 无法直接显示 Telegram 图片（因防盗链/过期）的痛点。
- **📂 媒体组 (Album) 合并**：将 Telegram 的多图“相册”消息自动聚合为一条 Discord 消息发送，保持频道整洁，告别刷屏。
- **👤 发送者聚合**：自动抓取并缓存发送者头像，在 Discord 中完美复刻原消息发送者的身份体验。
- **⚙️ 话题 (Forum) 路由**：精准支持 Telegram Topics，可将不同话题的消息聚合到 Discord 的不同频道。
- **🛡️ 灵活过滤**：支持配置白名单或特定用户 ID 过滤，只聚合你关心的核心消息。

---

## ✅ 环境要求

* **Python**: 3.8 或更高版本
* **Telegram 账号**: 用于接收/读取消息
* **Cloudflare 账号**: 用于 R2 图片存储 (免费额度通常足够个人使用)
* **Discord Webhook URL**: 聚合消息的目标地址

---

## 🛠️ 配置指南 (如何获取 Key)

### 1. 获取 Telegram API ID & Hash
1. 访问 [my.telegram.org](https://my.telegram.org) 并输入手机号登录。
2. 点击 **"API development tools"**。
3. 填写表单（Title 和 Short name 随意填），点击 **"Create application"**。
4. 复制页面显示的 **`App api_id`** 和 **`App api_hash`**。

### 2. 获取 Cloudflare R2 配置
1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/) 进入 **R2**。
2. **创建存储桶**：点击 "Create bucket"，输入名称（如 `tg-aggregator`），创建并记下名称。
3. **开启公开访问**：
   - 进入存储桶 -> **"Settings"** -> **"Public Access"**。
   - 点击 "Allow R2.dev subdomain" (或绑定自定义域名)。
   - 复制显示的 URL（如 `https://pub-xxxx.r2.dev`），这将是配置中的 `public_url`。
4. **获取密钥**：
   - 回到 R2 主页 -> 右侧 **"Manage R2 API Tokens"** -> **"Create API token"**。
   - 权限选择 **"Object Read & Write"**。
   - 创建后复制：**Access Key ID**、**Secret Access Key** 和 **Endpoint**。
   - *注意：配置时 Endpoint 去掉开头的 `https://`。*

---

## 🚀 安装与运行

### 1. 克隆 & 安装

```bash
git clone https://github.com/your-username/TG-Discord-Aggregator.git
cd TG-Discord-Aggregator
pip install -r requirements.txt
```

### 2. 配置文件

复制模板并重命名为 `config.json`：

```bash
cp config.example.json config.json
```

`config.json` 参考结构：

> **注意**：标准 JSON 不支持注释。复制以下内容填入时，请务必删除所有 `//` 开头的注释内容，或参考 `config.example.json`。

```json
{
  "telegram": {
    "api_id": 123456,
    "api_hash": "你的_API_HASH",
    "phone_number": "+8613800000000"
  },
  "r2": {
    "endpoint_url": "xxxx.r2.cloudflarestorage.com",
    "access_key": "你的_R2_ACCESS_KEY",
    "secret_key": "你的_R2_SECRET_KEY",
    "bucket_name": "tg-aggregator",
    "public_url": "https://pub-xxxx.r2.dev"
  },
  "mappings": [
    {
      "comment": "聚合源 1：普通群组",
      "tg_chat_id": -100123456789,
      "tg_topic_id": null,
      "discord_webhook_url": "https://discord.com/api/webhooks/...",
      "target_user_ids": null
    },
    {
      "comment": "聚合源 2：特定话题",
      "tg_chat_id": -100987654321,
      "tg_topic_id": 123, 
      "discord_webhook_url": "https://discord.com/api/webhooks/...",
      "target_user_ids": [12345678]
    }
  ]
}
```

### 3. 启动聚合器

前台运行（首次登录需验证码）：

```bash
python main.py
```

后台运行：

```bash
nohup python3 main.py > output.log 2>&1 &
```

---

## ⚠️ 安全与注意事项

- **敏感文件**：`config.json` 和 `*.session` 文件包含你的账号权限和登录状态，**严禁上传到 GitHub 或发送给他人**。建议在 `.gitignore` 中添加这些文件。
- **R2 额度**：Cloudflare R2 每月提供 10GB 免费存储和 100万次 写入操作（A类操作），这对于绝大多数个人聚合场景已经绰绰有余，但仍建议留意用量。

---

## 📜 License

MIT License
