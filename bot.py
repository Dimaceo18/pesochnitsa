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
    Разделяет текст на заголовок (первые 2-3 строки) и основной текст.
    Возвращает (заголовок, основной_текст)
    """
    if not text:
        return "", ""
    
    # Разбиваем на строки
    lines = text.strip().split('\n')
    lines = [line.strip() for line in lines if line.strip()]
    
    if len(lines) <= 3:
        # Если текста мало, всё идет в заголовок
        return "\n".join(lines), ""
    
    # Заголовок - первые 2-3 строки (но не более 100 символов)
    title_lines = []
    title_length = 0
    for i, line in enumerate(lines[:4]):  # Проверяем первые 4 строки
        if title_length + len(line) < 150 and len(title_lines) < 3:
            title_lines.append(line)
            title_length += len(line)
        else:
            break
    
    # Если заголовок получился слишком коротким (меньше 2 строк), берем 3 строки
    if len(title_lines) < 2 and len(lines) >= 3:
        title_lines = lines[:3]
    
    title = "\n".join(title_lines)
    
    # Основной текст - всё остальное
    remaining_lines = lines[len(title_lines):]
    content = "\n".join(remaining_lines)
    
    return title, content

# ========== ГЕНЕРАЦИЯ СТОРИС (ОБЩАЯ ФУНКЦИЯ) ==========
async def generate_story(photo_path: str, title: str, content: str) -> str:
    W, H = 1080, 1920
    HALF_H = H // 2

    # Черный холст
    canvas = Image.new('RGB', (W, H), color='black')

    # Вставляем фото (занимает верхнюю половину)
    photo = Image.open(photo_path).convert("RGB")
    photo_ratio = photo.width / photo.height
    target_ratio = W / HALF_H

    if photo_ratio > target_ratio:
        new_height = HALF_H
        new_width = int(new_height * photo_ratio)
        photo = photo.resize((new_width, new_height), Image.Resampling.LANCZOS)
        left = (new_width - W) // 2
        photo = photo.crop((left, 0, left + W, new_height))
    else:
        new_width = W
        new_height = int(new_width / photo_ratio)
        photo = photo.resize((new_width, new_height), Image.Resampling.LANCZOS)
        top = (new_height - HALF_H) // 2
        photo = photo.crop((0, top, new_width, top + HALF_H))

    canvas.paste(photo, (0, 0))

    # Градиент (40% от высоты фото)
    GRADIENT_HEIGHT = int(HALF_H * 0.4)
    GRADIENT_START_Y = HALF_H - GRADIENT_HEIGHT
    
    gradient = Image.new('RGBA', (W, GRADIENT_HEIGHT), (0, 0, 0, 0))
    draw_grad = ImageDraw.Draw(gradient)
    
    for i in range(GRADIENT_HEIGHT):
        alpha = int(255 * (i / GRADIENT_HEIGHT) * 0.8)
        draw_grad.rectangle([(0, i), (W, i + 1)], fill=(0, 0, 0, alpha))
    
    canvas.paste(gradient, (0, GRADIENT_START_Y), gradient)

    draw = ImageDraw.Draw(canvas)

    # Шрифты Inter
    try:
        font_bold = ImageFont.truetype(FONT_PATH_BOLD, 72)
    except:
        font_bold = ImageFont.load_default()
        logging.warning(f"Шрифт {FONT_PATH_BOLD} не найден, использую дефолтный")

    try:
        font_reg = ImageFont.truetype(FONT_PATH_REG, 48)
    except:
        font_reg = ImageFont.load_default()
        logging.warning(f"Шрифт {FONT_PATH_REG} не найден, использую дефолтный")

    # ========== ЗАГОЛОВОК ==========
    if title:
        PADDING_X = 5
        MAX_TITLE_WIDTH = W - (PADDING_X * 2)
        
        def wrap_title(text, font, max_width):
            words = text.split()
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
            
            return lines
        
        title_lines = wrap_title(title, font_bold, MAX_TITLE_WIDTH)
        title_text = "\n".join(title_lines)
        
        title_bbox = draw.textbbox((0, 0), title_text, font=font_bold)
        title_w = title_bbox[2] - title_bbox[0]
        title_h = title_bbox[3] - title_bbox[1]
        
        title_x = (W - title_w) // 2
        title_y = 870 - (title_h // 2)
        
        # Темно-серая подложка с градиентом
        padding = 25
        rect_x1 = title_x - padding
        rect_y1 = title_y - padding
        rect_x2 = title_x + title_w + padding
        rect_y2 = title_y + title_h + padding
        
        radius = 15
        rect_w = rect_x2 - rect_x1
        rect_h = rect_y2 - rect_y1
        
        # Создаем градиент для подложки
        gradient_bg = Image.new('RGBA', (rect_w, rect_h), (0, 0, 0, 0))
        grad_draw = ImageDraw.Draw(gradient_bg)
        
        for i in range(rect_h):
            gray_value = int(128 + (i / rect_h) * 52)
            alpha = 220
            grad_draw.rectangle([(0, i), (rect_w, i + 1)], fill=(gray_value, gray_value, gray_value, alpha))
        
        # Маска с закругленными углами
        mask = Image.new('L', (rect_w, rect_h), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle([(0, 0), (rect_w, rect_h)], radius=radius, fill=255)
        
        canvas.paste(gradient_bg, (rect_x1, rect_y1), mask)
        
        # Белая рамка
        draw.rounded_rectangle(
            [rect_x1, rect_y1, rect_x2, rect_y2],
            radius=radius,
            fill=None,
            outline=(255, 255, 255),
            width=3
        )
        
        # Внутренняя тонкая рамка
        inner_padding = 5
        draw.rounded_rectangle(
            [rect_x1 + inner_padding, rect_y1 + inner_padding, 
             rect_x2 - inner_padding, rect_y2 - inner_padding],
            radius=radius - 2,
            fill=None,
            outline=(255, 255, 255, 80),
            width=1
        )
        
        draw.text((title_x, title_y), title_text, font=font_bold, fill='white')

    # ========== ОСНОВНОЙ ТЕКСТ ==========
    if content:
        MAX_TEXT_H = H - HALF_H - 80
        MAX_TEXT_W = W - 60

        def fit_text(text, max_w, max_h):
            size = 48
            while size > 20:
                try:
                    test_font = ImageFont.truetype(FONT_PATH_REG, size)
                except:
                    test_font = ImageFont.load_default()
                chars_per_line = int(max_w / (size * 0.6))
                wrapped = textwrap.wrap(text, width=chars_per_line)
                test_text = "\n".join(wrapped)
                bbox = draw.textbbox((0, 0), test_text, font=test_font)
                th = bbox[3] - bbox[1]
                tw = bbox[2] - bbox[0]
                if th <= max_h and tw <= max_w:
                    return test_font, wrapped
                size -= 2
            return ImageFont.load_default(), [text]

        font_reg_fitted, wrapped_text = fit_text(content, MAX_TEXT_W, MAX_TEXT_H)
        final_text = "\n".join(wrapped_text)

        bbox = draw.textbbox((0, 0), final_text, font=font_reg_fitted)
        th = bbox[3] - bbox[1]
        tw = bbox[2] - bbox[0]
        text_x = (W - tw) // 2
        text_y = HALF_H + 40 + (MAX_TEXT_H - th) // 2

        draw.text((text_x, text_y), final_text, font=font_reg_fitted, fill='white')

    output_path = "output_story.png"
    canvas.save(output_path, "PNG")
    return output_path

# ========== ОБЩАЯ ФУНКЦИЯ ДЛЯ ОБРАБОТКИ ==========
async def process_story(user_id: int, photo_path: str, title: str, content: str, message: types.Message):
    """Общая функция для создания сторис из фото, заголовка и текста"""
    try:
        output = await generate_story(photo_path, title, content)
        await bot.send_photo(
            chat_id=user_id,
            photo=InputFile(output),
            caption="✅ Готово! Твоя сторис 50/50."
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
        "📱 Привет! Я делаю сторис 50/50 из репостов!\n\n"
        "Просто отправь мне РЕПОСТ любого поста из Telegram, и я:\n"
        "1️⃣ Возьму фото из поста\n"
        "2️⃣ Сделаю заголовок из первых 2-3 строк\n"
        "3️⃣ Остальной текст помещу в черную зону\n\n"
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
    
    # Проверяем, является ли сообщение репостом
    is_forward = message.forward_from or message.forward_from_chat or message.forward_date
    
    if not is_forward:
        # Если не репост - пропускаем, обработается другими хендлерами
        return
    
    await message.answer("📥 Обнаружен репост! Обрабатываю...")
    
    # Получаем текст из репоста
    text = message.text or message.caption or ""
    
    # Ищем фото в репосте
    photo_file_path = None
    
    if message.photo:
        # Фото в репосте
        file = await bot.get_file(message.photo[-1].file_id)
        photo_file_path = f"temp_{user_id}_forward.jpg"
        await bot.download_file(file.file_path, photo_file_path)
    elif message.document and message.document.mime_type and message.document.mime_type.startswith('image/'):
        # Фото как документ
        file = await bot.get_file(message.document.file_id)
        photo_file_path = f"temp_{user_id}_forward.jpg"
        await bot.download_file(file.file_path, photo_file_path)
    else:
        await message.answer("❌ В репосте нет фото! Пожалуйста, отправь репост с изображением.")
        return
    
    # Если есть медиагруппа (несколько фото)
    if message.media_group_id:
        await message.answer("⚠️ Обнаружено несколько фото. Я возьму первое изображение.")
    
    # Парсим текст на заголовок и основной текст
    title, content = parse_text(text)
    
    # Если нет заголовка, берем первые 2 строки
    if not title and text:
        lines = text.strip().split('\n')
        title = "\n".join(lines[:2])
        content = "\n".join(lines[2:])
    
    # Если нет текста - используем дефолтные значения
    if not title:
        title = "📌 Заголовок"
    if not content:
        content = "Текст отсутствует"
    
    await message.answer(f"📝 Заголовок: {title[:50]}...\n\n⏳ Генерирую сторис...")
    
    # Используем ТУ ЖЕ САМУЮ функцию, что и для ручного ввода
    success = await process_story(user_id, photo_file_path, title, content, message)
    
    if success:
        # Очищаем данные пользователя
        if user_id in user_data:
            del user_data[user_id]

# ========== ОБРАБОТКА РУЧНОГО ВВОДА ==========
@dp.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    
    # Если это репост с фото - уже обработано в handle_forward
    if message.forward_from or message.forward_from_chat or message.forward_date:
        return
    
    # Проверяем, есть ли подпись к фото (текст)
    caption = message.caption or ""
    
    # Если есть текст под фото - парсим его
    if caption:
        title, content = parse_text(caption)
        
        # Скачиваем фото
        file = await bot.get_file(message.photo[-1].file_id)
        file_path = f"temp_{user_id}.jpg"
        await bot.download_file(file.file_path, file_path)
        
        await message.answer("⏳ Генерирую сторис из фото и подписи...")
        
        await process_story(user_id, file_path, title, content, message)
        return
    
    # Если фото без подписи - ждем текст отдельно
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
    
    # Если это репост с текстом - уже обработано в handle_forward
    if message.forward_from or message.forward_from_chat or message.forward_date:
        return
    
    # Игнорируем команды
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
