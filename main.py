import asyncio
import logging
from telethon import TelegramClient, events, types
import json
import sys
import os
import aiohttp
import aiofiles
import boto3
from botocore.exceptions import ClientError
import uuid

# --- 日志配置 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("output.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

# --- 加载配置文件 ---
def load_config():
    config_path = 'config.json'
    if not os.path.exists(config_path):
        logging.error(f"配置文件 {config_path} 未找到！请参考 config.example.json 创建。")
        sys.exit(1)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"读取配置文件失败: {e}")
        sys.exit(1)

# --- 初始化配置 ---
config_data = load_config()

# Telegram 配置
api_id = config_data['telegram']['api_id']
api_hash = config_data['telegram']['api_hash']
phone_number = config_data['telegram']['phone_number']

# Cloudflare R2 图床配置
r2_config = config_data.get('r2', {})
R2_ENDPOINT_URL = r2_config.get('endpoint_url')
R2_ACCESS_KEY = r2_config.get('access_key')
R2_SECRET_KEY = r2_config.get('secret_key')
R2_BUCKET_NAME = r2_config.get('bucket_name')
PUBLIC_R2_URL = r2_config.get('public_url')

# --- 构建监控映射关系 ---
# 将 JSON 中的列表转换为代码逻辑所需的字典格式
monitored_chats = {}
for item in config_data.get('mappings', []):
    chat_id = item['tg_chat_id']
    topic_id = item.get('tg_topic_id')
    
    # 构造 value 字典
    config_value = {
        'webhook_url': item['discord_webhook_url'],
        'target_user_ids': item.get('target_user_ids')
    }
    
    # 如果指定了 topic_id，使用 (chat_id, topic_id) 作为键
    if topic_id is not None:
        monitored_chats[(chat_id, topic_id)] = config_value
    else:
        # 否则直接使用 chat_id 作为键
        monitored_chats[chat_id] = config_value

# --- 客户端初始化 ---
client = TelegramClient('anon', api_id, api_hash)
media_group_cache = {}

# 确保临时目录存在
if not os.path.exists("tg_temp"):
    os.makedirs("tg_temp")

AVATAR_CACHE_FILE = "avatar_cache.json"

async def load_avatar_cache():
    if os.path.exists(AVATAR_CACHE_FILE):
        try:
            async with aiofiles.open(AVATAR_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.loads(await f.read())
        except (IOError, json.JSONDecodeError) as e:
            logging.error(f"加载头像缓存失败: {e}")
            return {}
    return {}

async def save_avatar_cache(cache):
    try:
        async with aiofiles.open(AVATAR_CACHE_FILE, 'w', encoding='utf-8') as f:
            await f.write(json.dumps(cache, ensure_ascii=False, indent=4))
    except IOError as e:
        logging.error(f"保存头像缓存失败: {e}")

async def upload_to_cloudflare_r2(file_path):
    if not all([R2_ENDPOINT_URL, R2_ACCESS_KEY, R2_SECRET_KEY, R2_BUCKET_NAME, PUBLIC_R2_URL]):
        logging.warning("R2 配置不完整，跳过上传。")
        return None

    try:
        # 处理 endpoint_url，去掉 https:// 前缀如果是 boto3 需要的话，但通常 boto3 需要完整的或者域名的
        # 这里假设用户在 json 里填的是域名部分，如果报错可以调整
        endpoint = f'https://{R2_ENDPOINT_URL}' if not R2_ENDPOINT_URL.startswith('http') else R2_ENDPOINT_URL
        
        s3 = boto3.client(
            service_name='s3', 
            endpoint_url=endpoint,
            aws_access_key_id=R2_ACCESS_KEY, 
            aws_secret_access_key=R2_SECRET_KEY, 
            region_name='auto'
        )
        _, extension = os.path.splitext(file_path)
        object_name = f"{uuid.uuid4().hex}{extension}"
        
        with open(file_path, 'rb') as f:
            await asyncio.to_thread(s3.upload_fileobj, f, R2_BUCKET_NAME, object_name)
        
        logging.info(f"✅ 文件 {os.path.basename(file_path)} 已作为 {object_name} 成功上传。")
        return f"{PUBLIC_R2_URL}/{object_name}"
    except ClientError as e:
        logging.error(f"❌ 上传到 Cloudflare R2 失败: {e.response['Error']['Code']}")
        return None
    except Exception as e:
        logging.error(f"❌ 上传到 Cloudflare R2 时发生未知错误: {e}", exc_info=True)
        return None

async def send_to_discord(webhook_url, sender_name, content, file_path=None, image_urls=None, avatar_url=None):
    if avatar_url and not (avatar_url.startswith('http://') or avatar_url.startswith('https://')):
        avatar_url = "https://cdn-icons-png.flaticon.com/512/2111/2111646.png"
    
    payload = {
        "username": f"{sender_name}", 
        "avatar_url": avatar_url if avatar_url else "https://cdn-icons-png.flaticon.com/512/2111/2111646.png"
    }
    
    if image_urls:
        payload["embeds"] = [{"image": {"url": url}} for url in image_urls]
    
    if content:
        payload["content"] = content
        
    if not content and not file_path and not image_urls:
        logging.warning("警告: 消息既没有文本也没有附件，不发送到Discord。")
        return

    async with aiohttp.ClientSession() as session:
        try:
            if file_path:
                with open(file_path, 'rb') as f:
                    form_data = aiohttp.FormData()
                    form_data.add_field('payload_json', json.dumps(payload))
                    form_data.add_field('file', f, filename=os.path.basename(file_path))
                    async with session.post(webhook_url, data=form_data) as response:
                        response.raise_for_status()
            else:
                async with session.post(webhook_url, json=payload) as response:
                    response.raise_for_status()
        except aiohttp.ClientError as err:
            logging.error(f"发送消息到Discord时发生网络错误: {err}")
        except Exception as err:
            logging.error(f"发送消息到Discord时发生未知错误: {err}", exc_info=True)

async def get_sender_details(sender):
    sender_name = '未知用户'
    if isinstance(sender, types.User):
        sender_name = sender.first_name or '未知用户'
        if sender.last_name:
            sender_name += f" {sender.last_name}"
    elif isinstance(sender, types.Channel):
        sender_name = sender.title or '未知频道'
    
    sender_id = str(sender.id) if hasattr(sender, 'id') else None
    avatar_cache = await load_avatar_cache()
    avatar_url = avatar_cache.get(sender_id)

    if avatar_url:
        logging.info(f"头像缓存命中: 找到了用户 '{sender_name}' ({sender_id}) 的头像。")
    elif sender and hasattr(sender, 'photo') and sender.photo:
        logging.info(f"头像缓存未命中: 用户 '{sender_name}' ({sender_id}) 的头像不在缓存中，开始获取...")
        try:
            avatar_path = await client.download_profile_photo(sender, file="tg_temp/")
            if avatar_path:
                logging.info(f"已下载用户 '{sender_name}' 的头像，准备上传...")
                avatar_url = await upload_to_cloudflare_r2(avatar_path)
                os.remove(avatar_path)
                if avatar_url and sender_id:
                    avatar_cache[sender_id] = avatar_url
                    await save_avatar_cache(avatar_cache)
                    logging.info(f"✅ 成功缓存用户 '{sender_name}' ({sender_id}) 的新头像。")
        except Exception as e:
            logging.error(f"动态获取用户 '{sender_name}' 的头像时出错: {e}", exc_info=True)
            
    return sender_name, avatar_url

async def process_media_group(group_id, webhook_url):
    await asyncio.sleep(2.0)
    try:
        if group_id not in media_group_cache: return
        grouped_messages = media_group_cache[group_id]['messages']
        grouped_messages.sort(key=lambda m: m.id)
        
        first_message = grouped_messages[0]
        sender = await first_message.get_sender()
        sender_name, avatar_url = await get_sender_details(sender)
        
        message_text = next((msg.text for msg in grouped_messages if msg.text), '')
        image_urls = []
        
        logging.info(f"正在处理媒体组 {group_id}，包含 {len(grouped_messages)} 个项目...")
        for msg in grouped_messages:
            if msg.photo or (msg.file and 'image' in msg.file.mime_type):
                media_path = await client.download_media(msg, file="tg_temp/")
                if media_path:
                    url = await upload_to_cloudflare_r2(media_path)
                    os.remove(media_path)
                    if url:
                        image_urls.append(url)
        
        if image_urls:
            await send_to_discord(webhook_url, sender_name, message_text, image_urls=image_urls, avatar_url=avatar_url)
            
    except Exception as e:
        logging.error(f"处理媒体组 {group_id} 时出错: {e}", exc_info=True)
    finally:
        if group_id in media_group_cache:
            del media_group_cache[group_id]
            logging.info(f"已清理媒体组 {group_id} 的缓存。")

# 计算需要监听的 chat_id 列表
listen_chats = list(set([k[0] if isinstance(k, tuple) else k for k in monitored_chats.keys()]))

@client.on(events.NewMessage(chats=listen_chats))
async def handle_new_message(event):
    chat_id = event.chat_id
    # 获取回复消息的 ID 作为 Topic ID (如果是 Forum 频道)
    message_topic_id = event.message.reply_to.reply_to_msg_id if event.message.reply_to else None
    
    config = None
    
    # 1. 优先匹配 (chat_id, topic_id) 的精确配置
    if (chat_id, message_topic_id) in monitored_chats:
        config = monitored_chats[(chat_id, message_topic_id)]
    # 2. 其次匹配 chat_id 的通用配置
    elif chat_id in monitored_chats:
        # 需要确保取出的不是其他 topic 的配置，这里逻辑需要严谨，简化处理：
        # 如果 monitored_chats[chat_id] 存在且是个字典（不是我们在上面构建时的 tuple key），则使用
        # 在上面构建时，如果 topic_id 是 None，我们就用了 chat_id 直接做 key
        config = monitored_chats.get(chat_id)

    if not config: return

    if event.message.grouped_id:
        group_id = event.message.grouped_id
        if group_id not in media_group_cache:
            media_group_cache[group_id] = {
                'messages': [],
                'task': asyncio.create_task(process_media_group(group_id, config['webhook_url']))
            }
        media_group_cache[group_id]['messages'].append(event.message)
        return

    try:
        sender = await event.get_sender()
        if not sender: return
        
        target_user_ids = config.get('target_user_ids')
        if target_user_ids and sender.id not in target_user_ids: return
        
        sender_name, avatar_url = await get_sender_details(sender)
        message_text = event.message.text or ''
        
        if event.message.reply_to:
            try:
                original_message = await event.get_reply_message()
                if original_message and original_message.text:
                    reply_text = original_message.text.replace('\n', '\n> ')
                    message_text = f"> {reply_text}\n\n{message_text}"
            except Exception: pass
            
        file_path, image_urls = None, []
        
        if event.message.file and ('gif' in event.message.file.mime_type or 'video' in event.message.file.mime_type or 'sticker' in event.message.file.mime_type):
            logging.info(f"检测到来自 {sender_name} 的文件（动图/视频/贴纸），准备下载...")
            file_path = await client.download_media(event.message, file="tg_temp/")
            
        elif event.message.photo or (event.message.file and 'image' in event.message.file.mime_type):
            logging.info(f"检测到来自 {sender_name} 的单张图片，准备下载上传...")
            media_path = await client.download_media(event.message, file="tg_temp/")
            if media_path:
                url = await upload_to_cloudflare_r2(media_path)
                os.remove(media_path)
                if url:
                    image_urls.append(url)
                    
        if not message_text and not file_path and not image_urls: return
        
        logging.info(f"检测到来自群组 {chat_id} [话题: {message_topic_id}] 的新消息，发送者: {sender_name}")
        await send_to_discord(config['webhook_url'], sender_name, message_text, file_path=file_path, image_urls=image_urls, avatar_url=avatar_url)
        
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            
    except Exception as e:
        logging.error(f"处理单条消息时发生严重错误: {e}", exc_info=True)

async def main():
    logging.info("正在连接到Telegram...")
    try:
        await client.start(phone=phone_number)
        logging.info("连接成功！")
        logging.info(f"正在监听 {len(listen_chats)} 个群组的新消息...")
        await client.run_until_disconnected()
    except Exception as e:
        logging.critical(f"启动或连接时发生致命错误: {e}", exc_info=True)

if __name__ == '__main__':
    asyncio.run(main())