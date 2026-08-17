import os
import logging
import io
from PIL import Image, ImageDraw, ImageFont
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command
import textwrap

# ========== КОНФИГ ==========
API_TOKEN = "ТВОЙ_ТОКЕН_СЮДА"  # ВСТАВЬ СВОЙ ТОКЕН
FONT_PATH_BOLD = "arialbd.ttf"  # Жирный для заголовка
FONT_PATH_REG = "arial.ttf"     # Обычный для текста

# ========== НАСТРОЙКА ЛОГОВ ==========
logging.basicConfig(level=logging.INFO)

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ========== ГЕНЕРАЦИЯ ИЗОБРАЖЕНИЯ ==========
async def generate_story(photo_path: str, title: str, content: str) -> str:
    # 1. Размеры холста
    W, H = 1080, 1920
    HALF_H = H // 2  # 960 px

    # 2. Создаем холст (черный фон)
    canvas = Image.new('RGB', (W, H), color='black')

    # 3. Открываем и вставляем фото (Cover - обрезка по центру)
    photo = Image.open(photo_path).convert("RGB")
    # Пропорции фото приводим к 1080x960
    photo_ratio = photo.width / photo.height
    target_ratio = W / HALF_H

    if photo_ratio > target_ratio:
        # Фото шире - обрезаем по бокам
        new_height = HALF_H
        new_width = int(new_height * photo_ratio)
        photo = photo.resize((new_width, new_height), Image.Resampling.LANCZOS)
        left = (new_width - W) // 2
        photo = photo.crop((left, 0, left + W, new_height))
    else:
        # Фото выше - обрезаем сверху/снизу
        new_width = W
        new_height = int(new_width / photo_ratio)
        photo = photo.resize((new_width, new_height), Image.Resampling.LANCZOS)
        top = (new_height - HALF_H) // 2
        photo = photo.crop((0, top, new_width, top + HALF_H))

    # Вставляем фото в верхнюю половину
    canvas.paste(photo, (0, 0))

    # 4. ГРАДИЕНТ (от y=768 до y=960, 20% от высоты фото)
    gradient = Image.new('RGBA', (W, 192), (0, 0, 0, 0))
    draw_grad = ImageDraw.Draw(gradient)
    for i in range(192):
        # Прозрачность от 0% (вверху) до 80% (внизу)
        alpha = int(255 * (i / 192) * 0.8)
        draw_grad.rectangle([(0, i), (W, i + 1)], fill=(0, 0, 0, alpha))
    canvas.paste(gradient, (0, 768), gradient)

    # 5. ШРИФТЫ
    try:
        font_bold = ImageFont.truetype(FONT_PATH_BOLD, 72)
        font_reg = ImageFont.truetype(FONT_PATH_REG, 48)
    except:
        # Если шрифтов нет - используем дефолтные
        font_bold = ImageFont.load_default()
        font_reg = ImageFont.load_default()

    # 6. ЗАГОЛОВОК (жирный, крупный, по центру, y=870)
    draw = ImageDraw.Draw(canvas)
    # Перенос длинного заголовка
    title_lines = textwrap.wrap(title, width=25)
    title_text = "\n".join(title_lines)
    
    # Центрируем заголовок
    title_bbox = draw.textbbox((0, 0), title_text, font=font_bold)
    title_w = title_bbox[2] - title_bbox[0]
    title_h = title_bbox[3] - title_bbox[1]
    title_x = (W - title_w) // 2
    title_y = 870 - (title_h // 2)
    
    draw.text((title_x, title_y), title_text, font=font_bold, fill='white')

    # 7. ОСНОВНОЙ ТЕКСТ (авторазмер, чтобы влазил в черную зону)
    # Черная зона: y от 960 до 1920. Отступы сверху/снизу по 40px
    MAX_TEXT_H = H - HALF_H - 80  # 960 - 80 = 880 px
    MAX_TEXT_W = W - 60  # отступы по бокам 30px

    # Функция подбора размера шрифта
    def fit_text(text, max_w, max_h, font_path):
        size = 48
        while size > 20:
            try:
                test_font = ImageFont.truetype(font_path, size)
            except:
                test_font = ImageFont.load_default()
            # Разбиваем по словам, чтобы переносить
            chars_per_line = int(max_w / (size * 0.6))
            wrapped = textwrap.wrap(text, width=chars_per_line)
            test_text = "\n".join(wrapped)
            bbox = draw.textbbox((0, 0), test_text, font=test_font)
            th = bbox[3] - bbox[1]
            tw = bbox[2] - bbox[0]
            if th <= max_h and tw <= max_w:
                return test_font, wrapped, size
            size -= 2
        return ImageFont.load_default(), [text], 20

    font_reg_fitted, wrapped_text, used_size = fit_text(content, MAX_TEXT_W, MAX_TEXT_H, FONT_PATH_REG)
    final_text = "\n".join(wrapped_text)

    # Центрируем основной текст по вертикали в черной зоне
    bbox = draw.textbbox((0, 0), final_text, font=font_reg_fitted)
    th = bbox[3] - bbox[1]
    tw = bbox[2] - bbox[0]
    text_x = (W - tw) // 2
    text_y = HALF_H + 40 + (MAX_TEXT_H - th) // 2

    draw.text((text_x, text_y), final_text, font=font_reg_fitted, fill='white')

    # 8. СОХРАНЯЕМ РЕЗУЛЬТАТ
    output_path = "output_story.png"
    canvas.save(output_path, "PNG")
    return output_path

# ========== ХЕНДЛЕРЫ КОМАНД ==========
# Словарь для хранения данных пользователя (временно)
user_data = {}

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "📱 Привет! Я делаю сторис 50/50.\n\n"
        "1. Отправь мне ФОТО\n"
        "2. Затем отправь ЗАГОЛОВОК (жирный текст)\n"
        "3. Затем отправь ОСНОВНОЙ ТЕКСТ (остальной контент)\n\n"
        "Я соберу всё в готовую сторис 9:16!"
    )
    user_data[message.from_user.id] = {"step": "waiting_photo"}

@dp.message(lambda msg: msg.photo)
async def handle_photo(message: Message):
    user_id = message.from_user.id
    if user_id not in user_data:
        await start(message)
        return
    
    # Скачиваем фото
    file = await bot.get_file(message.photo[-1].file_id)
    file_path = f"temp_{user_id}.jpg"
    await bot.download_file(file.file_path, file_path)
    
    user_data[user_id]["photo"] = file_path
    user_data[user_id]["step"] = "waiting_title"
    await message.answer("✅ Фото принято! Теперь отправь ЗАГОЛОВОК (текстом).")

@dp.message(lambda msg: msg.text and msg.text.startswith("/") == False)
async def handle_text(message: Message):
    user_id = message.from_user.id
    if user_id not in user_data:
        await start(message)
        return
    
    step = user_data[user_id].get("step", "")
    
    if step == "waiting_title":
        user_data[user_id]["title"] = message.text
        user_data[user_id]["step"] = "waiting_content"
        await message.answer("✅ Заголовок сохранен! Теперь отправь ОСНОВНОЙ ТЕКСТ (его я помещу в черную зону).")
    
    elif step == "waiting_content":
        user_data[user_id]["content"] = message.text
        user_data[user_id]["step"] = "done"
        
        await message.answer("⏳ Генерирую сторис... Подожди пару секунд.")
        
        # Генерируем картинку
        photo_path = user_data[user_id]["photo"]
        title = user_data[user_id]["title"]
        content = user_data[user_id]["content"]
        
        try:
            output = await generate_story(photo_path, title, content)
            # Отправляем файл
            await bot.send_photo(
                chat_id=user_id,
                photo=FSInputFile(output),
                caption="✅ Готово! Твоя сторис 50/50."
            )
            # Чистим за собой
            os.remove(photo_path)
            os.remove(output)
            del user_data[user_id]
        except Exception as e:
            await message.answer(f"❌ Ошибка: {str(e)}")
            del user_data[user_id]

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    print("🚀 Бот запущен...")
    dp.run_polling(bot)
