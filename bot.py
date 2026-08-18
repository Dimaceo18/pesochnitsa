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
FONT_PATH_REG = "Inter-Regular.ttf"

# ========== НАСТРОЙКА ЛОГОВ ==========
logging.basicConfig(level=logging.INFO)

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# ========== ПАРСИНГ ТЕКСТА ==========
def parse_text(text: str) -> tuple:
    """
    Заголовок = ТОЛЬКО первый абзац (до первой пустой строки)
    Основной текст = всё остальное
    """
    if not text:
        return "", ""
    
    text = text.strip()
    
    # Разбиваем на абзацы по двойному переводу строки
    paragraphs = re.split(r'\n\s*\n', text)
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    
    if not paragraphs:
        return "", ""
    
    # ПЕРВЫЙ АБЗАЦ - это заголовок
    title = paragraphs[0]
    
    # ВСЁ ОСТАЛЬНОЕ - основной текст (включая второй, третий абзацы и т.д.)
    content = "\n\n".join(paragraphs[1:]) if len(paragraphs) > 1 else ""
    
    # Если заголовок длиннее 150 символов - обрезаем по последней точке
    if len(title) > 150:
        # Ищем последнюю точку, вопросительный или восклицательный знак в пределах 150 символов
        cut_pos = 150
        # Ищем последний разделитель в пределах 150 символов
        last_dot = title.rfind('.', 0, cut_pos)
        last_q = title.rfind('?', 0, cut_pos)
        last_excl = title.rfind('!', 0, cut_pos)
        
        # Берем самый дальний разделитель
        cut_pos = max(last_dot, last_q, last_excl)
        
        if cut_pos > 0:
            # Обрезаем заголовок
            remaining = title[cut_pos+1:].strip()
            title = title[:cut_pos+1].strip()
            # Добавляем остаток к основному тексту
            if remaining:
                content = remaining + "\n\n" + content if content else remaining
        else:
            # Если нет разделителя, просто обрезаем
            title = title[:150] + "..."
    
    # ЛОГИРУЕМ РЕЗУЛЬТАТ
    logging.info(f"📝 Парсинг текста:")
    logging.info(f"   Всего абзацев: {len(paragraphs)}")
    logging.info(f"   Заголовок ({len(title)} симв): {title[:100]}...")
    logging.info(f"   Контент ({len(content)} симв): {content[:100] if content else 'ПУСТО'}...")
    
    return title, content

# ========== ГЕНЕРАЦИЯ СТОРИС ==========
async def generate_story(photo_path: str, title: str, content: str) -> str:
    W, H = 1080, 1920  # 9:16
    
    logging.info(f"🖼 Генерация сторис:")
    logging.info(f"   Заголовок: {title[:100] if title else 'ПУСТО'}...")
    logging.info(f"   Контент: {content[:100] if content else 'ПУСТО'}...")
    
    # 1. БЕЛЫЙ ФОН
    canvas = Image.new('RGB', (W, H), color='white')
    draw = ImageDraw.Draw(canvas)
    
    # 2. ФОТО НА ВСЮ ШИРИНУ
    PHOTO_WIDTH = W
    PHOTO_X = 0
    
    photo = Image.open(photo_path).convert("RGB")
    photo_ratio = photo.width / photo.height
    PHOTO_HEIGHT = int(PHOTO_WIDTH / photo_ratio)
    
    if PHOTO_HEIGHT > 960:
        PHOTO_HEIGHT = 960
        photo = photo.crop((0, 0, photo.width, int(photo.width / (PHOTO_WIDTH / PHOTO_HEIGHT))))
    
    photo = photo.resize((PHOTO_WIDTH, PHOTO_HEIGHT), Image.Resampling.LANCZOS)
    
    border_size = 8
    bordered_photo = Image.new('RGB', (PHOTO_WIDTH, PHOTO_HEIGHT + border_size), color='black')
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
    
    # 4. ЗАГОЛОВОК (по центру)
    title_y_position = PHOTO_HEIGHT + border_size + 25
    
    if title:
        MAX_TITLE_WIDTH = W - 80
        
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
        
        title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
        title_w = title_bbox[2] - title_bbox[0]
        title_h = title_bbox[3] - title_bbox[1]
        
        title_x = (W - title_w) // 2
        title_y = title_y_position
        
        draw.text((title_x, title_y), title_text, font=title_font, fill='black')
        
        title_y_position = title_y + title_h + 8
    
    # 5. ОСНОВНОЙ ТЕКСТ (по левому краю с отступами)
    if content:
        logging.info(f"📄 Рисуем основной текст, длина: {len(content)} символов")
        
        SIDE_MARGIN = 40
        MAX_TEXT_W = W - (SIDE_MARGIN * 2)
        MAX_TEXT_H = H - title_y_position - 100
        
        def fit_content(text, max_w, max_h):
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
                    chars_per_line = int(max_w / (size * 0.6))
                    wrapped = textwrap.wrap(para, width=chars_per_line)
                    if not wrapped:
                        wrapped = [para]
                    wrapped_paragraphs.append(wrapped)
                    
                    for line in wrapped:
                        bbox = draw.textbbox((0, 0), line, font=font)
                        total_height += bbox[3] - bbox[1]
                    total_height += 12
                
                if total_height <= max_h:
                    return font, wrapped_paragraphs
            
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
        
        start_y = title_y_position + 5
        
        current_y = start_y
        for para_lines in wrapped_paragraphs:
            for line in para_lines:
                bbox = draw.textbbox((0, 0), line, font=content_font)
                line_width = bbox[2] - bbox[0]
                line_height = bbox[3] - bbox[1]
                
                line_x = SIDE_MARGIN
                draw.text((line_x, current_y), line, font=content_font, fill='#333333')
                current_y += line_height
            
            current_y += 12
        
        logging.info(f"✅ Основной текст нарисован")
    else:
        logging.warning(f"⚠️ Основной текст ПУСТОЙ!")
    
    # 6. ЖЕЛТЫЙ БЛОК ВНИЗУ
    YELLOW_BLOCK_H = 60
    YELLOW_BLOCK_Y = H - YELLOW_BLOCK_H
    
    draw.rectangle([0, YELLOW_BLOCK_Y, W, H], fill='#FFD700')
    
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
            caption="✅ Готово!"
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
        "📱 Привет! Я делаю сторис!\n\n"
        "Просто отправь мне РЕПОСТ любого поста, и я:\n"
        "1️⃣ Возьму фото на всю ширину\n"
        "2️⃣ Первый абзац сделаю заголовком\n"
        "3️⃣ Остальной текст размещу ниже\n\n"
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
    
    await message.answer("📥 Обнаружен репост! Обрабатываю...")
    
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
    
    # Очищаем текст от мусора
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
    
    # Если заголовок пустой - берем первое предложение
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
    
    await message.answer(f"📝 Заголовок: {title[:50]}...\n\n⏳ Генерирую...")
    
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
