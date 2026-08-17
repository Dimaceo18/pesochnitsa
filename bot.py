import os
import logging
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

# ========== ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЯ ==========
async def generate_story(photo_path: str, title: str, content: str) -> str:
    W, H = 1080, 1920
    HALF_H = H // 2

    # Черный холст
    canvas = Image.new('RGB', (W, H), color='black')

    # Вставляем фото
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

    # Градиент
    gradient = Image.new('RGBA', (W, 192), (0, 0, 0, 0))
    draw_grad = ImageDraw.Draw(gradient)
    for i in range(192):
        alpha = int(255 * (i / 192) * 0.8)
        draw_grad.rectangle([(0, i), (W, i + 1)], fill=(0, 0, 0, alpha))
    canvas.paste(gradient, (0, 768), gradient)

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

    # ========== ЗАГОЛОВОК С РАМКОЙ И ПОДЛОЖКОЙ ==========
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
    
    # ===== ПОДЛОЖКА С РАМКОЙ =====
    padding = 25  # Отступ текста от краев подложки
    rect_x1 = title_x - padding
    rect_y1 = title_y - padding
    rect_x2 = title_x + title_w + padding
    rect_y2 = title_y + title_h + padding
    
    radius = 15  # Радиус закругления
    
    # 1. Рисуем подложку (полупрозрачный черный, чтобы текст читался на любом фоне)
    draw.rounded_rectangle(
        [rect_x1, rect_y1, rect_x2, rect_y2],
        radius=radius,
        fill=(0, 0, 0, 200),  # Черный с прозрачностью ~78%
        outline=None
    )
    
    # 2. Рисуем белую рамку поверх подложки (чтобы было видно на черном фоне)
    draw.rounded_rectangle(
        [rect_x1, rect_y1, rect_x2, rect_y2],
        radius=radius,
        fill=None,
        outline=(255, 255, 255),  # Белая рамка
        width=3  # Толщина рамки 3px
    )
    
    # 3. Рисуем дополнительную декоративную рамку (тонкую внутреннюю)
    inner_padding = 5
    draw.rounded_rectangle(
        [rect_x1 + inner_padding, rect_y1 + inner_padding, 
         rect_x2 - inner_padding, rect_y2 - inner_padding],
        radius=radius - 2,
        fill=None,
        outline=(255, 255, 255, 100),  # Белая с прозрачностью
        width=1
    )
    
    # 4. Рисуем сам заголовок
    draw.text((title_x, title_y), title_text, font=font_bold, fill='white')

    # ========== ОСНОВНОЙ ТЕКСТ ==========
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

# ========== ХЕНДЛЕРЫ ==========
user_data = {}

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer(
        "📱 Привет! Я делаю сторис 50/50.\n\n"
        "1. Отправь мне ФОТО\n"
        "2. Затем отправь ЗАГОЛОВОК (жирный текст)\n"
        "3. Затем отправь ОСНОВНОЙ ТЕКСТ (остальной контент)\n\n"
        "Я соберу всё в готовую сторис 9:16!"
    )
    user_data[message.from_user.id] = {"step": "waiting_photo"}

@dp.message_handler(content_types=['photo'])
async def handle_photo(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_data:
        await start(message)
        return

    file = await bot.get_file(message.photo[-1].file_id)
    file_path = f"temp_{user_id}.jpg"
    await bot.download_file(file.file_path, file_path)

    user_data[user_id]["photo"] = file_path
    user_data[user_id]["step"] = "waiting_title"
    await message.answer("✅ Фото принято! Теперь отправь ЗАГОЛОВОК (текстом).")

@dp.message_handler(content_types=['text'])
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    if user_id not in user_data:
        await start(message)
        return

    if message.text.startswith('/'):
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
            del user_data[user_id]
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}")
            if user_id in user_data:
                del user_data[user_id]

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("🚀 Бот запущен...")
    from aiogram import executor
    executor.start_polling(dp, skip_updates=True)
