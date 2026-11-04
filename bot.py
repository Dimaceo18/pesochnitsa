import os
import logging
import re
import random
import asyncio
import unicodedata
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.exceptions import TerminatedByOtherGetUpdates
import textwrap
import io

# ========== КОНФИГ ==========
API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise ValueError("❌ Токен не найден! Создай переменную BOT_TOKEN в настройках Render.")

FONT_PATHS = [
    "Inter-Black.ttf",          # главный шрифт — лежит в корне репозитория
    "Inter-Bold.ttf",
    "Inter-Regular.ttf",
    "Inter-Medium.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "arial.ttf"
]

# ========== КЛАССИЧЕСКИЙ ШАБЛОН (1080x1920) ==========
W, H = 1080, 1920
PHOTO_TOP = 0
PHOTO_HEIGHT = 900
PHOTO_WIDTH = W
PHOTO_LEFT = 0

RUBRIC_TOP = PHOTO_TOP + PHOTO_HEIGHT + 20
RUBRIC_LEFT = 40
RUBRIC_PADDING_X = 30
RUBRIC_PADDING_Y = 12

TITLE_TOP = PHOTO_TOP + PHOTO_HEIGHT + 90
TITLE_MAX_WIDTH = W - 100
TITLE_LINE_SPACING = 12
LINE_TOP_OFFSET = 27
LINE_HEIGHT = 8
TEXT_TOP_OFFSET = 15

# ========== ИНСТА-ШАБЛОН (720x1280) ==========
IW, IH = 720, 1280

I_PHOTO_TOP = 0
I_PHOTO_HEIGHT = 520
I_PHOTO_WIDTH = IW
I_PHOTO_LEFT = 0

I_MARGIN_X = 32
I_TITLE_TOP = I_PHOTO_HEIGHT + 28

I_TITLE_FONT_MAX = 54
I_TITLE_FONT_MIN = 20
I_TITLE_PLATE_PAD_X = 18
I_TITLE_PLATE_PAD_Y = 10
I_TITLE_PLATE_RADIUS = 16
I_TITLE_LINE_GAP = -1

I_TEXT_TOP_GAP = 24
I_TEXT_FONT_MAX = 30
I_TEXT_FONT_MIN = 16
I_TEXT_LINE_GAP = 6
I_TEXT_PARA_GAP = 16

RUBRICS = ["НОВОСТИ", "АФИША", "СПОРТ", "ФИНАНСЫ", "АВТО", "НЕДВИЖИМОСТЬ"]

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

def load_font(size, weight='regular'):
    """
    Загрузка шрифта.
    Для инста-шаблона используется weight='black' — Inter-Black.ttf из корня.
    Фолбэк — Bold/Regular/системные шрифты, чтобы бот не падал без файла.
    """
    font_names = {
        'black':   ["Inter-Black.ttf"] + FONT_PATHS,
        'bold':    ["Inter-Black.ttf"] + FONT_PATHS[:4],
        'medium':  [FONT_PATHS[3], FONT_PATHS[1], FONT_PATHS[5]],
        'regular': [FONT_PATHS[2], FONT_PATHS[1]] + FONT_PATHS[4:]
    }
    paths = font_names.get(weight, [FONT_PATHS[2], FONT_PATHS[1]] + FONT_PATHS[4:])
    for path in paths:
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except:
            continue
    logging.warning(f"⚠️ Шрифт не найден (weight={weight}, size={size}), используется дефолтный")
    return ImageFont.load_default()

def remove_emojis(text: str) -> str:
    if not text:
        return text
    cleaned_chars = []
    for ch in text:
        code = ord(ch)
        if (0x1F300 <= code <= 0x1FAFF or 0x1F000 <= code <= 0x1F2FF or
            0x2600 <= code <= 0x27BF or 0x2B00 <= code <= 0x2BFF or
            0xFE00 <= code <= 0xFE0F or 0x1F1E6 <= code <= 0x1F1FF or
            0xE0020 <= code <= 0xE007F):
            continue
        if unicodedata.category(ch) == 'So':
            continue
        cleaned_chars.append(ch)
    cleaned = ''.join(cleaned_chars)
    cleaned = re.sub(r'\s+([,.!?;:…»)])', r'\1', cleaned)
    cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)
    cleaned = '\n'.join(line.strip() for line in cleaned.split('\n'))
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned.strip()

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

def apply_photo_effect(image: Image.Image) -> Image.Image:
    if image.mode != 'RGB':
        image = image.convert('RGB')
    enhancer = ImageEnhance.Color(image)
    image = enhancer.enhance(1.05)
    pixel_data = list(image.getdata())
    width, height = image.size
    noise_intensity = 12
    noisy_pixels = []
    for pixel in pixel_data:
        r, g, b = pixel
        r = max(0, min(255, r + random.randint(-noise_intensity, noise_intensity)))
        g = max(0, min(255, g + random.randint(-noise_intensity, noise_intensity)))
        b = max(0, min(255, b + random.randint(-noise_intensity, noise_intensity)))
        noisy_pixels.append((r, g, b))
    noisy_image = Image.new('RGB', (width, height))
    noisy_image.putdata(noisy_pixels)
    return noisy_image

def fit_photo(photo: Image.Image, target_w: int, target_h: int) -> Image.Image:
    photo_ratio = photo.width / photo.height
    target_ratio = target_w / target_h
    if photo_ratio > target_ratio:
        new_height = target_h
        new_width = int(new_height * photo_ratio)
        photo = photo.resize((new_width, new_height), Image.Resampling.LANCZOS)
        left = (new_width - target_w) // 2
        photo = photo.crop((left, 0, left + target_w, new_height))
    else:
        new_width = target_w
        new_height = int(new_width / photo_ratio)
        photo = photo.resize((new_width, new_height), Image.Resampling.LANCZOS)
        top = (new_height - target_h) // 2
        photo = photo.crop((0, top, new_width, top + target_h))
    return photo

# ========== ГЕНЕРАЦИЯ: КЛАССИЧЕСКИЙ ШАБЛОН ==========
async def generate_story_classic(photo_path: str, title: str, content: str, rubric: str,
                                 highlight_words: list, theme: str = "light") -> str:
    logging.info(f"🖼 [classic] тема: {theme}, рубрика: {rubric or 'БЕЗ'}")
    is_dark = (theme == "dark")
    bg_color = 'black' if is_dark else 'white'
    text_color = 'white' if is_dark else 'black'
    placeholder_bg = '#1a1a1a' if is_dark else '#f0f0f0'
    placeholder_outline = '#333333' if is_dark else '#cccccc'
    placeholder_text = '#666666' if is_dark else '#999999'

    canvas = Image.new('RGB', (W, H), color=bg_color)
    draw = ImageDraw.Draw(canvas)

    try:
        if os.path.exists(photo_path):
            photo = Image.open(photo_path).convert("RGB")
            photo = fit_photo(photo, PHOTO_WIDTH, PHOTO_HEIGHT)
            photo = apply_photo_effect(photo)
            canvas.paste(photo, (PHOTO_LEFT, PHOTO_TOP))
        else:
            raise FileNotFoundError(photo_path)
    except Exception as e:
        logging.error(f"❌ Фото: {e}")
        draw.rectangle([PHOTO_LEFT, PHOTO_TOP, PHOTO_LEFT + PHOTO_WIDTH, PHOTO_TOP + PHOTO_HEIGHT],
                      fill=placeholder_bg, outline=placeholder_outline, width=2)
        draw.text((W//2 - 60, PHOTO_TOP + PHOTO_HEIGHT//2 - 10),
                 "📷 ФОТО", font=load_font(36, 'bold'), fill=placeholder_text)

    if rubric:
        rf = load_font(34, 'bold')
        rb = draw.textbbox((0, 0), rubric, font=rf)
        rw = rb[2] - rb[0]
        rh = rb[3] - rb[1]
        x1, y1 = RUBRIC_LEFT, RUBRIC_TOP
        x2 = x1 + rw + RUBRIC_PADDING_X * 2
        y2 = y1 + rh + RUBRIC_PADDING_Y * 2
        draw.rectangle([x1, y1, x2, y2], fill='#6C3CE1')
        draw.text((x1 + (x2 - x1 - rw) // 2, y1 + (y2 - y1 - rh) // 2 - 4),
                  rubric, font=rf, fill='white')

    title_y = TITLE_TOP
    max_title_height = 380
    title_font_size = 56
    title_lines = []

    for size in range(72, 32, -2):
        tf = load_font(size, 'bold')
        words = title.upper().split()
        lines, cur = [], []
        for word in words:
            test = ' '.join(cur + [word])
            bb = draw.textbbox((0, 0), test, font=tf)
            if bb[2] - bb[0] <= TITLE_MAX_WIDTH:
                cur.append(word)
            else:
                if cur: lines.append(' '.join(cur))
                cur = [word]
        if cur: lines.append(' '.join(cur))
        if lines:
            lb = draw.textbbox((0, 0), "A", font=tf)
            lh = lb[3] - lb[1]
            th = len(lines) * lh + (len(lines) - 1) * TITLE_LINE_SPACING
            if th <= max_title_height and len(lines) <= 4:
                title_font_size = size
                title_lines = lines
                break
    else:
        tf = load_font(32, 'bold')
        words = title.upper().split()
        lines, cur = [], []
        for word in words:
            test = ' '.join(cur + [word])
            bb = draw.textbbox((0, 0), test, font=tf)
            if bb[2] - bb[0] <= TITLE_MAX_WIDTH:
                cur.append(word)
            else:
                if cur: lines.append(' '.join(cur))
                cur = [word]
        if cur: lines.append(' '.join(cur))
        title_lines = lines
        title_font_size = 32

    title_font = load_font(title_font_size, 'bold')
    purple_font = load_font(title_font_size, 'bold')
    lb = draw.textbbox((0, 0), "A", font=title_font)
    lh = lb[3] - lb[1]

    current_y = title_y
    for line in title_lines:
        cx = 50
        for word in line.split():
            is_hl = word in [w.upper() for w in highlight_words]
            font = purple_font if is_hl else title_font
            color = '#6C3CE1' if is_hl else text_color
            draw.text((cx, current_y), word, font=font, fill=color)
            wb = draw.textbbox((0, 0), word, font=font)
            cx += (wb[2] - wb[0]) + 10
        current_y += lh + TITLE_LINE_SPACING
    title_end_y = current_y - TITLE_LINE_SPACING

    LINE_TOP = title_end_y + LINE_TOP_OFFSET
    draw.rectangle([50, LINE_TOP, W - 50, LINE_TOP + LINE_HEIGHT], fill='#6C3CE1')

    text_y = LINE_TOP + LINE_HEIGHT + TEXT_TOP_OFFSET
    available_text_height = H - text_y - 50
    if content and content != "Текст отсутствует":
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    else:
        paragraphs = ["Текст отсутствует"]

    text_font_size = 34
    wrapped_paragraphs = []
    for size in range(42, 20, -2):
        tf = load_font(size, 'regular')
        sb = draw.textbbox((0, 0), "A", font=tf)
        sh = sb[3] - sb[1]
        total_h = 0
        tmp = []
        for para in paragraphs:
            cpl = int((W - 100) / (size * 0.6))
            w = textwrap.wrap(para, width=cpl) or [para]
            tmp.append(w)
            total_h += len(w) * (sh + 8) + 18
        if total_h <= available_text_height:
            text_font_size = size
            wrapped_paragraphs = tmp
            break
    else:
        tf = load_font(20, 'regular')
        sb = draw.textbbox((0, 0), "A", font=tf)
        sh = sb[3] - sb[1]
        for para in paragraphs:
            cpl = int((W - 100) / (20 * 0.6))
            w = textwrap.wrap(para, width=cpl) or [para]
            wrapped_paragraphs.append(w)
        text_font_size = 20

    text_font = load_font(text_font_size, 'regular')
    sb = draw.textbbox((0, 0), "A", font=text_font)
    sh = sb[3] - sb[1]
    pos_y = text_y
    for para_lines in wrapped_paragraphs:
        for line in para_lines:
            draw.text((50, pos_y), line, font=text_font, fill=text_color)
            pos_y += sh + 8
        pos_y += 18

    output_path = "output_story.png"
    canvas.save(output_path, format='PNG')
    return output_path

# ========== ГЕНЕРАЦИЯ: ИНСТА-ШАБЛОН ==========
def draw_rounded_rect_highres(draw, box, radius, fill):
    x1, y1, x2, y2 = box
    r = min(radius, (x2 - x1) // 2, (y2 - y1) // 2)
    if r <= 0:
        draw.rectangle(box, fill=fill)
        return

    scale = 4
    width = (x2 - x1) * scale
    height = (y2 - y1) * scale
    if width <= 0 or height <= 0:
        return

    temp = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp)
    temp_draw.rounded_rectangle(
        [0, 0, width - 1, height - 1],
        radius=r * scale,
        fill=fill
    )
    temp = temp.resize((x2 - x1, y2 - y1), Image.Resampling.LANCZOS)
    draw._image.paste(temp, (x1, y1), temp)

def wrap_title_by_width(draw, text, font, max_width):
    words = text.upper().split()
    lines, cur = [], []
    for word in words:
        test = ' '.join(cur + [word])
        bb = draw.textbbox((0, 0), test, font=font)
        if bb[2] - bb[0] <= max_width:
            cur.append(word)
        else:
            if cur:
                lines.append(' '.join(cur))
            cur = [word]
    if cur:
        lines.append(' '.join(cur))
    return lines

# Строгий перенос текста по РЕАЛЬНОЙ ширине через textbbox
def wrap_text_strict(draw, text, font, max_width):
    words = text.split()
    lines, cur = [], []
    for word in words:
        test = ' '.join(cur + [word])
        bb = draw.textbbox((0, 0), test, font=font)
        if bb[2] - bb[0] <= max_width:
            cur.append(word)
        else:
            if cur:
                lines.append(' '.join(cur))
            cur = [word]
    if cur:
        lines.append(' '.join(cur))
    return lines

async def generate_story_insta(photo_path: str, title: str, content: str, theme: str = "dark") -> str:
    logging.info(f"🖼 [insta] генерация (тема: {theme})")

    if theme == "dark":
        bg_color = 'black'
        text_color = 'white'
        plate_color = 'white'
        title_text_color = 'black'
        placeholder_bg = '#111111'
        placeholder_outline = '#333333'
        placeholder_text = '#666666'
    else:
        bg_color = 'white'
        text_color = 'black'
        plate_color = 'black'
        title_text_color = 'white'
        placeholder_bg = '#f0f0f0'
        placeholder_outline = '#cccccc'
        placeholder_text = '#999999'

    canvas = Image.new('RGB', (IW, IH), color=bg_color)
    draw = ImageDraw.Draw(canvas)

    try:
        if os.path.exists(photo_path):
            photo = Image.open(photo_path).convert("RGB")
            photo = fit_photo(photo, I_PHOTO_WIDTH, I_PHOTO_HEIGHT)
            photo = apply_photo_effect(photo)
            canvas.paste(photo, (I_PHOTO_LEFT, I_PHOTO_TOP))
        else:
            raise FileNotFoundError(photo_path)
    except Exception as e:
        logging.error(f"❌ Фото: {e}")
        draw.rectangle([I_PHOTO_LEFT, I_PHOTO_TOP, I_PHOTO_LEFT + I_PHOTO_WIDTH, I_PHOTO_TOP + I_PHOTO_HEIGHT],
                      fill=placeholder_bg, outline=placeholder_outline, width=2)
        draw.text((IW // 2 - 50, I_PHOTO_HEIGHT // 2 - 10),
                 "📷 ФОТО", font=load_font(28, 'black'), fill=placeholder_text)

    max_width = IW - 2 * I_MARGIN_X

    title_words_count = len(title.upper().split())
    max_lines_allowed = 3 if title_words_count <= 9 else 4

    title_font_size = I_TITLE_FONT_MAX
    title_lines = []

    # Inter-Black для подбора размера заголовка
    for size in range(I_TITLE_FONT_MAX, I_TITLE_FONT_MIN - 1, -1):
        tf = load_font(size, 'black')
        lines = wrap_title_by_width(draw, title, tf, max_width - 2 * I_TITLE_PLATE_PAD_X)

        lb = draw.textbbox((0, 0), "A", font=tf)
        lh = lb[3] - lb[1]
        plate_h = lh + 2 * I_TITLE_PLATE_PAD_Y
        total_h = len(lines) * plate_h + (len(lines) - 1) * I_TITLE_LINE_GAP

        if len(lines) <= max_lines_allowed and total_h <= 300:
            title_font_size = size
            title_lines = lines
            break

    if not title_lines:
        tf = load_font(I_TITLE_FONT_MIN, 'black')
        title_lines = wrap_title_by_width(draw, title, tf, max_width - 2 * I_TITLE_PLATE_PAD_X)
        title_font_size = I_TITLE_FONT_MIN

    # Inter-Black для отрисовки заголовка
    title_font = load_font(title_font_size, 'black')
    lb = draw.textbbox((0, 0), "A", font=title_font)
    lh = lb[3] - lb[1]
    plate_h = lh + 2 * I_TITLE_PLATE_PAD_Y

    cur_y = I_TITLE_TOP
    max_plate_w = 0

    for line in title_lines:
        wb = draw.textbbox((0, 0), line, font=title_font)
        line_w = wb[2] - wb[0]
        plate_w = line_w + 2 * I_TITLE_PLATE_PAD_X
        max_plate_w = max(max_plate_w, plate_w)

        x1 = I_MARGIN_X
        y1 = cur_y
        x2 = x1 + plate_w
        y2 = y1 + plate_h

        draw_rounded_rect_highres(draw, [x1, y1, x2, y2], I_TITLE_PLATE_RADIUS, plate_color)

        center_x = x1 + plate_w / 2
        center_y = y1 + plate_h / 2
        draw.text((center_x, center_y), line, font=title_font, fill=title_text_color, anchor="mm")

        cur_y = y2 + I_TITLE_LINE_GAP

    # ==========================================
    # ОСНОВНОЙ ТЕКСТ (Inter-Black)
    # Строго привязываем ширину текста к ширине самой широкой плашки.
    # ==========================================
    text_y = cur_y + I_TEXT_TOP_GAP
    available_h = IH - text_y - 24

    text_line_max_width = max_plate_w - 4

    if content and content != "Текст отсутствует":
        paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    else:
        paragraphs = ["Текст отсутствует"]

    text_font_size = I_TEXT_FONT_MAX
    wrapped_paragraphs = []

    # Inter-Black для подбора размера основного текста
    for size in range(I_TEXT_FONT_MAX, I_TEXT_FONT_MIN - 1, -1):
        tf = load_font(size, 'black')
        sb = draw.textbbox((0, 0), "A", font=tf)
        sh = sb[3] - sb[1]

        total_h = 0
        tmp_paragraphs = []

        for para in paragraphs:
            lines = wrap_text_strict(draw, para.upper(), tf, text_line_max_width)
            tmp_paragraphs.append(lines)
            total_h += len(lines) * (sh + I_TEXT_LINE_GAP) + I_TEXT_PARA_GAP

        if total_h <= available_h:
            text_font_size = size
            wrapped_paragraphs = tmp_paragraphs
            break

    if not wrapped_paragraphs:
        tf = load_font(I_TEXT_FONT_MIN, 'black')
        for para in paragraphs:
            lines = wrap_text_strict(draw, para.upper(), tf, text_line_max_width)
            wrapped_paragraphs.append(lines)
        text_font_size = I_TEXT_FONT_MIN

    # Inter-Black для отрисовки основного текста
    text_font = load_font(text_font_size, 'black')
    sb = draw.textbbox((0, 0), "A", font=text_font)
    sh = sb[3] - sb[1]

    pos_y = text_y
    for para_lines in wrapped_paragraphs:
        for line in para_lines:
            draw.text((I_MARGIN_X, pos_y), line, font=text_font, fill=text_color)
            pos_y += sh + I_TEXT_LINE_GAP
        pos_y += I_TEXT_PARA_GAP

    output_path = f"output_story_insta_{theme}.png"
    canvas.save(output_path, format='PNG')
    return output_path

# ========== ДИСПЕТЧЕР ГЕНЕРАЦИИ ==========
async def generate_story(photo_path: str, title: str, content: str, rubric: str,
                         highlight_words: list, theme: str = "light",
                         template: str = "classic") -> str:
    if template == "insta":
        return await generate_story_insta(photo_path, title, content, theme)
    return await generate_story_classic(photo_path, title, content, rubric, highlight_words, theme)

# ========== ОБЩАЯ ФУНКЦИЯ ==========
async def process_story(user_id: int, photo_path: str, title: str, content: str,
                        rubric: str, highlight_words: list, message: types.Message,
                        theme: str = "light", template: str = "classic"):
    try:
        output = await generate_story(photo_path, title, content, rubric,
                                      highlight_words, theme, template)
        with open(output, 'rb') as photo_file:
            await bot.send_photo(chat_id=user_id, photo=photo_file, caption="✅ Готово! 🎞️")
        for file_path in [photo_path, output]:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logging.warning(f"⚠️ Не удалось удалить {file_path}: {e}")
        return True
    except Exception as e:
        logging.error(f"❌ Ошибка: {str(e)}")
        await bot.send_message(user_id, f"❌ Ошибка: {str(e)}")
        return False

# ========== КЛАВИАТУРЫ ==========
def get_template_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("🎨 Классик", callback_data="template_classic"),
        InlineKeyboardButton("📸 Инста-дизайн", callback_data="template_insta"),
    )
    return kb

def get_theme_keyboard():
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("☀️ Светлая", callback_data="theme_light"),
        InlineKeyboardButton("🌙 Тёмная", callback_data="theme_dark"),
    )
    return kb

def get_rubric_keyboard():
    kb = InlineKeyboardMarkup(row_width=3)
    buttons = [InlineKeyboardButton(r, callback_data=f"rubric_{r}") for r in RUBRICS]
    buttons.append(InlineKeyboardButton("🚫 БЕЗ РУБРИКИ", callback_data="rubric_none"))
    kb.add(*buttons)
    return kb

# ========== ВСПОМОГАТЕЛЬНОЕ ==========
async def safe_remove_keyboard(message: types.Message):
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

# ========== ХЕНДЛЕРЫ ==========
user_data = {}

@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    user_id = message.from_user.id
    user_data[user_id] = {"step": "waiting_photo"}
    await bot.send_message(
        user_id,
        "📱 Привет! Я делаю стильные сторис!\n\n"
        "Отправь мне РЕПОСТ любого поста с фото и текстом.\n"
        "Дальше — шаблон, тема, рубрика и выделение слов (если нужно).\n\n"
        "✨ Эмодзи и смайлики из текста автоматически убираются."
    )

@dp.message_handler(content_types=['photo', 'document'])
async def handle_photo_or_document(message: types.Message):
    user_id = message.from_user.id
    is_forward = message.forward_from or message.forward_from_chat or message.forward_date

    if is_forward:
        await bot.send_message(user_id, "📥 Обнаружен репост! Обрабатываю...")

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
            await bot.send_message(user_id, "❌ В репосте нет фото!")
            return

        text = text.replace("**Текст отсутствует**", "").strip()
        lines = text.split('\n')
        clean_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('Подписаться') and not line.startswith('@') and not line.startswith('#'):
                clean_lines.append(line)
        text = '\n'.join(clean_lines)
        text = remove_emojis(text)

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
            "highlight_words": [],
            "step": "waiting_template"
        }

        await bot.send_message(
            user_id,
            f"📝 Заголовок:\n{title}\n\n"
            f"🖼 Выберите шаблон оформления:",
            reply_markup=get_template_keyboard()
        )
        return

    if user_id not in user_data:
        user_data[user_id] = {"step": "waiting_photo"}

    caption = message.caption or ""
    if caption:
        caption = remove_emojis(caption)
        title, content = parse_text(caption)
        file = await bot.get_file(message.photo[-1].file_id)
        file_path = f"temp_{user_id}.jpg"
        await bot.download_file(file.file_path, file_path)

        user_data[user_id] = {
            "photo": file_path,
            "title": title,
            "content": content,
            "highlight_words": [],
            "step": "waiting_template"
        }

        await bot.send_message(
            user_id,
            f"📝 Заголовок:\n{title}\n\n"
            f"🖼 Выберите шаблон оформления:",
            reply_markup=get_template_keyboard()
        )
        return

    file = await bot.get_file(message.photo[-1].file_id)
    file_path = f"temp_{user_id}.jpg"
    await bot.download_file(file.file_path, file_path)
    user_data[user_id]["photo"] = file_path
    user_data[user_id]["step"] = "waiting_title"
    await bot.send_message(user_id, "✅ Фото принято! Теперь отправь ЗАГОЛОВОК.")

@dp.message_handler(content_types=['text'])
async def handle_text(message: types.Message):
    user_id = message.from_user.id
    if message.text.startswith('/'):
        return
    if user_id not in user_data:
        await start(message)
        return

    step = user_data[user_id].get("step", "")

    if step == "waiting_title":
        user_data[user_id]["title"] = remove_emojis(message.text)
        user_data[user_id]["step"] = "waiting_content"
        await bot.send_message(user_id, "✅ Заголовок сохранен! Теперь отправь ОСНОВНОЙ ТЕКСТ.")
        return

    if step == "waiting_content":
        user_data[user_id]["content"] = remove_emojis(message.text)
        user_data[user_id]["step"] = "waiting_template"
        await bot.send_message(
            user_id,
            "✅ Текст сохранен!\n\n"
            "🖼 Выберите шаблон оформления:",
            reply_markup=get_template_keyboard()
        )
        return

    if step == "waiting_highlight_words":
        text = message.text.strip()
        if text.lower() in ['нет', '-', 'без', 'none', 'skip', 'не надо']:
            user_data[user_id]["highlight_words"] = []
        else:
            if ',' in text:
                words = [w.strip() for w in text.split(',') if w.strip()]
            else:
                words = text.split()
            words = [w for w in words if len(w) > 2]
            user_data[user_id]["highlight_words"] = words

        user_data[user_id]["step"] = "waiting_theme"
        hl = f"Выделенные слова: {', '.join(user_data[user_id]['highlight_words']) if user_data[user_id]['highlight_words'] else 'Нет'}"
        await bot.send_message(
            user_id,
            f"✅ Слова сохранены!\n{hl}\n\n"
            f"🎨 Выберите тему оформления:",
            reply_markup=get_theme_keyboard()
        )
        return

    await bot.send_message(user_id, "❓ Я не понял. Отправь /start, чтобы начать заново.")

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('template_'))
async def process_template_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    template = "insta" if callback_query.data == "template_insta" else "classic"
    await callback_query.answer()

    if user_id not in user_data:
        await bot.send_message(user_id, "❌ Начните заново: /start")
        return

    if user_data[user_id].get("step") not in ["waiting_template", "waiting_title", "waiting_content"]:
        if template == "classic" and user_data[user_id].get("step") == "waiting_highlight_words":
            pass
        else:
            await bot.send_message(user_id, "❌ Начните заново: /start")
            return

    user_data[user_id]["template"] = template
    await safe_remove_keyboard(callback_query.message)

    if template == "classic":
        user_data[user_id]["step"] = "waiting_highlight_words"
        title = user_data[user_id].get("title", "")
        await bot.send_message(
            user_id,
            f"🎨 Шаблон: Классик\n\n"
            f"✏️ Отправь слова для выделения фиолетовым (через запятую/пробел).\n"
            f"Например: {', '.join(title.split()[:3]) if title.split() else 'важные слова'}\n\n"
            f"Если не нужно — отправь 'нет' или '-'"
        )
    else:
        user_data[user_id]["step"] = "waiting_generation"
        photo_path = user_data[user_id].get("photo")
        title = user_data[user_id].get("title")
        content = user_data[user_id].get("content")

        if not photo_path or not title:
            await bot.send_message(user_id, "❌ Не хватает данных. Начните заново: /start")
            return

        await bot.send_message(
            user_id,
            "⏳ Генерирую два варианта в шаблоне «Инста-дизайн»...\n"
            "1. Чёрно-белый (чёрный фон)\n"
            "2. Бело-чёрный (белый фон)"
        )

        dark_output = await generate_story_insta(photo_path, title, content, theme="dark")
        with open(dark_output, 'rb') as photo_file:
            await bot.send_photo(chat_id=user_id, photo=photo_file, caption="1. Чёрно-белый (чёрный фон)")

        light_output = await generate_story_insta(photo_path, title, content, theme="light")
        with open(light_output, 'rb') as photo_file:
            await bot.send_photo(chat_id=user_id, photo=photo_file, caption="2. Бело-чёрный (белый фон)")

        for file_path in [photo_path, dark_output, light_output]:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                logging.warning(f"⚠️ Не удалось удалить {file_path}: {e}")

        if user_id in user_data:
            del user_data[user_id]

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('theme_'))
async def process_theme_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    theme = "dark" if callback_query.data == "theme_dark" else "light"
    await callback_query.answer()

    if user_id not in user_data:
        await bot.send_message(user_id, "❌ Начните заново: /start")
        return

    if user_data[user_id].get("step") not in ["waiting_theme", "waiting_highlight_words"]:
        await bot.send_message(user_id, "❌ Начните заново: /start")
        return

    user_data[user_id]["theme"] = theme
    user_data[user_id]["step"] = "waiting_rubric"
    await safe_remove_keyboard(callback_query.message)

    await bot.send_message(
        user_id,
        f"🎨 Тема: {'🌙 Тёмная' if theme == 'dark' else '☀️ Светлая'}\n\n"
        f"📌 Теперь выберите рубрику (или «Без неё»):",
        reply_markup=get_rubric_keyboard()
    )

@dp.callback_query_handler(lambda c: c.data and c.data.startswith('rubric_'))
async def process_rubric_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    raw = callback_query.data.replace('rubric_', '')
    rubric = None if raw == 'none' else raw
    await callback_query.answer()

    if user_id not in user_data:
        await bot.send_message(user_id, "❌ Начните заново: /start")
        return

    if user_data[user_id].get("step") not in ["waiting_rubric", "waiting_theme"]:
        await bot.send_message(user_id, "❌ Начните заново: /start")
        return

    user_data[user_id]["rubric"] = rubric
    user_data[user_id]["step"] = "done"
    await safe_remove_keyboard(callback_query.message)

    photo_path = user_data[user_id].get("photo")
    title = user_data[user_id].get("title")
    content = user_data[user_id].get("content")
    highlight_words = user_data[user_id].get("highlight_words", [])
    theme = user_data[user_id].get("theme", "light")
    template = user_data[user_id].get("template", "classic")

    if not photo_path or not title:
        await bot.send_message(user_id, "❌ Не хватает данных. Начните заново: /start")
        return

    label = "📸 Инста-дизайн" if template == "insta" else f"🎨 Классик / {'тёмная' if theme == 'dark' else 'светлая'}"
    await bot.send_message(
        user_id,
        f"⏳ Генерирую сторис ({label}"
        f"{', рубрика: ' + rubric if rubric else ', без рубрики'})..."
    )
    await process_story(user_id, photo_path, title, content, rubric, highlight_words,
                        callback_query.message, theme, template)

    if user_id in user_data:
        del user_data[user_id]

# ========== ЗАПУСК ==========
async def on_startup(dp):
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        print("✅ Вебхук удален, pending updates сброшены")
    except Exception as e:
        print(f"⚠️ Ошибка удаления вебхука: {e}")

    await asyncio.sleep(3)

    try:
        me = await bot.get_me()
        print(f"✅ Бот: @{me.username} (id={me.id})")
    except Exception as e:
        print(f"⚠️ get_me failed: {e}")

async def on_shutdown(dp):
    try:
        await bot.close()
        print("✅ Сессия бота закрыта")
    except Exception as e:
        print(f"⚠️ Ошибка при закрытии сессии: {e}")

if __name__ == "__main__":
    from aiogram import executor

    print("🚀 Бот запускается...")
    print("⚠️ Убедитесь, что запущен только ОДИН экземпляр бота!")

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            executor.start_polling(
                dp,
                skip_updates=True,
                on_startup=on_startup,
                on_shutdown=on_shutdown,
            )
            break
        except TerminatedByOtherGetUpdates:
            print(f"⚠️ Конфликт getUpdates (попытка {attempt}/{max_attempts}). Ждём 5 секунд...")
            import time
            time.sleep(5)
        except Exception as e:
            print(f"❌ Ошибка при запуске: {e}")
            break
