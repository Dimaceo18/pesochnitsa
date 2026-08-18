import os
import logging
import re
from PIL import Image, ImageDraw, ImageFont
from aiogram import Bot, Dispatcher, types
from aiogram.types import InputFile
from aiogram.contrib.middlewares.logging import LoggingMiddleware
import textwrap

# ========== КОНФИГ ==========
API_TOKEN = os.getenv("BOT_TOKEN")

if not API_TOKEN:
    raise ValueError("❌ Токен не найден! Создай переменную BOT_TOKEN в настройках Render.")

# Шрифты Inter (один и тот же шрифт, но разные начертания)
FONT_PATH_BOLD = "Inter-Bold.ttf"      # Жирный для заголовка
FONT_PATH_REG = "Inter-Regular.ttf"    # Обычный для текста

# ========== НАСТРОЙКА ЛОГОВ ==========
logging.basicConfig(level=logging.INFO)

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# ========== ПАРСИНГ ТЕКСТА ==========
def parse_text(text: str) -> tuple:
    """
    Разделяет текст на заголовок (первый абзац) и основной текст (всё остальное).
    """
    if not text:
        return "", ""
    
    text = text.strip()
    
    # Разбиваем на абзацы (по двойному переводу строки)
    paragraphs = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    if not paragraphs:
        return "", ""
    
    # Первый абзац - заголовок
    title = paragraphs[0]
    
    # Все остальные абзацы - основной текст (сохраняем структуру)
    content = "\n\n".join(paragraphs[1:]) if len(paragraphs) > 1 else ""
    
    # Если заголовок слишком длинный (> 150 символов), обрезаем
    if len(title) > 150:
        match = re.search(r'[.!?]\s+', title)
        if match:
            title = title[:match.end()].strip()
            remaining = title[match.end():].strip()
            if remaining:
                content = remaining + "\n\n" + content if content else remaining
    
    return title, content

# ========== ГЕНЕРАЦИЯ СТОРИС ==========
async def generate_story(photo_path: str, title: str, content: str) -> str:
    W, H = 1080, 1920  # 9:16
    
    # 1. БЕЛЫЙ ФОН
    canvas = Image.new('RGB', (W, H), color='white')
    draw = ImageDraw.Draw(canvas)
    
    # 2. ФОТО (квадрат с черной обводкой)
    PHOTO_SIZE = int(W * 0.8)
    PHOTO_X = (W - PHOTO_SIZE) // 2
    PHOTO_Y = 60
    
    photo = Image.open(photo_path).convert("RGB")
    min_side = min(photo.width, photo.height)
    left = (photo.width - min_side) // 2
    top = (photo.height - min_side) // 2
    photo = photo.crop((left, top, left + min_side, top + min_side))
    photo = photo.resize((PHOTO_SIZE, PHOTO_SIZE), Image.Resampling.LANCZOS)
    
    border_size = 8
    bordered_photo = Image.new('RGB', (PHOTO_SIZE + border_size * 2, PHOTO_SIZE + border_size * 2), color='black')
    bordered_photo.paste(photo, (border_size, border_size))
    
    canvas.paste(bordered_photo, (PHOTO_X - border_size, PHOTO_Y - border_size))
    
    # 3. ЗАГРУЗКА ШРИФТОВ
    try:
        font_bold = ImageFont.truetype(FONT_PATH_BOLD, 60)
    except:
        font_bold = ImageFont.load_default()
        logging.warning(f"Шрифт {FONT_PATH_BOLD} не найден, использую дефолтный")
    
    try:
        font_reg = ImageFont.truetype(FONT_PATH_REG, 40)
    except:
        font_reg = ImageFont.load_default()
        logging.warning(f"Шрифт {FONT_PATH_REG} не найден, использую дефолтный")
    
    # 4. ЗАГОЛОВОК (жирный, ВСЕ БОЛЬШИЕ БУКВЫ, 2-3 строки)
    if title:
        MAX_TITLE_WIDTH = W - 80
        
        def fit_title(text, max_width):
            # Пробуем размер от 70 до 36
            for size in range(70, 36, -2):
                try:
                    font = ImageFont.truetype(FONT_PATH_BOLD, size)
                except:
                    font = ImageFont.load_default()
                
                # Разбиваем на строки по словам
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
                
                # Проверяем количество строк
                if 2 <= len(lines) <= 3:
                    return font, lines
                if len(lines) > 3:
                    continue
                if len(lines) <= 2:
                    return font, lines
            
            # Если ничего не подошло
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
        title_text = "\n".join(title_lines)  # Уже в верхнем регистре
        
        title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
        title_w = title_bbox[2] - title_bbox[0]
        title_h = title_bbox[3] - title_bbox[1]
        
        title_x = (W - title_w) // 2
        title_y = PHOTO_Y + PHOTO_SIZE + border_size * 2 + 30
        
        draw.text((title_x, title_y), title_text, font=title_font, fill='black')
        
        # 5. ОСНОВНОЙ ТЕКСТ (обычный шрифт, с сохранением абзацев)
        if content:
            TEXT_START_Y = title_y + title_h + 25
            MAX_TEXT_H = H - TEXT_START_Y - 100
            MAX_TEXT_W = W - 80
            
            def fit_content(text, max_w, max_h):
                # Пробуем размер от 40 до 22
                for size in range(40, 22, -2):
                    try:
                        font = ImageFont.truetype(FONT_PATH_REG, size)
                    except:
                        font = ImageFont.load_default()
                    
                    # Разбиваем на абзацы
                    paragraphs = text.split('\n\n')
                    wrapped_paragraphs = []
                    total_height = 0
                    
                    for para in paragraphs:
                        # Разбиваем абзац на строки
                        chars_per_line = int(max_w / (size * 0.6))
                        wrapped = textwrap.wrap(para, width=chars_per_line)
                        if not wrapped:
                            wrapped = [para]
                        wrapped_paragraphs.append(wrapped)
                        
                        # Считаем высоту
                        for line in wrapped:
                            bbox = draw.textbbox((0, 0), line, font=font)
                            total_height += bbox[3] - bbox[1]
                        # Добавляем отступ между абзацами
                        if len(paragraphs) > 1:
                            total_height += 15
                    
                    if total_height <= max_h:
                        return font, wrapped_paragraphs
                
                # Если ничего не подошло
                try:
                    font = ImageFont.truetype(FONT_PATH_REG, 22)
                except:
                    font = ImageFont.load_default()
                paragraphs = text.split('\n\n')
                wrapped_paragraphs = []
                for para in paragraphs:
                    chars_per_line = int(max_w / (22 * 0.6))
                    wrapped = textwrap.wrap(para, width=chars_per_line)
                    if not wrapped:
                        wrapped = [para]
                    wrapped_paragraphs.append(wrapped)
                return font, wrapped_paragraphs
            
            content_font, wrapped_paragraphs = fit_content(content, MAX_TEXT_W, MAX_TEXT_H)
            
            # Рисуем текст с сохранением абзацев
            current_y = TEXT_START_Y
            total_height = 0
            
            # Сначала считаем общую высоту для центрирования
            for para_idx, para_lines in enumerate(wrapped_paragraphs):
                for line in para_lines:
                    bbox = draw.textbbox((0, 0), line, font=content_font)
                    total_height += bbox[3] - bbox[1]
                if para_idx < len(wrapped_paragraphs) - 1:
                    total_height += 15  # Отступ между абзацами
            
            # Центрируем текст по вертикали
            start_y = TEXT_START_Y + (MAX_TEXT_H - total_height) // 2
            
            # Рисуем
            current_y = start_y
            for para_idx, para_lines in enumerate(wrapped_paragraphs):
                for line in para_lines:
                    bbox = draw.textbbox((0, 0), line, font=content_font)
                    line_width = bbox[2] - bbox[0]
                    line_height = bbox[3] - bbox[1]
                    
                    line_x = (W - line_width) // 2
                    draw.text((line_x, current_y), line, font=content_font, fill='#333333')
                    current_y += line_height
                
                # Отступ между абзацами
                if para_idx < len(wrapped_paragraphs) - 1:
                    current_y += 15
    
    # 6. ЖЕЛТЫЙ ПРЯМОУГОЛЬНИК ВНИЗУ
    YELLOW_BLOCK_H = 60
    YELLOW_BLOCK_Y = H - YELLOW_BLOCK_H
    
    draw.rectangle(
        [0, YELLOW_BLOCK_Y, W, H],
        fill='#FFD700'
    )
    
    try:
        footer_font = ImageFont.truetype(FONT_PATH_BOLD, 28)
    except:
        footer_font = ImageFont.load_default()
    
    footer_text = "ВСЕГДА СВЕЖИЕ НОВОСТИ"
    footer_bbox = draw.textbbox((0, 0), footer_text, font=footer_font)
    footer_w = footer_bbox[2] - footer_bbox[0]
    footer_h = footer_bbox[3] - footer_bbox[1]
    
    footer_x = (W - footer_w) // 2
    footer_y = YELLOW_BLOCK_Y + (YELLOW_BLOCK_H - footer_h) // 2
    
    draw.text((footer_x, footer_y), footer_text, font=footer_font, fill='black')
    
    output_path = "output_story.png"
    canvas.save(output_path, "PNG")
    return output_path

# ========== ОБЩАЯ ФУНКЦИЯ ДЛЯ ОБРАБОТКИ ==========
async def process_story(user_id: int, photo_path: str, title: str, content: str, message: types.Message):
    try:
        output = await generate_story(photo_path, title, content)
        await bot.send_photo(
            chat_id=user_id,
            photo=InputFile(output),
            caption="✅ Готово! Твоя сторис в новом дизайне."
        )
        if os.path.exists(photo_path):
            os.remove(photo_path)
        if os.path.exists(output):
            os.remove(output)
        return True
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")
        return False

# ========== ХЕНДЛЕРЫ ==========
user_data = {}

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer(
        "📱 Привет! Я делаю сторис в белом стиле!\n\n"
        "Просто отправь мне РЕПОСТ любого поста из Telegram, и я:\n"
        "1️⃣ Возьму фото и сделаю его квадратом с черной обводкой\n"
        "2️⃣ Первый абзац сделаю заголовком (жирный, ВСЕ БОЛЬШИЕ)\n"
        "3️⃣ Остальной текст сохраню с абзацами\n"
        "4️⃣ Добавлю желтый блок внизу\n\n"
        "Или отправь данные вручную:\n"
        "1. ФОТО\n"
        "2. ЗАГОЛОВОК (текстом)\n"
        "3. ОСНОВНОЙ ТЕКСТ (текстом)"
    )
    user_data[message.from_user.id] = {"step": "waiting_photo"}

# ========== ОБРАБОТКА РЕПОСТОВ ==========
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
        await message.answer("❌ В репосте нет фото! Пожалуйста, отправь репост с изображением.")
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
        title = ". ".join(sentences[:2])
        content = ". ".join(sentences[2:])
    
    if not title:
        title = "📌 Заголовок"
    if not content:
        content = "Текст отсутствует"
    
    if len(title) > 150:
        last_dot = title.rfind('.', 0, 150)
        if last_dot > 0:
            content = title[last_dot+1:].strip() + "\n\n" + content if content else title[last_dot+1:].strip()
            title = title[:last_dot+1].strip()
    
    await message.answer(f"📝 Заголовок: {title[:50]}...\n\n⏳ Генерирую сторис...")
    
    success = await process_story(user_id, photo_file_path, title, content, message)
    
    if success:
        if user_id in user_data:
            del user_data[user_id]

# ========== ОБРАБОТКА РУЧНОГО ВВОДА ==========
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
        
        await message.answer("⏳ Генерирую сторис из фото и подписи...")
        
        await process_story(user_id, file_path, title, content, message)
        return
    
    if user_id not in user_data:
        user_data[user_id] = {"step": "waiting_photo"}
    
    file = await bot.get_file(message.photo[-1].file_id)
    file_path = f"temp_{user_id}.jpg"
    await bot.download_file(file.file_path, file_path)

    user_data[user_id]["photo"] = file_path
    user_data[user_id]["step"] = "waiting_title"
    await message.answer("✅ Фото принято! Теперь отправь ЗАГОЛОВОК (текстом).")

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

        await message.answer("⏳ Генерирую сторис... Подожди пару секунд.")

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
        await bot.delete_webhook()
        print("✅ Вебхук удален")
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(delete_webhook())
    
    executor.start_polling(dp, skip_updates=True)
