import os
import logging
import re
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputFile
from aiogram.contrib.middlewares.logging import LoggingMiddleware
import textwrap
import asyncio

# ========== КОНФИГ ==========
API_TOKEN = os.getenv("BOT_TOKEN")

if not API_TOKEN:
    raise ValueError("❌ Токен не найден! Создай переменную BOT_TOKEN в настройках Render.")

# Шрифты
FONT_PATH_BOLD = "Inter-Bold.ttf"
FONT_PATH_REG = "Inter-Regular.ttf"
FONT_PATH_MEDIUM = "Inter-Medium.ttf"

# Фоновое изображение
BACKGROUND_IMAGE = "fon.png"

# Размеры сторис
W, H = 1080, 1920

# ========== НОВЫЕ ОТСТУПЫ ДЛЯ ДИЗАЙНА ==========
# ФОТО
PHOTO_TOP = 50
PHOTO_HEIGHT = 710
PHOTO_WIDTH = W - 80
PHOTO_LEFT = 40

# БЛОК "НОВОСТИ"
NEWS_BLOCK_TOP = PHOTO_TOP + PHOTO_HEIGHT + 25
NEWS_BLOCK_HEIGHT = 70

# ЗАГОЛОВОК
TITLE_TOP = NEWS_BLOCK_TOP + NEWS_BLOCK_HEIGHT + 30
TITLE_MAX_WIDTH = W - 100

# КНОПКА
BUTTON_BOTTOM = 150

# ========== НАСТРОЙКА ЛОГОВ ==========
logging.basicConfig(level=logging.INFO)

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# ========== ПАРСИНГ ТЕКСТА ==========
def parse_text(text: str) -> tuple:
    if not text:
        return "", ""
    
    text = text.strip()
    
    paragraphs = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    if len(paragraphs) > 1:
        title = paragraphs[0]
        content = "\n\n".join(paragraphs[1:])
    else:
        lines = text.split('\n')
        lines = [l.strip() for l in lines if l.strip()]
        
        if len(lines) > 1:
            title = lines[0]
            content = '\n\n'.join(lines[1:])
        else:
            match = re.search(r'\.\s+([А-ЯA-Z])', text)
            if match:
                cut_pos = match.start() + 1
                title = text[:cut_pos].strip()
                content = text[cut_pos:].strip()
            else:
                match = re.search(r'[?!]\s+([А-ЯA-Z])', text)
                if match:
                    cut_pos = match.start() + 1
                    title = text[:cut_pos].strip()
                    content = text[cut_pos:].strip()
                else:
                    title = text
                    content = ""
    
    if len(title) > 150:
        last_dot = title.rfind('.', 0, 150)
        last_q = title.rfind('?', 0, 150)
        last_excl = title.rfind('!', 0, 150)
        cut_pos = max(last_dot, last_q, last_excl)
        
        if cut_pos > 0:
            remaining = title[cut_pos+1:].strip()
            title = title[:cut_pos+1].strip()
            if remaining:
                content = remaining + "\n\n" + content if content else remaining
        else:
            title = title[:147] + "..."
    
    return title, content

# ========== РЕТРО-ЭФФЕКТ (для фото) ==========
def apply_retro_effect(image: Image.Image) -> Image.Image:
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(0.75)
    
    width, height = image.size
    sepia_overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    sepia_draw = ImageDraw.Draw(sepia_overlay)
    sepia_draw.rectangle([(0, 0), (width, height)], fill=(180, 130, 80, 40))
    image = image.convert('RGBA')
    image = Image.alpha_composite(image, sepia_overlay)
    image = image.convert('RGB')
    
    pixel_data = list(image.getdata())
    width, height = image.size
    
    noise_intensity = 22
    noisy_pixels = []
    
    for pixel in pixel_data:
        r, g, b = pixel
        noise_r = random.randint(-noise_intensity, noise_intensity)
        noise_g = random.randint(-noise_intensity, noise_intensity)
        noise_b = random.randint(-noise_intensity, noise_intensity)
        r = max(0, min(255, r + noise_r))
        g = max(0, min(255, g + noise_g))
        b = max(0, min(255, b + noise_b))
        noisy_pixels.append((r, g, b))
    
    noisy_image = Image.new('RGB', (width, height))
    noisy_image.putdata(noisy_pixels)
    noisy_image = noisy_image.filter(ImageFilter.GaussianBlur(radius=0.8))
    
    enhancer = ImageEnhance.Brightness(noisy_image)
    noisy_image = enhancer.enhance(1.1)
    
    return noisy_image

# ========== ГЕНЕРАЦИЯ СТОРИС ==========
async def generate_story(photo_path: str, title: str, content: str) -> str:
    logging.info(f"🖼 Генерация сторис в новом стиле:")
    logging.info(f"   Заголовок: {title[:100] if title else 'ПУСТО'}...")
    logging.info(f"   Контент: {content[:100] if content else 'ПУСТО'}...")
    
    # ============================================================
    # ШАГ 1: СОЗДАЕМ ХОЛСТ
    # ============================================================
    try:
        background = Image.open(BACKGROUND_IMAGE).convert("RGB")
        background = background.resize((W, H), Image.Resampling.LANCZOS)
        canvas = background
        logging.info(f"✅ Фоновое изображение загружено")
    except Exception as e:
        logging.warning(f"⚠️ Не удалось загрузить фон: {e}. Использую черный фон.")
        canvas = Image.new('RGB', (W, H), color='black')
    
    draw = ImageDraw.Draw(canvas)
    
    # ============================================================
    # ШАГ 2: ЗАГРУЖАЕМ ШРИФТЫ
    # ============================================================
    try:
        font_bold = ImageFont.truetype(FONT_PATH_BOLD, 60)
        font_reg = ImageFont.truetype(FONT_PATH_REG, 40)
        font_medium = ImageFont.truetype(FONT_PATH_MEDIUM, 40)
    except Exception as e:
        logging.warning(f"⚠️ Шрифт не загружен: {e}")
        font_bold = ImageFont.load_default()
        font_reg = ImageFont.load_default()
        font_medium = ImageFont.load_default()
    
    # ============================================================
    # ШАГ 3: ВСТАВЛЯЕМ ФОТО
    # ============================================================
    try:
        photo = Image.open(photo_path).convert("RGB")
        
        # Обрезаем фото до пропорций 1000x710
        photo_ratio = photo.width / photo.height
        target_ratio = PHOTO_WIDTH / PHOTO_HEIGHT
        
        if photo_ratio > target_ratio:
            new_height = PHOTO_HEIGHT
            new_width = int(new_height * photo_ratio)
            photo = photo.resize((new_width, new_height), Image.Resampling.LANCZOS)
            left = (new_width - PHOTO_WIDTH) // 2
            photo = photo.crop((left, 0, left + PHOTO_WIDTH, new_height))
        else:
            new_width = PHOTO_WIDTH
            new_height = int(new_width / photo_ratio)
            photo = photo.resize((new_width, new_height), Image.Resampling.LANCZOS)
            top = (new_height - PHOTO_HEIGHT) // 2
            photo = photo.crop((0, top, new_width, top + PHOTO_HEIGHT))
        
        # Применяем ретро-эффект
        photo = apply_retro_effect(photo)
        
        # Вставляем фото с белой рамкой
        bordered_photo = Image.new('RGB', (PHOTO_WIDTH + 4, PHOTO_HEIGHT + 4), color='white')
        bordered_photo.paste(photo, (2, 2))
        canvas.paste(bordered_photo, (PHOTO_LEFT, PHOTO_TOP))
    except Exception as e:
        logging.error(f"❌ Ошибка при обработке фото: {e}")
        # Рисуем заглушку
        draw.rectangle([PHOTO_LEFT, PHOTO_TOP, PHOTO_LEFT + PHOTO_WIDTH, PHOTO_TOP + PHOTO_HEIGHT], fill='#333333')
        draw.text((W//2 - 100, PHOTO_TOP + PHOTO_HEIGHT//2), "ФОТО НЕ ЗАГРУЖЕНО", font=font_reg, fill='white')
    
    # ============================================================
    # ШАГ 4: БЛОК "НОВОСТИ"
    # ============================================================
    draw.rectangle(
        [PHOTO_LEFT, NEWS_BLOCK_TOP, PHOTO_LEFT + PHOTO_WIDTH, NEWS_BLOCK_TOP + NEWS_BLOCK_HEIGHT],
        fill='#2A2A2A',
        outline='#6C3CE1',
        width=2
    )
    
    news_text = "НОВОСТИ"
    try:
        news_font = ImageFont.truetype(FONT_PATH_BOLD, 32)
    except:
        news_font = ImageFont.load_default()
    
    news_bbox = draw.textbbox((0, 0), news_text, font=news_font)
    news_w = news_bbox[2] - news_bbox[0]
    news_h = news_bbox[3] - news_bbox[1]
    
    news_x = (W - news_w) // 2
    news_y = NEWS_BLOCK_TOP + (NEWS_BLOCK_HEIGHT - news_h) // 2
    draw.text((news_x, news_y), news_text, font=news_font, fill='white')
    
    # ============================================================
    # ШАГ 5: ЗАГОЛОВОК
    # ============================================================
    title_y = TITLE_TOP
    max_title_height = 200
    
    title_font_size = 56
    title_lines = []
    
    for size in range(72, 32, -2):
        try:
            test_font = ImageFont.truetype(FONT_PATH_BOLD, size)
        except:
            test_font = ImageFont.load_default()
        
        words = title.upper().split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=test_font)
            if bbox[2] - bbox[0] <= TITLE_MAX_WIDTH:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))
        
        if lines:
            test_text = "\n".join(lines)
            bbox = draw.textbbox((0, 0), test_text, font=test_font)
            title_h = bbox[3] - bbox[1]
            
            if title_h <= max_title_height and len(lines) <= 3:
                title_font_size = size
                title_lines = lines
                break
    else:
        try:
            title_font = ImageFont.truetype(FONT_PATH_BOLD, 32)
        except:
            title_font = ImageFont.load_default()
        words = title.upper().split()
        lines = []
        current_line = []
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=title_font)
            if bbox[2] - bbox[0] <= TITLE_MAX_WIDTH:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))
        title_lines = lines
        title_font_size = 32
    
    try:
        title_font = ImageFont.truetype(FONT_PATH_BOLD, title_font_size)
    except:
        title_font = ImageFont.load_default()
    
    title_text = "\n".join(title_lines)
    draw.text((50, title_y), title_text, font=title_font, fill='white')
    
    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_height = title_bbox[3] - title_bbox[1]
    title_end_y = title_y + title_height
    
    logging.info(f"📐 Размер заголовка: {title_font_size}px, строк: {len(title_lines)}")
    
    # ============================================================
    # ШАГ 6: ФИОЛЕТОВАЯ ЛИНИЯ
    # ============================================================
    LINE_TOP = title_end_y + 15
    LINE_HEIGHT = 3
    draw.rectangle(
        [50, LINE_TOP, W - 50, LINE_TOP + LINE_HEIGHT],
        fill='#6C3CE1'
    )
    
    # ============================================================
    # ШАГ 7: ТЕКСТ НОВОСТИ
    # ============================================================
    text_y = LINE_TOP + LINE_HEIGHT + 35
    
    button_y = H - BUTTON_BOTTOM - 50
    available_text_height = button_y - text_y - 50
    
    if content and content != "Текст отсутствует":
        paragraphs = content.split('\n\n')
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
    else:
        paragraphs = ["Текст отсутствует"]
    
    text_font_size = 34
    wrapped_paragraphs = []
    
    for size in range(42, 20, -2):
        try:
            test_font = ImageFont.truetype(FONT_PATH_REG, size)
        except:
            test_font = ImageFont.load_default()
        
        single_bbox = draw.textbbox((0, 0), "A", font=test_font)
        single_h = single_bbox[3] - single_bbox[1]
        
        total_height = 0
        temp_wrapped = []
        
        for para in paragraphs:
            chars_per_line = int((W - 100) / (size * 0.6))
            wrapped = textwrap.wrap(para, width=chars_per_line)
            if not wrapped:
                wrapped = [para]
            temp_wrapped.append(wrapped)
            
            para_height = len(wrapped) * (single_h + 6)
            total_height += para_height + 15
        
        if total_height <= available_text_height:
            text_font_size = size
            wrapped_paragraphs = temp_wrapped
            break
    else:
        try:
            text_font = ImageFont.truetype(FONT_PATH_REG, 20)
        except:
            text_font = ImageFont.load_default()
        single_bbox = draw.textbbox((0, 0), "A", font=text_font)
        single_h = single_bbox[3] - single_bbox[1]
        
        for para in paragraphs:
            chars_per_line = int((W - 100) / (20 * 0.6))
            wrapped = textwrap.wrap(para, width=chars_per_line)
            if not wrapped:
                wrapped = [para]
            wrapped_paragraphs.append(wrapped)
        text_font_size = 20
    
    try:
        text_font = ImageFont.truetype(FONT_PATH_REG, text_font_size)
    except:
        text_font = ImageFont.load_default()
    
    single_bbox = draw.textbbox((0, 0), "A", font=text_font)
    single_h = single_bbox[3] - single_bbox[1]
    
    pos_y = text_y
    for para_idx, para_lines in enumerate(wrapped_paragraphs):
        for line in para_lines:
            draw.text((50, pos_y), line, font=text_font, fill='white')
            pos_y += single_h + 6
        pos_y += 15
    
    logging.info(f"📐 Размер текста: {text_font_size}px, абзацев: {len(wrapped_paragraphs)}")
    
    # ============================================================
    # ШАГ 8: КНОПКА
    # ============================================================
    button_text = "ЧИТАТЬ ПОЛНОСТЬЮ НА САЙТЕ"
    try:
        button_font = ImageFont.truetype(FONT_PATH_MEDIUM, 28)
    except:
        button_font = ImageFont.load_default()
    
    button_bbox = draw.textbbox((0, 0), button_text, font=button_font)
    button_w = button_bbox[2] - button_bbox[0]
    button_h = button_bbox[3] - button_bbox[1]
    
    button_padding_x = 40
    button_padding_y = 20
    button_x1 = (W - button_w - button_padding_x * 2) // 2
    button_y1 = H - BUTTON_BOTTOM - button_h - button_padding_y * 2
    button_x2 = button_x1 + button_w + button_padding_x * 2
    button_y2 = button_y1 + button_h + button_padding_y * 2
    
    draw.rectangle(
        [button_x1, button_y1, button_x2, button_y2],
        fill='#6C3CE1',
        outline='#6C3CE1',
        width=2
    )
    
    button_text_x = (W - button_w) // 2
    button_text_y = button_y1 + (button_y2 - button_y1 - button_h) // 2
    draw.text((button_text_x, button_text_y), button_text, font=button_font, fill='white')
    
    # ============================================================
    # ШАГ 9: СОХРАНЯЕМ (исправлено: явно указываем кодировку)
    # ============================================================
    output_path = "output_story.png"
    try:
        # Сохраняем с явным указанием формата
        canvas.save(output_path, format='PNG')
        logging.info(f"✅ Сторис сохранена: {output_path}")
    except Exception as e:
        logging.error(f"❌ Ошибка при сохранении: {e}")
        # Пробуем сохранить с другим параметром
        canvas.save(output_path, format='PNG', optimize=True)
    
    return output_path

# ========== ОБЩАЯ ФУНКЦИЯ ==========
async def process_story(user_id: int, photo_path: str, title: str, content: str, message: types.Message):
    try:
        output = await generate_story(photo_path, title, content)
        
        # Отправляем фото
        with open(output, 'rb') as photo_file:
            await bot.send_photo(
                chat_id=user_id,
                photo=photo_file,
                caption="✅ Готово! 🎞️"
            )
        
        # Удаляем временные файлы
        for file_path in [photo_path, output]:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logging.warning(f"⚠️ Не удалось удалить файл {file_path}: {e}")
        
        return True
    except Exception as e:
        logging.error(f"❌ Ошибка: {str(e)}")
        await message.answer(f"❌ Ошибка: {str(e)}")
        return False

# ========== ХЕНДЛЕРЫ ==========
user_data = {}

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer(
        "📱 Привет! Я делаю стильные сторис!\n\n"
        "Просто отправь мне РЕПОСТ любого поста с фото и текстом.\n"
        "Дизайн автоматически подстроится под твой контент!"
    )
    user_data[message.from_user.id] = {"step": "waiting_photo"}

@dp.message_handler(content_types=['text', 'photo', 'document'])
async def handle_forward(message: types.Message):
    user_id = message.from_user.id
    is_forward = message.forward_from or message.forward_from_chat or message.forward_date
    
    if not is_forward:
        return
    
    await message.answer("📥 Обнаружен репост! Обрабатываю...")
    
    text = message.text or message.caption or ""
    photo_file_path = None
    
    if message.photo:
        file = await bot.get_file(message.photo[-1].file_id)
        photo_file_path = f"temp_{user_id}_forward.jpg"
        await bot.download_file(file.file_path, photo_file_path)
    elif message.document and message.document.mime_type and message.document.mime_type.startswith('image/'):
        file = await bot.get_file(message.document.file_id)
        photo_file_path = f"temp_{user_id}_forward.jpg"
        await bot.download_file(file.file_path, photo_file_path)
    else:
        await message.answer("❌ В репосте нет фото!")
        return
    
    text = text.replace("**Текст отсутствует**", "").strip()
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith('Подписаться') and not line.startswith('@') and not line.startswith('#'):
            clean_lines.append(line)
    text = '\n'.join(clean_lines)
    
    title, content = parse_text(text)
    
    if not title and text:
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        if sentences:
            title = sentences[0]
            content = ". ".join(sentences[1:])
    
    if not title:
        title = "📌 Заголовок"
    if not content:
        content = "Текст отсутствует"
    
    await message.answer(f"⏳ Генерирую стильную сторис...")
    await process_story(user_id, photo_file_path, title, content, message)
    
    if user_id in user_data:
        del user_data[user_id]

# ========== РУЧНОЙ ВВОД ==========
@dp.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    if message.forward_from or message.forward_from_chat or message.forward_date:
        return
    
    caption = message.caption or ""
    if caption:
        title, content = parse_text(caption)
        file = await bot.get_file(message.photo[-1].file_id)
        file_path = f"temp_{user_id}.jpg"
        await bot.download_file(file.file_path, file_path)
        await message.answer("⏳ Генерирую...")
        await process_story(user_id, file_path, title, content, message)
        return
    
    if user_id not in user_data:
        user_data[user_id] = {"step": "waiting_photo"}
    
    file = await bot.get_file(message.photo[-1].file_id)
    file_path = f"temp_{user_id}.jpg"
    await bot.download_file(file.file_path, file_path)
    user_data[user_id]["photo"] = file_path
    user_data[user_id]["step"] = "waiting_title"
    await message.answer("✅ Фото принято! Теперь отправь ЗАГОЛОВОК.")

@dp.message_handler(content_types=['text'])
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    if message.forward_from or message.forward_from_chat or message.forward_date:
        return
    if message.text.startswith('/'):
        return
    if user_id not in user_data:
        await start(message)
        return
    
    step = user_data[user_id].get("step", "")
    if step == "waiting_title":
        user_data[user_id]["title"] = message.text
        user_data[user_id]["step"] = "waiting_content"
        await message.answer("✅ Заголовок сохранен! Теперь отправь ОСНОВНОЙ ТЕКСТ.")
    elif step == "waiting_content":
        user_data[user_id]["content"] = message.text
        user_data[user_id]["step"] = "done"
        await message.answer("⏳ Генерирую...")
        photo_path = user_data[user_id]["photo"]
        title = user_data[user_id]["title"]
        content = user_data[user_id]["content"]
        await process_story(user_id, photo_path, title, content, message)
        if user_id in user_data:
            del user_data[user_id]

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    from aiogram import executor
    
    print("🚀 Бот запускается в новом стиле...")
    
    async def on_startup(dp):
        try:
            await bot.delete_webhook()
            print("✅ Вебхук удален")
        except Exception as e:
            print(f"⚠️ Ошибка удаления вебхука: {e}")
    
    try:
        executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
    except Exception as e:
        print(f"❌ Ошибка при запуске: {e}")
