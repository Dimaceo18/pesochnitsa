import os
import logging
import re
import random
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import textwrap
import io

# ========== КОНФИГ ==========
API_TOKEN = os.getenv("BOT_TOKEN")

if not API_TOKEN:
    raise ValueError("❌ Токен не найден! Создай переменную BOT_TOKEN в настройках Render.")

# Шрифты
FONT_PATHS = [
    "Inter-Bold.ttf",
    "Inter-Regular.ttf", 
    "Inter-Medium.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "arial.ttf"
]

# Размеры сторис
W, H = 1080, 1920

# ========== ОТСТУПЫ ==========
# ФОТО
PHOTO_TOP = 40
PHOTO_HEIGHT = 800
PHOTO_WIDTH = W - 80
PHOTO_LEFT = 40

# РУБРИКА
RUBRIC_TOP = PHOTO_TOP + 20
RUBRIC_LEFT = PHOTO_LEFT + 20
RUBRIC_PADDING_X = 30
RUBRIC_PADDING_Y = 12

# ЗАГОЛОВОК
TITLE_TOP = PHOTO_TOP + PHOTO_HEIGHT + 35
TITLE_MAX_WIDTH = W - 100

# ФИОЛЕТОВАЯ ЛИНИЯ (в 2 раза толще)
LINE_TOP_OFFSET = 20
LINE_HEIGHT = 8  # Было 4, теперь 8 (в 2 раза толще)

# ТЕКСТ НОВОСТИ
TEXT_TOP_OFFSET = 15

# КНОПКА (ПРЯМОУГОЛЬНИК С ЗАКРУГЛЕННЫМИ УГЛАМИ)
BUTTON_BOTTOM = 160
BUTTON_WIDTH = 600
BUTTON_HEIGHT = 120
BUTTON_RADIUS = 20  # Радиус скругления углов
BUTTON_OUTLINE_WIDTH = 15  # Толщина обводки 15px

# ========== РУБРИКИ ==========
RUBRICS = ["НОВОСТИ", "АФИША", "СПОРТ", "ФИНАНСЫ", "АВТО", "НЕДВИЖИМОСТЬ"]

# ========== НАСТРОЙКА ЛОГОВ ==========
logging.basicConfig(level=logging.INFO)

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# ========== ЗАГРУЗКА ШРИФТОВ ==========
def load_font(size, weight='regular'):
    """Загружает шрифт с запасным вариантом"""
    font_names = {
        'bold': FONT_PATHS[:3],
        'medium': [FONT_PATHS[2], FONT_PATHS[0], FONT_PATHS[4]],
        'regular': FONT_PATHS[1:3] + FONT_PATHS[3:5]
    }
    
    paths = font_names.get(weight, FONT_PATHS[1:3] + FONT_PATHS[3:5])
    
    for path in paths:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except:
            continue
    
    return ImageFont.load_default()

# ========== ФУНКЦИЯ ДЛЯ РИСОВАНИЯ ПРЯМОУГОЛЬНИКА С ЗАКРУГЛЕННЫМИ УГЛАМИ ==========
def draw_rounded_rectangle(draw, xy, radius, fill, outline=None, width=0):
    """Рисует прямоугольник с закругленными углами"""
    x1, y1, x2, y2 = xy
    
    # Основной прямоугольник
    draw.rectangle([x1 + radius, y1, x2 - radius, y2], fill=fill, outline=None, width=0)
    draw.rectangle([x1, y1 + radius, x2, y2 - radius], fill=fill, outline=None, width=0)
    
    # Четыре закругленных угла
    draw.ellipse([x1, y1, x1 + radius*2, y1 + radius*2], fill=fill, outline=None, width=0)
    draw.ellipse([x2 - radius*2, y1, x2, y1 + radius*2], fill=fill, outline=None, width=0)
    draw.ellipse([x1, y2 - radius*2, x1 + radius*2, y2], fill=fill, outline=None, width=0)
    draw.ellipse([x2 - radius*2, y2 - radius*2, x2, y2], fill=fill, outline=None, width=0)
    
    # Рисуем обводку поверх
    if outline:
        # Верхняя сторона
        draw.rectangle([x1 + radius, y1, x2 - radius, y1 + width], fill=outline, outline=None, width=0)
        # Нижняя сторона
        draw.rectangle([x1 + radius, y2 - width, x2 - radius, y2], fill=outline, outline=None, width=0)
        # Левая сторона
        draw.rectangle([x1, y1 + radius, x1 + width, y2 - radius], fill=outline, outline=None, width=0)
        # Правая сторона
        draw.rectangle([x2 - width, y1 + radius, x2, y2 - radius], fill=outline, outline=None, width=0)
        
        # Углы
        draw.ellipse([x1, y1, x1 + radius*2, y1 + radius*2], fill=outline, outline=None, width=0)
        draw.ellipse([x2 - radius*2, y1, x2, y1 + radius*2], fill=outline, outline=None, width=0)
        draw.ellipse([x1, y2 - radius*2, x1 + radius*2, y2], fill=outline, outline=None, width=0)
        draw.ellipse([x2 - radius*2, y2 - radius*2, x2, y2], fill=outline, outline=None, width=0)
        
        # Внутренние углы (белые, чтобы скрыть лишнюю обводку)
        r = radius - width
        if r > 0:
            draw.ellipse([x1 + width, y1 + width, x1 + width + r*2, y1 + width + r*2], fill=fill, outline=None, width=0)
            draw.ellipse([x2 - width - r*2, y1 + width, x2 - width, y1 + width + r*2], fill=fill, outline=None, width=0)
            draw.ellipse([x1 + width, y2 - width - r*2, x1 + width + r*2, y2 - width], fill=fill, outline=None, width=0)
            draw.ellipse([x2 - width - r*2, y2 - width - r*2, x2 - width, y2 - width], fill=fill, outline=None, width=0)

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

# ========== ОБРАБОТКА ФОТО ==========
def apply_photo_effect(image: Image.Image) -> Image.Image:
    """Применяет эффекты к фото: шум +5%, насыщенность +5%"""
    if image.mode != 'RGB':
        image = image.convert('RGB')
    
    # 1. Увеличение насыщенности на 5%
    enhancer = ImageEnhance.Color(image)
    image = enhancer.enhance(1.05)
    
    # 2. Добавление шума 5%
    pixel_data = list(image.getdata())
    width, height = image.size
    
    noise_intensity = 12
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
    
    return noisy_image

# ========== ГЕНЕРАЦИЯ СТОРИС ==========
async def generate_story(photo_path: str, title: str, content: str, rubric: str) -> str:
    logging.info(f"🖼 Генерация сторис:")
    logging.info(f"   Рубрика: {rubric}")
    logging.info(f"   Заголовок: {title[:100] if title else 'ПУСТО'}...")
    logging.info(f"   Контент: {content[:100] if content else 'ПУСТО'}...")
    
    # ============================================================
    # ШАГ 1: БЕЛЫЙ ХОЛСТ
    # ============================================================
    canvas = Image.new('RGB', (W, H), color='white')
    draw = ImageDraw.Draw(canvas)
    
    # ============================================================
    # ШАГ 2: ВСТАВЛЯЕМ ФОТО С ЭФФЕКТАМИ
    # ============================================================
    try:
        if os.path.exists(photo_path):
            photo = Image.open(photo_path).convert("RGB")
            
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
            
            # Применяем эффекты
            photo = apply_photo_effect(photo)
            
            # Вставляем фото с серой рамкой
            bordered_photo = Image.new('RGB', (PHOTO_WIDTH + 4, PHOTO_HEIGHT + 4), color='#e0e0e0')
            bordered_photo.paste(photo, (2, 2))
            canvas.paste(bordered_photo, (PHOTO_LEFT, PHOTO_TOP))
        else:
            raise FileNotFoundError(f"Фото не найдено: {photo_path}")
    except Exception as e:
        logging.error(f"❌ Ошибка при обработке фото: {e}")
        draw.rectangle([PHOTO_LEFT, PHOTO_TOP, PHOTO_LEFT + PHOTO_WIDTH, PHOTO_TOP + PHOTO_HEIGHT], 
                      fill='#f0f0f0', outline='#cccccc', width=2)
        draw.text((W//2 - 60, PHOTO_TOP + PHOTO_HEIGHT//2 - 10), 
                 "📷 ФОТО", font=load_font(36, 'bold'), fill='#999999')
    
    # ============================================================
    # ШАГ 3: РУБРИКА
    # ============================================================
    rubric_font = load_font(34, 'bold')
    rubric_bbox = draw.textbbox((0, 0), rubric, font=rubric_font)
    rubric_w = rubric_bbox[2] - rubric_bbox[0]
    rubric_h = rubric_bbox[3] - rubric_bbox[1]
    
    rub_x1 = RUBRIC_LEFT
    rub_y1 = RUBRIC_TOP
    rub_x2 = RUBRIC_LEFT + rubric_w + RUBRIC_PADDING_X * 2
    rub_y2 = RUBRIC_TOP + rubric_h + RUBRIC_PADDING_Y * 2
    
    draw.rectangle(
        [rub_x1, rub_y1, rub_x2, rub_y2],
        fill='#6C3CE1',
        outline='#6C3CE1',
        width=2
    )
    
    rub_text_x = rub_x1 + (rub_x2 - rub_x1 - rubric_w) // 2
    rub_text_y = rub_y1 + (rub_y2 - rub_y1 - rubric_h) // 2 - 2
    draw.text((rub_text_x, rub_text_y), rubric, font=rubric_font, fill='white')
    
    logging.info(f"📌 Рубрика '{rubric}' нарисована на фото")
    
    # ============================================================
    # ШАГ 4: ЗАГОЛОВОК
    # ============================================================
    title_y = TITLE_TOP
    max_title_height = 240
    
    title_font_size = 56
    title_lines = []
    
    for size in range(72, 32, -2):
        test_font = load_font(size, 'bold')
        
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
        title_font = load_font(32, 'bold')
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
    
    title_font = load_font(title_font_size, 'bold')
    title_text = "\n".join(title_lines)
    draw.text((50, title_y), title_text, font=title_font, fill='black')
    
    title_bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_height = title_bbox[3] - title_bbox[1]
    title_end_y = title_y + title_height
    
    logging.info(f"📐 Размер заголовка: {title_font_size}px, строк: {len(title_lines)}")
    
    # ============================================================
    # ШАГ 5: ФИОЛЕТОВАЯ ЛИНИЯ (в 2 раза толще)
    # ============================================================
    LINE_TOP = title_end_y + LINE_TOP_OFFSET
    draw.rectangle(
        [50, LINE_TOP, W - 50, LINE_TOP + LINE_HEIGHT],
        fill='#6C3CE1'
    )
    
    # ============================================================
    # ШАГ 6: ТЕКСТ НОВОСТИ
    # ============================================================
    text_y = LINE_TOP + LINE_HEIGHT + TEXT_TOP_OFFSET
    
    button_y = H - BUTTON_BOTTOM - BUTTON_HEIGHT - 20
    available_text_height = button_y - text_y - 30
    
    if content and content != "Текст отсутствует":
        paragraphs = content.split('\n\n')
        paragraphs = [p.strip() for p in paragraphs if p.strip()]
    else:
        paragraphs = ["Текст отсутствует"]
    
    text_font_size = 34
    wrapped_paragraphs = []
    
    for size in range(42, 20, -2):
        test_font = load_font(size, 'regular')
        
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
            
            para_height = len(wrapped) * (single_h + 8)
            total_height += para_height + 18
        
        if total_height <= available_text_height:
            text_font_size = size
            wrapped_paragraphs = temp_wrapped
            break
    else:
        text_font = load_font(20, 'regular')
        single_bbox = draw.textbbox((0, 0), "A", font=text_font)
        single_h = single_bbox[3] - single_bbox[1]
        
        for para in paragraphs:
            chars_per_line = int((W - 100) / (20 * 0.6))
            wrapped = textwrap.wrap(para, width=chars_per_line)
            if not wrapped:
                wrapped = [para]
            wrapped_paragraphs.append(wrapped)
        text_font_size = 20
    
    text_font = load_font(text_font_size, 'regular')
    single_bbox = draw.textbbox((0, 0), "A", font=text_font)
    single_h = single_bbox[3] - single_bbox[1]
    
    pos_y = text_y
    for para_idx, para_lines in enumerate(wrapped_paragraphs):
        for line in para_lines:
            draw.text((50, pos_y), line, font=text_font, fill='black')
            pos_y += single_h + 8
        pos_y += 18
    
    logging.info(f"📐 Размер текста: {text_font_size}px, абзацев: {len(wrapped_paragraphs)}")
    
    # ============================================================
    # ШАГ 7: ПРЯМОУГОЛЬНИК С ЗАКРУГЛЕННЫМИ УГЛАМИ (белый фон, фиолетовая обводка 15px)
    # ============================================================
    # Координаты кнопки
    btn_x1 = (W - BUTTON_WIDTH) // 2
    btn_y1 = H - BUTTON_BOTTOM - BUTTON_HEIGHT
    btn_x2 = btn_x1 + BUTTON_WIDTH
    btn_y2 = btn_y1 + BUTTON_HEIGHT
    
    # Рисуем прямоугольник с закругленными углами
    draw_rounded_rectangle(
        draw,
        [btn_x1, btn_y1, btn_x2, btn_y2],
        BUTTON_RADIUS,
        fill='white',
        outline='#6C3CE1',
        width=BUTTON_OUTLINE_WIDTH
    )
    
    logging.info(f"✅ Кнопка нарисована, размер: {BUTTON_WIDTH}x{BUTTON_HEIGHT}px, обводка: {BUTTON_OUTLINE_WIDTH}px")
    
    # ============================================================
    # ШАГ 8: СОХРАНЯЕМ
    # ============================================================
    output_path = "output_story.png"
    try:
        buffer = io.BytesIO()
        canvas.save(buffer, format='PNG')
        buffer.seek(0)
        
        with open(output_path, 'wb') as f:
            f.write(buffer.getvalue())
        
        logging.info(f"✅ Сторис сохранена: {output_path}")
        return output_path
    except Exception as e:
        logging.error(f"❌ Ошибка при сохранении: {e}")
        canvas.save(output_path, format='PNG', optimize=True)
        return output_path

# ========== ОБЩАЯ ФУНКЦИЯ ==========
async def process_story(user_id: int, photo_path: str, title: str, content: str, rubric: str, message: types.Message):
    try:
        output = await generate_story(photo_path, title, content, rubric)
        
        with open(output, 'rb') as photo_file:
            await bot.send_photo(
                chat_id=user_id,
                photo=photo_file,
                caption="✅ Готово! 🎞️"
            )
        
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

# ========== КЛАВИАТУРА ДЛЯ ВЫБОРА РУБРИКИ ==========
def get_rubric_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=3)
    buttons = []
    for rubric in RUBRICS:
        buttons.append(InlineKeyboardButton(rubric, callback_data=f"rubric_{rubric}"))
    keyboard.add(*buttons)
    return keyboard

# ========== ХЕНДЛЕРЫ ==========
user_data = {}

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer(
        "📱 Привет! Я делаю стильные сторис!\n\n"
        "Просто отправь мне РЕПОСТ любого поста с фото и текстом.\n"
        "Я спрошу рубрику, и создам красивую сторис!"
    )
    user_data[message.from_user.id] = {"step": "waiting_photo"}

@dp.callback_query_handler(lambda c: c.data.startswith('rubric_'))
async def process_rubric_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    rubric = callback_query.data.replace('rubric_', '')
    
    if user_id not in user_data or user_data[user_id].get("step") != "waiting_rubric":
        await callback_query.answer("❌ Пожалуйста, начните заново с отправки репоста.")
        return
    
    user_data[user_id]["rubric"] = rubric
    user_data[user_id]["step"] = "done"
    
    await callback_query.answer(f"✅ Выбрана рубрика: {rubric}")
    
    photo_path = user_data[user_id]["photo"]
    title = user_data[user_id]["title"]
    content = user_data[user_id]["content"]
    
    await callback_query.message.answer(f"⏳ Генерирую сторис с рубрикой '{rubric}'...")
    await process_story(user_id, photo_path, title, content, rubric, callback_query.message)
    
    if user_id in user_data:
        del user_data[user_id]

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
        title = "ЗДЕСЬ БУДЕТ ЗАГОЛОВОК ВАШЕЙ НОВОСТИ"
    if not content:
        content = "Текст отсутствует"
    
    user_data[user_id] = {
        "photo": photo_file_path,
        "title": title,
        "content": content,
        "step": "waiting_rubric"
    }
    
    await message.answer(
        "📌 Выберите рубрику для этой статьи:",
        reply_markup=get_rubric_keyboard()
    )

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
        
        user_data[user_id] = {
            "photo": file_path,
            "title": title,
            "content": content,
            "step": "waiting_rubric"
        }
        
        await message.answer(
            "📌 Выберите рубрику для этой статьи:",
            reply_markup=get_rubric_keyboard()
        )
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
        user_data[user_id]["step"] = "waiting_rubric"
        
        await message.answer(
            "📌 Выберите рубрику для этой статьи:",
            reply_markup=get_rubric_keyboard()
        )

# ========== ЗАПУСК ==========
if __name__ == "__main__":
    from aiogram import executor
    
    print("🚀 Бот запускается с рубриками...")
    
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
