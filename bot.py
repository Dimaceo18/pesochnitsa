import os
import logging
import re
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputFile
from aiogram.contrib.middlewares.logging import LoggingMiddleware
import textwrap

# ========== КОНФИГ ==========
API_TOKEN = os.getenv("BOT_TOKEN")

if not API_TOKEN:
    raise ValueError("❌ Токен не найден! Создай переменную BOT_TOKEN в настройках Render.")

# Шрифты
FONT_PATH_BOLD = "Inter-Bold.ttf"
FONT_PATH_REG = "Inter-Regular.ttf"

# Фоновое изображение
BACKGROUND_IMAGE = "fon.png"

# Размеры сторис
W, H = 1080, 1920

# Отступы
SIDE_MARGIN = 40
GAP_BETWEEN_TITLE_AND_TEXT = 25  # Расстояние между заголовком и текстом
MAX_PHOTO_HEIGHT = 700  # МАКСИМАЛЬНАЯ ВЫСОТА ФОТО (чтобы осталось место для текста)

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
            content = '\n'.join(lines[1:])
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

# ========== ФОРМАТИРОВАНИЕ ТЕКСТА В АБЗАЦЫ ==========
def format_paragraphs(text: str) -> list:
    if not text:
        return []
    
    sentences = re.split(r'(?<=[.!?])\s+(?=[А-ЯA-Z])', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    paragraphs = []
    current_para = []
    
    for sent in sentences:
        current_para.append(sent)
        if len(current_para) >= 3:
            paragraphs.append(". ".join(current_para))
            current_para = []
    
    if current_para:
        paragraphs.append(". ".join(current_para))
    
    return paragraphs

# ========== РЕТРО-ЭФФЕКТ ==========
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
    logging.info(f"🖼 Генерация сторис:")
    logging.info(f"   Заголовок: {title[:100] if title else 'ПУСТО'}...")
    logging.info(f"   Контент: {content[:100] if content else 'ПУСТО'}...")
    
    # ============================================================
    # ШАГ 1: СОЗДАЕМ ХОЛСТ С ФОНОМ
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
    # ШАГ 2: ВСТАВЛЯЕМ ФОТО (ОГРАНИЧЕННОЙ ВЫСОТЫ)
    # ============================================================
    photo = Image.open(photo_path).convert("RGB")
    photo_ratio = photo.width / photo.height
    PHOTO_HEIGHT = int(W / photo_ratio)
    
    # ОГРАНИЧИВАЕМ ВЫСОТУ ФОТО, чтобы осталось место для текста
    if PHOTO_HEIGHT > MAX_PHOTO_HEIGHT:
        PHOTO_HEIGHT = MAX_PHOTO_HEIGHT
        # Обрезаем фото по центру по высоте
        crop_height = int(photo.width / (W / PHOTO_HEIGHT))
        if crop_height < photo.height:
            top = (photo.height - crop_height) // 2
            photo = photo.crop((0, top, photo.width, top + crop_height))
    
    photo = photo.resize((W, PHOTO_HEIGHT), Image.Resampling.LANCZOS)
    photo = apply_retro_effect(photo)
    
    # Обводка снизу
    border_size = 8
    bordered_photo = Image.new('RGB', (W, PHOTO_HEIGHT + border_size), color='white')
    bordered_photo.paste(photo, (0, 0))
    
    canvas.paste(bordered_photo, (0, 0))
    
    # ============================================================
    # ШАГ 3: ЗАГРУЖАЕМ ШРИФТЫ
    # ============================================================
    try:
        font_bold = ImageFont.truetype(FONT_PATH_BOLD, 60)
    except:
        font_bold = ImageFont.load_default()
    
    try:
        font_reg = ImageFont.truetype(FONT_PATH_REG, 40)
    except:
        font_reg = ImageFont.load_default()
    
    # ============================================================
    # ШАГ 4: РИСУЕМ ЗАГОЛОВОК
    # ============================================================
    current_y = PHOTO_HEIGHT + border_size + 25
    
    if title:
        MAX_TITLE_WIDTH = W - (SIDE_MARGIN * 2)
        
        # Подбираем размер шрифта
        title_font = None
        title_lines = []
        for size in range(70, 36, -2):
            try:
                font = ImageFont.truetype(FONT_PATH_BOLD, size)
            except:
                font = ImageFont.load_default()
            
            words = title.upper().split()
            lines = []
            current_line = []
            for word in words:
                test_line = ' '.join(current_line + [word])
                bbox = draw.textbbox((0, 0), test_line, font=font)
                if bbox[2] - bbox[0] <= MAX_TITLE_WIDTH:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]
            if current_line:
                lines.append(' '.join(current_line))
            
            if 2 <= len(lines) <= 3:
                title_font = font
                title_lines = lines
                break
        
        if title_font is None:
            try:
                title_font = ImageFont.truetype(FONT_PATH_BOLD, 36)
            except:
                title_font = ImageFont.load_default()
            words = title.upper().split()
            title_lines = []
            current_line = []
            for word in words:
                test_line = ' '.join(current_line + [word])
                bbox = draw.textbbox((0, 0), test_line, font=title_font)
                if bbox[2] - bbox[0] <= MAX_TITLE_WIDTH:
                    current_line.append(word)
                else:
                    if current_line:
                        title_lines.append(' '.join(current_line))
                    current_line = [word]
            if current_line:
                title_lines.append(' '.join(current_line))
        
        title_text = "\n".join(title_lines)
        
        # Рисуем заголовок
        draw.text((SIDE_MARGIN, current_y), title_text, font=title_font, fill='white')
        
        # Вычисляем конец заголовка
        single_bbox = draw.textbbox((0, 0), "A", font=title_font)
        single_h = single_bbox[3] - single_bbox[1]
        title_total_h = len(title_lines) * single_h + 6 * (len(title_lines) - 1)
        title_end_y = current_y + title_total_h
        
        # ============================================================
        # ШАГ 5: ОТСТУП 25px МЕЖДУ ЗАГОЛОВКОМ И ТЕКСТОМ
        # ============================================================
        current_y = title_end_y + GAP_BETWEEN_TITLE_AND_TEXT
        
        logging.info(f"📐 Позиции:")
        logging.info(f"   Конец заголовка: {title_end_y}")
        logging.info(f"   Начало текста: {current_y} (отступ {GAP_BETWEEN_TITLE_AND_TEXT}px)")
    
    # ============================================================
    # ШАГ 6: РИСУЕМ ОСНОВНОЙ ТЕКСТ
    # ============================================================
    if content and content != "Текст отсутствует":
        logging.info(f"📄 Рисуем основной текст, длина: {len(content)} символов")
        
        paragraphs = format_paragraphs(content)
        logging.info(f"   Разбито на {len(paragraphs)} абзацев")
        
        MAX_TEXT_W = W - (SIDE_MARGIN * 2)
        MAX_TEXT_H = H - current_y - 100
        CONTENT_LINE_SPACING = 5
        
        # Подбираем размер шрифта
        content_font = None
        wrapped_paragraphs = []
        single_h = 0
        
        for size in range(40, 22, -2):
            try:
                font = ImageFont.truetype(FONT_PATH_REG, size)
            except:
                font = ImageFont.load_default()
            
            test_wrapped = []
            total_height = 0
            single_bbox = draw.textbbox((0, 0), "A", font=font)
            single_h = single_bbox[3] - single_bbox[1]
            
            for para in paragraphs:
                chars_per_line = int(MAX_TEXT_W / (size * 0.6))
                wrapped = textwrap.wrap(para, width=chars_per_line)
                if not wrapped:
                    wrapped = [para]
                test_wrapped.append(wrapped)
                
                para_height = len(wrapped) * single_h + CONTENT_LINE_SPACING * (len(wrapped) - 1)
                total_height += para_height
                total_height += 15
            
            if total_height <= MAX_TEXT_H:
                content_font = font
                wrapped_paragraphs = test_wrapped
                break
        
        if content_font is None:
            try:
                content_font = ImageFont.truetype(FONT_PATH_REG, 22)
            except:
                content_font = ImageFont.load_default()
            single_bbox = draw.textbbox((0, 0), "A", font=content_font)
            single_h = single_bbox[3] - single_bbox[1]
            wrapped_paragraphs = []
            for para in paragraphs:
                chars_per_line = int(MAX_TEXT_W / (22 * 0.6))
                wrapped = textwrap.wrap(para, width=chars_per_line)
                if not wrapped:
                    wrapped = [para]
                wrapped_paragraphs.append(wrapped)
        
        # Рисуем текст
        pos_y = current_y
        for para_lines in wrapped_paragraphs:
            for line in para_lines:
                draw.text((SIDE_MARGIN, pos_y), line, font=content_font, fill='white')
                pos_y += single_h + CONTENT_LINE_SPACING
            pos_y += 15
        
        logging.info(f"✅ Основной текст нарисован")
    else:
        logging.warning(f"⚠️ Основной текст ПУСТОЙ")
    
    # ============================================================
    # ШАГ 7: РИСУЕМ НИЖНИЙ БЛОК
    # ============================================================
    GRAY_BLOCK_H = 60
    GRAY_BLOCK_Y = H - GRAY_BLOCK_H
    
    draw.rectangle([0, GRAY_BLOCK_Y, W, H], fill='#2A2A2A')
    
    try:
        footer_font = ImageFont.truetype(FONT_PATH_BOLD, 28)
    except:
        footer_font = ImageFont.load_default()
    
    footer_text = "ВСЕГДА СВЕЖИЕ НОВОСТИ"
    footer_bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
    footer_w = footer_bbox[2] - footer_bbox[0]
    footer_h = footer_bbox[3] - footer_bbox[1]
    
    footer_x = (W - footer_w) // 2
    footer_y = GRAY_BLOCK_Y + (GRAY_BLOCK_H - footer_h) // 2
    
    draw.text((footer_x, footer_y), footer_text, font=footer_font, fill='white')
    
    # ============================================================
    # ШАГ 8: СОХРАНЯЕМ
    # ============================================================
    output_path = "output_story.png"
    canvas.save(output_path, "PNG")
    return output_path

# ========== ОБЩАЯ ФУНКЦИЯ ==========
async def process_story(user_id: int, photo_path: str, title: str, content: str, message: types.Message):
    try:
        output = await generate_story(photo_path, title, content)
        await bot.send_photo(
            chat_id=user_id,
            photo=InputFile(output),
            caption="✅ Готово! 🎞️"
        )
        if os.path.exists(photo_path):
            os.remove(photo_path)
        if os.path.exists(output):
            os.remove(output)
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
        "📱 Привет! Я делаю ретро-сторис!\n\n"
        "Просто отправь мне РЕПОСТ любого поста с фото и текстом."
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
    
    # Очищаем текст
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
        title = sentences[0]
        content = ". ".join(sentences[1:])
    
    if not title:
        title = "📌 Заголовок"
    if not content:
        content = "Текст отсутствует"
    
    await message.answer(f"⏳ Генерирую ретро-сторис...")
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
    import asyncio
    from aiogram import executor
    
    print("🚀 Бот запускается...")
    
    async def delete_webhook():
        try:
            await bot.delete_webhook()
            print("✅ Вебхук удален")
        except Exception as e:
            print(f"⚠️ Ошибка удаления вебхука: {e}")
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(delete_webhook())
    
    try:
        executor.start_polling(dp, skip_updates=True)
    except Exception as e:
        print(f"❌ Ошибка при запуске: {e}")
