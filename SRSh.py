import os
import telebot
from telebot import types
import time
from dotenv import load_dotenv

# --- Настройки ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

AUDIO_DIR = "audio_files"
SCHEDULE_FILE = "schedule.txt"
CRON_FILE = "audio_schedule.cron"
os.makedirs(AUDIO_DIR, exist_ok=True)

# --- Класс для событий ---
class LessonEvent:
    def __init__(self, lesson_num, event_type, time, audio_file):
        self.lesson_num = lesson_num
        self.event_type = event_type  # 'start' или 'end'
        self.time = time  # 'hh:mm'
        self.audio_file = audio_file  # имя файла

# --- Работа с расписанием ---
def load_events():
    """Загружает события из файла"""
    events = []
    if not os.path.exists(SCHEDULE_FILE):
        return events
        
    try:
        with open(SCHEDULE_FILE, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 4:
                    event_type, lesson_num, time, audio_file = parts
                    events.append(LessonEvent(lesson_num, event_type, time, audio_file))
    except Exception as e:
        print(f"Ошибка загрузки: {str(e)}")
    return events

def save_events(events):
    """Сохраняет события в файл"""
    with open(SCHEDULE_FILE, 'w') as f:
        for event in events:
            line = f"{event.event_type} {event.lesson_num} {event.time} {event.audio_file}\n"
            f.write(line)

# --- Работа с cron ---
def generate_cron_content(events):
    """Генерирует содержимое cron-файла с проверкой дубликатов"""
    content = "# Аудио расписание\n\n"
    added_lessons = set()  # Для отслеживания добавленных уроков
    
    for event in sorted(events, key=lambda x: (x.lesson_num, x.event_type)):
        if event.event_type == "start":
            # Нормализуем время (08:30 -> 8:30)
            hour, minute = map(int, event.time.split(':'))
            time_key = f"{hour}:{minute:02d}"
            
            # Проверяем, не добавляли ли уже этот урок
            if event.lesson_num not in added_lessons:
                audio_path = os.path.join(AUDIO_DIR, event.audio_file)
                content += f"{minute} {hour} * * 1-5 /usr/bin/mpg123 '{audio_path}' >/dev/null 2>&1\n"
                added_lessons.add(event.lesson_num)
    
    return content



def install_cron_jobs():
    """Устанавливает задания в crontab с очисткой старых"""
    try:
        events = load_events()
        if not events:
            return False, "Нет событий для установки"
        
        # Генерируем новое содержимое
        cron_content = generate_cron_content(events)
        
        # Создаем временный файл
        temp_cron = "temp_cron"
        with open(temp_cron, 'w') as f:
            f.write(cron_content)
        
        # Устанавливаем новый crontab (перезаписываем полностью)
        exit_code = os.system(f"crontab {temp_cron}")
        
        # Удаляем временный файл
        os.remove(temp_cron)
        
        if exit_code == 0:
            return True, "Cron-задания успешно обновлены!"
        else:
            return False, "Ошибка установки crontab"
    except Exception as e:
        return False, f"Ошибка: {str(e)}"


# --- Команды бота ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id,
        "📅 Бот для расписания аудиоуроков\n\n"
        "Доступные команды:\n"
        "/add_lesson - добавить урок\n"
        "/show_schedule - показать расписание\n"
        "/install_cron - установить cron-задания\n"
        "/help - справка"
    )

@bot.message_handler(commands=['help'])
def help(message):
    bot.send_message(
        message.chat.id,
        "ℹ️ Справка по командам:\n\n"
        "/add_lesson - добавить новый урок\n"
        "/show_schedule - показать текущее расписание\n"
        "/install_cron - установить задания в crontab\n"
        "/help - эта справка"
    )

@bot.message_handler(commands=['show_schedule'])
def show_schedule(message):
    events = load_events()
    if not events:
        bot.send_message(message.chat.id, "Расписание пусто.")
        return
    
    response = "📅 Текущее расписание:\n\n"
    for event in sorted(events, key=lambda x: (x.lesson_num, x.event_type)):
        response += f"Урок {event.lesson_num}: {'Начало' if event.event_type == 'start' else 'Конец'} в {event.time}\n"
    
    bot.send_message(message.chat.id, response)

@bot.message_handler(commands=['install_cron'])
def handle_install_cron(message):
    success, result = install_cron_jobs()
    if success:
        with open(CRON_FILE, 'rb') as f:
            bot.send_document(
                message.chat.id,
                f,
                caption=f"✅ {result}\n\n"
                       "Содержимое crontab:"
            )
    else:
        bot.send_message(message.chat.id, f"❌ {result}")

# --- Добавление урока ---
@bot.message_handler(commands=['add_lesson'])
def add_lesson(message):
    msg = bot.send_message(message.chat.id, "Введите номер урока:")
    bot.register_next_step_handler(msg, process_lesson_number)

def process_lesson_number(message):
    try:
        lesson_num = message.text.strip()
        if not lesson_num.isdigit():
            raise ValueError("Номер урока должен быть числом")
            
        msg = bot.send_message(message.chat.id, f"Урок {lesson_num}. Введите время начала (hh:mm):")
        bot.register_next_step_handler(msg, process_start_time, lesson_num)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

def process_start_time(message, lesson_num):
    try:
        start_time = message.text.strip()
        if ':' not in start_time or len(start_time.split(':')) != 2:
            raise ValueError("Неверный формат времени. Используйте hh:mm")
            
        msg = bot.send_message(message.chat.id, "Отправьте аудиофайл для начала урока:")
        bot.register_next_step_handler(msg, process_start_audio, lesson_num, start_time)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

def process_start_audio(message, lesson_num, start_time):
    try:
        if not (message.audio or message.voice):
            raise ValueError("Отправьте аудиофайл или голосовое сообщение")
            
        file_id = message.voice.file_id if message.voice else message.audio.file_id
        file_ext = "ogg" if message.voice else "mp3"
        file_name = f"lesson_{lesson_num}_start_{int(time.time())}.{file_ext}"
        
        # Сохраняем аудиофайл
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open(os.path.join(AUDIO_DIR, file_name), 'wb') as f:
            f.write(downloaded_file)
            
        # Сохраняем событие начала
        events = load_events()
        events.append(LessonEvent(lesson_num, "start", start_time, file_name))
        
        msg = bot.send_message(message.chat.id, f"Введите время окончания урока {lesson_num} (hh:mm):")
        bot.register_next_step_handler(msg, process_end_time, lesson_num, events)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

def process_end_time(message, lesson_num, events):
    try:
        end_time = message.text.strip()
        if ':' not in end_time or len(end_time.split(':')) != 2:
            raise ValueError("Неверный формат времени. Используйте hh:mm")
            
        msg = bot.send_message(message.chat.id, "Отправьте аудиофайл для окончания урока:")
        bot.register_next_step_handler(msg, process_end_audio, lesson_num, end_time, events)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

def process_end_audio(message, lesson_num, end_time, events):
    try:
        if not (message.audio or message.voice):
            raise ValueError("Отправьте аудиофайл или голосовое сообщение")
            
        file_id = message.voice.file_id if message.voice else message.audio.file_id
        file_ext = "ogg" if message.voice else "mp3"
        file_name = f"lesson_{lesson_num}_end_{int(time.time())}.{file_ext}"
        
        # Сохраняем аудиофайл
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        with open(os.path.join(AUDIO_DIR, file_name), 'wb') as f:
            f.write(downloaded_file)
            
        # Сохраняем событие окончания
        events.append(LessonEvent(lesson_num, "end", end_time, file_name))
        save_events(events)
        
        bot.send_message(
            message.chat.id,
            f"✅ Урок {lesson_num} успешно добавлен!\n"
            f"Начало: {events[-2].time}\n"
            f"Окончание: {end_time}"
        )
        
        # Предлагаем установить cron
        bot.send_message(
            message.chat.id,
            "Хотите установить расписание в cron? Отправьте /install_cron"
        )
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")

if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling()
