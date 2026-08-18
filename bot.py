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

# Шрифты Inter
FONT_PATH_BOLD = "Inter-Bold.ttf"
FONT_PATH_REG = "Inter-Regular.ttf"

# Фоновое изображение
BACKGROUND_IMAGE = "fon.png"

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
    
    logging.info(f"📝 Парсинг текста:")
    logging.info(f"   Заголовок ({len(title)} симв): {title[:100]}...")
    logging.info(f"   Контент ({len(content)} симв): {content[:100] if content else 'ПУСТО'}...")
    
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
    W, H = 1080, 1920
    
    logging.info(f"🖼 Генерация сторис:")
    logging.info(f"   Заголовок: {title[:100] if title else 'ПУСТО'}...")
    logging.info(f"   Контент: {content[:100] if content else 'ПУСТО'}...")
    
    # 1. ФОНОВОЕ ИЗОБРАЖЕНИЕ
    try:
        background = Image.open(BACKGROUND_IMAGE).convert("RGB")
        background = background.resize((W, H), Image.Resampling.LANCZOS)
        canvas = background
        logging.info(f"✅ Фоновое изображение загружено: {BACKGROUND_IMAGE}")
    except Exception as e:
        logging.warning(f"⚠️ Не удалось загрузить фон: {e}. Использую черный фон.")
        canvas = Image.new('RGB', (W, H), color='black')
    
    draw = ImageDraw.Draw(canvas)
    
    # 2. ФОТО
    PHOTO_WIDTH = W
    PHOTO_X = 0
    
    photo = Image.open(photo_path).convert("RGB")
    photo_ratio = photo.width / photo.height
    PHOTO_HEIGHT = int(PHOTO_WIDTH / photo_ratio)
    
    if PHOTO_HEIGHT > 960:
        PHOTO_HEIGHT = 960
        photo = photo.crop((0, 0, photo.width, int(photo.width / (PHOTO_WIDTH / PHOTO_HEIGHT))))
    
    photo = photo.resize((PHOTO_WIDTH, PHOTO_HEIGHT), Image.Resampling.LANCZOS)
    photo = apply_retro_effect(photo)
    
    border_size = 8
    bordered_photo = Image.new('RGB', (PHOTO_WIDTH, PHOTO_HEIGHT + border_size), color='white')
    bordered_photo.paste(photo, (0, 0))
    
    PHOTO_Y = 0
    canvas.paste(bordered_photo, (PHOTO_X, PHOTO_Y))
    
    # 3. ЗАГРУЗКА ШРИФТОВ
    try:
        font_bold = ImageFont.truetype(FONT_PATH_BOLD, 60)
    except:
        font_bold = ImageFont.load_default()
        logging.warning(f"Шрифт {FONT_PATH_BOLD} не найден")
    
    try:
        font_reg = ImageFont.truetype(FONT_PATH_REG, 40)
    except:
        font_reg = ImageFont.load_default()
        logging.warning(f"Шрифт {FONT_PATH_REG} не найден")
    
    # 4. КОНСТАНТЫ
    SIDE_MARGIN = 40
    TITLE_LINE_SPACING = 6
    GAP_BETWEEN_PHOTO_AND_TITLE = 30
    
    # ЖЕСТКИЕ ОТСТУПЫ
    LINE_THICKNESS = 2
    SPACE_BEFORE_LINE = 10  # 10px от заголовка до линии
    SPACE_AFTER_LINE = 10   # 10px от линии до текста
    
    # 5. ЗАГОЛОВОК
    title_y_position = PHOTO_HEIGHT + border_size + GAP_BETWEEN_PHOTO_AND_TITLE
    
    if title:
        MAX_TITLE_WIDTH = W - (SIDE_MARGIN * 2)
        
        def fit_title(text, max_width):
            for size in range(70, 36, -2):
                try:
                    font = ImageFont.truetype(FONT_PATH_BOLD, size)
                except:
                    font = ImageFont.load_default()
                
                words = text.upper().split()
                lines = []
                current_line = []
                
                for word in words:
                    test_line = ' '.join(current_line + [word])
                    bbox = draw.textbbox((0, 0), test_line, font=font)
                    line_width = bbox[2] - bbox[0]
                    
                    if line_width <= max_width:
                        current_line.append(word)
                    else:
                        if current_line:
                            lines.append(' '.join(current_line))
                        current_line = [word]
                
                if current_line:
                    lines.append(' '.join(current_line))
                
                if 2 <= len(lines) <= 3:
                    return font, lines
                if len(lines) > 3:
                    continue
                if len(lines) <= 2:
                    return font, lines
            
            try:
                font = ImageFont.truetype(FONT_PATH_BOLD, 36)
            except:
                font = ImageFont.load_default()
            words = text.upper().split()
            lines = []
            current_line = []
            for word in words:
                test_line = ' '.join(current_line + [word])
                bbox = draw.textbbox((0, 0), test_line, font=font)
                if bbox[2] - bbox[0] <= max_width:
                    current_line.append(word)
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]
            if current_line:
                lines.append(' '.join(current_line))
            return font, lines
        
        title_font, title_lines = fit_title(title, MAX_TITLE_WIDTH)
        title_text = "\n".join(title_lines)
        
        title_x = SIDE_MARGIN
        title_y = title_y_position
        
        # РИСУЕМ ЗАГОЛОВОК
        draw.text((title_x, title_y), title_text, font=title_font, fill='white')
        
        # Вычисляем конец заголовка (нижняя граница)
        single_bbox = draw.textbbox((0, 0), "A", font=title_font)
        single_h = single_bbox[3] - single_bbox[1]
        title_total_h = len(title_lines) * single_h + TITLE_LINE_SPACING * (len(title_lines) - 1)
        title_end_y = title_y + title_total_h
        
        # ===== РАЗДЕЛИТЕЛЬ С ЖЕСТКИМИ ОТСТУПАМИ =====
        # 1. Отступаем 10px от заголовка
        line_y = title_end_y + SPACE_BEFORE_LINE
        
        # 2. Рисуем линию
        LINE_WIDTH = W - (SIDE_MARGIN * 2)
        LINE_X1 = SIDE_MARGIN
        LINE_X2 = SIDE_MARGIN + LINE_WIDTH
        
        draw.rectangle([LINE_X1, line_y, LINE_X2, line_y + LINE_THICKNESS], fill='white')
        
        # 3. Отступаем 10px после линии
        text_start_y = line_y + LINE_THICKNESS + SPACE_AFTER_LINE
        
        # Сохраняем позицию для текста
        title_y_position = text_start_y
        
        logging.info(f"📐 Отступы:")
        logging.info(f"   Конец заголовка: {title_end_y}")
        logging.info(f"   Линия на: {line_y}")
        logging.info(f"   Начало текста: {text_start_y}")
    
    # 6. ОСНОВНОЙ ТЕКСТ
    if content and content != "Текст отсутствует":
        logging.info(f"📄 Рисуем основной текст, длина: {len(content)} символов")
        
        paragraphs = format_paragraphs(content)
        logging.info(f"   Разбито на {len(paragraphs)} абзацев")
        
        MAX_TEXT_W = W - (SIDE_MARGIN * 2)
        MAX_TEXT_H = H - title_y_position - 100
        
        CONTENT_LINE_SPACING = 5
        
        def fit_content(paragraphs_list, max_w, max_h):
            for size in range(40, 22, -2):
                try:
                    font = ImageFont.truetype(FONT_PATH_REG, size)
                except:
                    font = ImageFont.load_default()
                
                wrapped_paragraphs = []
                total_height = 0
                
                single_bbox = draw.textbbox((0, 0), "A", font=font)
                single_h = single_bbox[3] - single_bbox[1]
                
                for para in paragraphs_list:
                    chars_per_line = int(max_w / (size * 0.6))
                    wrapped = textwrap.wrap(para, width=chars_per_line)
                    if not wrapped:
                        wrapped = [para]
                    wrapped_paragraphs.append(wrapped)
                    
                    para_height = len(wrapped) * single_h + CONTENT_LINE_SPACING * (len(wrapped) - 1)
                    total_height += para_height
                    total_height += 15
                
                if total_height <= max_h:
                    return font, wrapped_paragraphs, single_h
            
            try:
                font = ImageFont.truetype(FONT_PATH_REG, 22)
            except:
                font = ImageFont.load_default()
            
            single_bbox = draw.textbbox((0, 0), "A", font=font)
            single_h = single_bbox[3] - single_bbox[1]
            
            wrapped_paragraphs = []
            for para in paragraphs_list:
                chars_per_line = int(max_w / (22 * 0.6))
                wrapped = textwrap.wrap(para, width=chars_per_line)
                if not wrapped:
                    wrapped = [para]
                wrapped_paragraphs.append(wrapped)
            return font, wrapped_paragraphs, single_h
        
        content_font, wrapped_paragraphs, single_h = fit_content(paragraphs, MAX_TEXT_W, MAX_TEXT_H)
        
        current_y = title_y_position
        
        for para_lines in wrapped_paragraphs:
            for line in para_lines:
                line_x = SIDE_MARGIN
                draw.text((line_x, current_y), line, font=content_font, fill='white')
                current_y += single_h + CONTENT_LINE_SPACING
            
            current_y += 15
        
        logging.info(f"✅ Основной текст нарисован")
    else:
        logging.warning(f"⚠️ Основной текст ПУСТОЙ или равен 'Текст отсутствует'")
    
    # 7. ТЕМНО-СЕРЫЙ БЛОК ВНИЗУ
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
    
    output_path = "output_story.png"
    canvas.save(output_path, "PNG")
    return output_path

# ========== ОБЩАЯ ФУНКЦИЯ ==========
async def process_story(user_id: int, photo_path: str, title: str, content: str, message: types.Message):
    try:
        logging.info(f"🔍 process_story вызван:")
        logging.info(f"   title: {title[:50] if title else 'ПУСТО'}...")
        logging.info(f"   content: {content[:50] if content else 'ПУСТО'}...")
        
        output = await generate_story(photo_path, title, content)
        await bot.send_photo(
            chat_id=user_id,
            photo=InputFile(output),
            caption="✅ Готово! 🎞️ Ретро-эффект усилен"
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
        "📱 Привет! Я делаю сторис в ретро-стиле!\n\n"
        "🎞️ К каждому фото применяется усиленный винтажный эффект:\n"
        "• Сильная зернистость\n"
        "• Теплый сепия-оттенок\n"
        "• Пленочный шум\n\n"
        "Просто отправь мне РЕПОСТ любого поста, и я:\n"
        "1️⃣ Обработаю фото в ретро-стиле\n"
        "2️⃣ Первый абзац сделаю заголовком\n"
        "3️⃣ Добавлю разделитель\n"
        "4️⃣ Остальной текст размещу ниже\n\n"
        "Или отправь вручную: ФОТО → ЗАГОЛОВОК → ТЕКСТ"
    )
    user_data[message.from_user.id] = {"step": "waiting_photo"}

# ========== ОБРАБОТКА РЕПОСТОВ ==========
@dp.message_handler(content_types=['text', 'photo', 'document'])
async def handle_forward(message: types.Message):
    user_id = message.from_user.id
    
    is_forward = message.forward_from or message.forward_from_chat or message.forward_date
    
    if not is_forward:
        return
    
    await message.answer("📥 Обнаружен репост! Обрабатываю с усиленным ретро-эффектом...")
    
    text = message.text or message.caption or ""
    logging.info(f"📥 Исходный текст репоста ({len(text)} симв): {text[:200]}...")
    
    photo_file_path = None
    
    if message.photo:
        file = await bot.get_file(message.photo[-1].file_id)
        photo_file_path = f"temp_{user_id}_forward.jpg"
        await bot.download_file(file.file_path, photo_file_path)
        logging.info(f"📸 Фото найдено в message.photo")
    elif message.document and message.document.mime_type and message.document.mime_type.startswith('image/'):
        file = await bot.get_file(message.document.file_id)
        photo_file_path = f"temp_{user_id}_forward.jpg"
        await bot.download_file(file.file_path, photo_file_path)
        logging.info(f"📸 Фото найдено в message.document")
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
    logging.info(f"🧹 Очищенный текст ({len(text)} симв): {text[:200]}...")
    
    title, content = parse_text(text)
    
    if not title and text:
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        title = sentences[0]
        content = ". ".join(sentences[1:])
        logging.info(f"🔄 Заголовок из первого предложения: {title[:50]}...")
    
    if not title:
        title = "📌 Заголовок"
    if not content:
        content = "Текст отсутствует"
    
    logging.info(f"📝 ИТОГО:")
    logging.info(f"   Заголовок: {title[:100]}...")
    logging.info(f"   Контент: {content[:100] if content else 'ПУСТО'}...")
    
    await message.answer(f"📝 Заголовок: {title[:50]}...\n\n🎞️ Применяю усиленный ретро-эффект...")
    
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
        
        await message.answer("🎞️ Обрабатываю с усиленным ретро-эффектом...")
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

        await message.answer("🎞️ Генерирую ретро-сторис...")

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
    
    print("🚀 Бот запускается с усиленным ретро-эффектом...")
    
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
