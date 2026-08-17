# -*- coding: utf-8 -*-

import os
import logging
import sys
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from io import BytesIO
from typing import Dict, List, Optional

import telebot
from telebot.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

# Выводим версию Python при запуске
print(f"Python version: {sys.version}")
print(f"Python path: {sys.executable}")

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# =========================
# ENV
# =========================
TOKEN = (os.getenv("BOT_TOKEN") or "").strip()

if not TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# =========================
# UI BUTTONS
# =========================
BTN_STORY = "📱 Создать сторис"
BTN_ENHANCE = "✨ Улучшить качество"

def main_menu_kb():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(KeyboardButton(BTN_STORY))
    kb.row(KeyboardButton(BTN_ENHANCE))
    return kb

# =========================
# BOT
# =========================
bot = telebot.TeleBot(TOKEN)

# Хранилище состояний пользователей
user_state: Dict[int, Dict] = {}

# Константы для сторис
STORY_WIDTH = 1080
STORY_HEIGHT = 1920
MARGIN = 60
IMAGE_HEIGHT_RATIO = 0.60  # Фото занимает 60% высоты

# =========================
# FONTS
# =========================
def get_font_path(bold=False):
    """Ищет шрифт в разных местах"""
    font_paths = [
        "Inter-Black.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
        "arialbd.ttf",
        "Arial.ttf"
    ]
    
    if not bold:
        font_paths = [
            "Inter-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
            "arial.ttf",
            "Arial.ttf"
        ]
    
    for path in font_paths:
        if os.path.exists(path):
            return path
    
    return None

def get_font(size, bold=False):
    """Загружает шрифт"""
    font_path = get_font_path(bold)
    if font_path:
        try:
            return ImageFont.truetype(font_path, size)
        except:
            pass
    return ImageFont.load_default()

# =========================
# STORY MAKING - НОВЫЙ ДИЗАЙН
# =========================
def create_gradient(width, height, color1, color2):
    """Создает плавный градиент"""
    gradient = Image.new('RGB', (width, height))
    draw = ImageDraw.Draw(gradient)
    
    for y in range(height):
        ratio = y / height
        r = int(color1[0] + (color2[0] - color1[0]) * ratio)
        g = int(color1[1] + (color2[1] - color1[1]) * ratio)
        b = int(color1[2] + (color2[2] - color1[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    
    return gradient

def wrap_text(text, font, max_width, draw):
    """Разбивает текст на строки по ширине"""
    if not text:
        return []
    
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        try:
            bbox = draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
        except:
            width = len(test_line) * 20
        
        if width <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return lines

def make_story(photo_bytes: bytes, title: str, text: str) -> BytesIO:
    """
    Создает сторис с дизайном как на примере:
    - Фото сверху на 60% высоты
    - Белый эллипс с заголовком
    - Черный фон с текстом снизу
    """
    # Создаем холст
    story = Image.new('RGB', (STORY_WIDTH, STORY_HEIGHT), (0, 0, 0))
    draw = ImageDraw.Draw(story)
    
    # 1. Загружаем и вставляем фото
    try:
        user_img = Image.open(BytesIO(photo_bytes))
        user_img = user_img.convert('RGB')
        
        # Вычисляем размеры для фото
        img_width = STORY_WIDTH - 2 * MARGIN
        img_height = int(STORY_HEIGHT * IMAGE_HEIGHT_RATIO)
        
        # Обрезаем фото с сохранением пропорций (cover)
        img_ratio = user_img.width / user_img.height
        target_ratio = img_width / img_height
        
        if img_ratio > target_ratio:
            new_width = int(img_height * img_ratio)
            user_img = user_img.resize((new_width, img_height), Image.Resampling.LANCZOS)
            left = (new_width - img_width) // 2
            user_img = user_img.crop((left, 0, left + img_width, img_height))
        else:
            new_height = int(img_width / img_ratio)
            user_img = user_img.resize((img_width, new_height), Image.Resampling.LANCZOS)
            top = (new_height - img_height) // 2
            user_img = user_img.crop((0, top, img_width, top + img_height))
        
        # Вставляем фото
        story.paste(user_img, (MARGIN, MARGIN))
        logger.info("Фото обработано и вставлено")
        
    except Exception as e:
        logger.error(f"Ошибка обработки фото: {e}")
        return None
    
    # 2. Рисуем белый эллипс
    ellipse_y_start = MARGIN + int(STORY_HEIGHT * IMAGE_HEIGHT_RATIO) + 20
    ellipse_height = 140
    ellipse_y_end = ellipse_y_start + ellipse_height
    
    # Создаем слой для эллипса с прозрачностью
    ellipse_layer = Image.new('RGBA', (STORY_WIDTH, STORY_HEIGHT), (0, 0, 0, 0))
    ellipse_draw = ImageDraw.Draw(ellipse_layer)
    ellipse_draw.ellipse(
        [MARGIN, ellipse_y_start, STORY_WIDTH - MARGIN, ellipse_y_end],
        fill=(255, 255, 255, 230)
    )
    
    # Накладываем эллипс
    story = story.convert('RGBA')
    story = Image.alpha_composite(story, ellipse_layer)
    story = story.convert('RGB')
    draw = ImageDraw.Draw(story)
    
    # 3. Рисуем заголовок внутри эллипса
    title_font = get_font(48, bold=True)
    title_padding = 40
    title_max_width = STORY_WIDTH - 2 * MARGIN - 2 * title_padding
    title_lines = wrap_text(title, title_font, title_max_width, draw)
    
    # Ограничиваем заголовок 3 строками
    if len(title_lines) > 3:
        title_lines = title_lines[:3]
    
    # Центрируем заголовок по вертикали в эллипсе
    total_title_height = 0
    for line in title_lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            total_title_height += bbox[3] - bbox[1]
        except:
            total_title_height += 50
    total_title_height += (len(title_lines) - 1) * 10
    
    title_y = ellipse_y_start + (ellipse_height - total_title_height) // 2
    
    for i, line in enumerate(title_lines):
        try:
            bbox = draw.textbbox((0, 0), line, font=title_font)
            text_width = bbox[2] - bbox[0]
        except:
            text_width = len(line) * 30
        x = (STORY_WIDTH - text_width) // 2
        y = title_y + i * 55
        draw.text((x, y), line, fill=(0, 0, 0), font=title_font)
    
    # 4. Рисуем основной текст на черном фоне
    text_start_y = ellipse_y_end + 20
    text_area_height = STORY_HEIGHT - text_start_y - MARGIN
    
    # Подбираем размер шрифта для текста
    text_font_size = 32
    text_lines = []
    
    for size in range(36, 18, -2):
        try:
            test_font = get_font(size, bold=False)
            test_lines = wrap_text(text, test_font, STORY_WIDTH - 2 * MARGIN - 40, draw)
            
            # Считаем общую высоту
            total_h = 0
            for line in test_lines:
                try:
                    bbox = draw.textbbox((0, 0), line, font=test_font)
                    total_h += bbox[3] - bbox[1]
                except:
                    total_h += size
            total_h += (len(test_lines) - 1) * int(size * 0.2)
            
            if total_h <= text_area_height and len(test_lines) <= 8:
                text_font_size = size
                text_lines = test_lines
                break
        except:
            continue
    
    # Если не подобрали - используем минимальный
    if not text_lines:
        text_font_size = 20
        text_font = get_font(text_font_size, bold=False)
        text_lines = wrap_text(text, text_font, STORY_WIDTH - 2 * MARGIN - 40, draw)
        if len(text_lines) > 8:
            text_lines = text_lines[:8]
            text_lines[-1] = text_lines[-1] + "..."
    
    text_font = get_font(text_font_size, bold=False)
    
    # Рисуем текст
    y = text_start_y
    for line in text_lines:
        try:
            bbox = draw.textbbox((0, 0), line, font=text_font)
            text_width = bbox[2] - bbox[0]
        except:
            text_width = len(line) * 15
        x = (STORY_WIDTH - text_width) // 2
        draw.text((x, y), line, fill=(255, 255, 255), font=text_font)
        y += text_font_size + int(text_font_size * 0.2)
    
    # Сохраняем результат
    out = BytesIO()
    story.save(out, format="JPEG", quality=95, optimize=True)
    out.seek(0)
    return out

# =========================
# IMAGE ENHANCE
# =========================
def enhance_image(image_bytes: bytes) -> BytesIO:
    """Улучшает качество фото"""
    try:
        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        
        # Увеличиваем резкость
        enhancer = ImageEnhance.Sharpness(img)
        img = enhancer.enhance(1.2)
        
        # Увеличиваем насыщенность
        enhancer = ImageEnhance.Color(img)
        img = enhancer.enhance(1.15)
        
        out = BytesIO()
        img.save(out, format="JPEG", quality=98, optimize=True)
        out.seek(0)
        return out
    except Exception as e:
        logger.error(f"Ошибка улучшения: {e}")
        return BytesIO(image_bytes)

# =========================
# HEALTH CHECK
# =========================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Bot is running!")

def run_http_server():
    try:
        port = int(os.environ.get('PORT', 10000))
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        logger.info(f"Health check server on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Health check server error: {e}")

# =========================
# TELEGRAM HANDLERS
# =========================
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    uid = message.from_user.id
    user_state[uid] = {"step": "idle"}
    
    bot.send_message(
        message.chat.id,
        "👋 <b>Привет! Я создаю стильные сторис для Instagram</b>\n\n"
        "📱 Как это работает:\n"
        "1️⃣ Отправь мне фото\n"
        "2️⃣ Отправь текст для сторис\n"
        "3️⃣ Получи готовую сторис\n\n"
        "<i>Первые 2-3 строки станут заголовком в белом эллипсе</i>",
        parse_mode="HTML",
        reply_markup=main_menu_kb()
    )

@bot.message_handler(commands=["story"])
def cmd_story(message):
    uid = message.from_user.id
    user_state[uid] = {"step": "waiting_photo", "type": "story"}
    bot.send_message(
        message.chat.id,
        "📸 Отправь фото для сторис:",
        reply_markup=main_menu_kb()
    )

@bot.message_handler(commands=["enhance"])
def cmd_enhance(message):
    uid = message.from_user.id
    user_state[uid] = {"step": "waiting_enhance"}
    bot.send_message(
        message.chat.id,
        "✨ Отправь фото для улучшения качества:",
        reply_markup=main_menu_kb()
    )

@bot.message_handler(func=lambda m: m.text == BTN_STORY)
def handle_story_button(message):
    cmd_story(message)

@bot.message_handler(func=lambda m: m.text == BTN_ENHANCE)
def handle_enhance_button(message):
    cmd_enhance(message)

@bot.message_handler(content_types=["photo", "document"])
def handle_media(message):
    uid = message.from_user.id
    st = user_state.get(uid, {"step": "idle"})
    step = st.get("step")
    
    # Улучшение фото
    if step == "waiting_enhance":
        try:
            if message.content_type == "photo":
                file_id = message.photo[-1].file_id
            else:
                doc = message.document
                if not doc.mime_type or not doc.mime_type.startswith("image/"):
                    bot.reply_to(message, "❌ Отправьте изображение")
                    return
                file_id = doc.file_id
            
            file_info = bot.get_file(file_id)
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
            
            import requests
            response = requests.get(file_url)
            photo_bytes = response.content
            
            enhanced = enhance_image(photo_bytes)
            
            bot.send_document(
                message.chat.id,
                document=enhanced,
                visible_file_name="enhanced.jpg",
                caption="✨ Фото улучшено!"
            )
            
            user_state[uid] = {"step": "idle"}
            
        except Exception as e:
            logger.error(f"Enhance error: {e}")
            bot.reply_to(message, f"❌ Ошибка: {e}")
        return
    
    # Создание сторис
    if step == "waiting_photo":
        try:
            if message.content_type == "photo":
                file_id = message.photo[-1].file_id
            else:
                doc = message.document
                if not doc.mime_type or not doc.mime_type.startswith("image/"):
                    bot.reply_to(message, "❌ Отправьте изображение")
                    return
                file_id = doc.file_id
            
            file_info = bot.get_file(file_id)
            file_url = f"https://api.telegram.org/file/bot{TOKEN}/{file_info.file_path}"
            
            import requests
            response = requests.get(file_url)
            photo_bytes = response.content
            
            st["photo_bytes"] = photo_bytes
            st["step"] = "waiting_text"
            user_state[uid] = st
            
            bot.reply_to(
                message,
                "✅ Фото сохранено!\n\n"
                "📝 Теперь отправь ТЕКСТ для сторис:\n"
                "<i>Первые 2-3 строки станут заголовком</i>",
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"Photo error: {e}")
            bot.reply_to(message, f"❌ Ошибка: {e}")
        return
    
    else:
        bot.reply_to(message, "Нажми кнопку 📱 Создать сторис", reply_markup=main_menu_kb())

@bot.message_handler(content_types=["text"])
def handle_text(message):
    uid = message.from_user.id
    text = message.text.strip()
    st = user_state.get(uid, {"step": "idle"})
    step = st.get("step")
    
    # Обработка текста для сторис
    if step == "waiting_text":
        if not text:
            bot.reply_to(message, "❌ Текст не может быть пустым")
            return
        
        # Разделяем на заголовок и текст
        lines = text.split('\n')
        
        # Заголовок - первые 2-3 строки
        if len(lines) >= 3:
            title = '\n'.join(lines[:3])
            body = '\n'.join(lines[3:])
        elif len(lines) >= 2:
            title = '\n'.join(lines[:2])
            body = '\n'.join(lines[2:])
        else:
            title = lines[0] if lines else " "
            body = ""
        
        if not body.strip():
            body = " "
        
        try:
            # Создаем сторис
            processing_msg = bot.reply_to(message, "⏳ Создаю сторис...")
            
            story_image = make_story(
                st["photo_bytes"],
                title.upper(),
                body
            )
            
            if story_image:
                # Отправляем результат
                bot.send_photo(
                    message.chat.id,
                    photo=story_image,
                    caption="✅ Готово! Сторис можно сохранить и публиковать в Instagram."
                )
                
                bot.delete_message(message.chat.id, processing_msg.message_id)
            else:
                bot.reply_to(message, "❌ Ошибка при создании сторис")
            
            user_state[uid] = {"step": "idle"}
            
        except Exception as e:
            logger.error(f"Story error: {e}")
            bot.reply_to(message, f"❌ Ошибка: {e}")
        return
    
    else:
        bot.reply_to(message, "Нажми кнопку 📱 Создать сторис", reply_markup=main_menu_kb())

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    logger.info("🚀 Запуск бота...")
    
    # Запускаем health check сервер
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()
    
    # Запускаем бота
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except Exception as e:
        logger.error(f"Bot error: {e}")
