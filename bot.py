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

# Шрифты Inter
FONT_PATH_BOLD = "Inter-Bold.ttf"
FONT_PATH_REG = "Inter-Black.ttf"

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
    Заголовок - текст до первой пустой строки или до первого перевода строки.
    """
    if not text:
        return "", ""
    
    # Убираем лишние пробелы в начале и конце
    text = text.strip()
    
    # Разбиваем на абзацы (по двойному переводу строки)
    paragraphs = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    if not paragraphs:
        return "", ""
    
    # Первый абзац - заголовок
    title = paragraphs[0]
    
    # Все остальные абзацы - основной текст
    content = "\n\n".join(paragraphs[1:]) if len(paragraphs) > 1 else ""
    
    # Если заголовок слишком длинный (> 200 символов), обрезаем до первого предложения
    if len(title) > 200:
        # Ищем первую точку с пробелом, вопросительный или восклицательный знак
        match = re.search(r'[.!?]\s+', title)
        if match:
            title = title[:match.end()].strip()
            # Остаток от заголовка добавляем к основному тексту
            remaining = title[match.end():].strip()
            if remaining:
                content = remaining + "\n\n" + content if content else remaining
    
    # Если заголовок пустой, берем первые 2 предложения
    if not title:
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        title = ". ".join(sentences[:2])
        content = ". ".join(sentences[2:])
    
    return title, content

# ========== ГЕНЕРАЦИЯ СТОРИС (НОВЫЙ ДИЗАЙН) ==========
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
    
    # 3. ЗАГОЛОВОК (большими буквами, максимум 3 строки)
    if title:
        MAX_TITLE_WIDTH = W - 80
        
        def fit_title(text, max_width):
            for size in range(80, 30, -2):
                try:
                    font = ImageFont.truetype(FONT_PATH_BOLD, size)
                except:
                    font = ImageFont.load_default()
                
                words = text.split()
                lines = []
                current_line = []
                
                for word in words:
                    test_line = ' '.join(current_line + [word])
                    bbox = draw.textbbox((0, 0), test_line.upper(), font=font)
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
            words = text.split()
            lines = []
            current_line = []
            for word in words:
                test_line = ' '.join(current_line + [word])
                bbox = draw.textbbox((0, 0), test_line.upper(), font=font)
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
        title_text = "\n".join([line.upper() for line in title_lines])
        
        title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
        title_w = title_bbox[2] - title_bbox[0]
        title_h = title_bbox[3] - title_bbox[1]
        
        title_x = (W - title_w) // 2
        title_y = PHOTO_Y + PHOTO_SIZE + border_size * 2 + 30
        
        draw.text((title_x, title_y), title_text, font=title_font, fill='black')
        
        # 4. ОСНОВНОЙ ТЕКСТ
        if content:
            TEXT_START_Y = title_y + title_h + 20
            MAX_TEXT_H = H - TEXT_START_Y - 100
            MAX_TEXT_W = W - 80
            
            def fit_content(text, max_w, max_h):
                for size in range(44, 20, -2):
                    try:
                        font = ImageFont.truetype(FONT_PATH_REG, size)
                    except:
                        font = ImageFont.load_default()
                    
                    chars_per_line = int(max_w / (size * 0.6))
                    wrapped = textwrap.wrap(text, width=chars_per_line)
                    test_text = "\n".join(wrapped)
                    bbox = draw.textbbox((0, 0), test_text, font=font)
                    th = bbox[3] - bbox[1]
                    tw = bbox[2] - bbox[0]
                    
                    if th <= max_h and tw <= max_w:
                        return font, wrapped
                
                try:
                    font = ImageFont.truetype(FONT_PATH_REG, 20)
                except:
                    font = ImageFont.load_default()
                chars_per_line = int(max_w / (20 * 0.6))
                wrapped = textwrap.wrap(text, width=chars_per_line)
                return font, wrapped
            
            content_font, wrapped_content = fit_content(content, MAX_TEXT_W, MAX_TEXT_H)
            final_text = "\n".join(wrapped_content)
            
            bbox = draw.textbbox((0, 0), final_text, font=content_font)
            th = bbox[3] - bbox[1]
            tw = bbox[2] - bbox[0]
            
            text_x = (W - tw) // 2
            text_y = TEXT_START_Y + (MAX_TEXT_H - th) // 2
            
            draw.text((text_x, text_y), final_text, font=content_font, fill='#333333')
    
    # 5. ЖЕЛТЫЙ ПРЯМОУГОЛЬНИК ВНИЗУ
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
        "2️⃣ Первый абзац сделаю заголовком большими буквами\n"
        "3️⃣ Остальной текст размещу ниже\n"
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
    
    # Удаляем мусорные строки
    text = text.replace("**Текст отсутствует**", "").strip()
    # Удаляем строки с "Подписаться" и подобные
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        line = line.strip()
        if line and not line.startswith('Подписаться') and not line.startswith('@') and not line.startswith('#'):
            clean_lines.append(line)
    text = '\n'.join(clean_lines)
    
    title, content = parse_text(text)
    
    if not title and text:
        # Если не удалось определить абзацы, берем первые 2 предложения
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        title = ". ".join(sentences[:2])
        content = ". ".join(sentences[2:])
    
    if not title:
        title = "📌 Заголовок"
    if not content:
        content = "Текст отсутствует"
    
    # Ограничиваем заголовок до 150 символов
    if len(title) > 150:
        # Обрезаем по последней точке
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
    
    print("🚀 Бот запускается в новом белом дизайне...")
    
    async def delete_webhook():
        await bot.delete_webhook()
        print("✅ Вебхук удален")
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(delete_webhook())
    
    executor.start_polling(dp, skip_updates=True)
