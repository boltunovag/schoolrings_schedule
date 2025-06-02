import os
import telebot
from telebot import types
from datetime import datetime
import time
from dotenv import load_dotenv

# --- Загрузка переменных окружения ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PASSWORD = os.getenv("BOT_PASSWORD")

bot = telebot.TeleBot(TOKEN)

# --- Конфигурация ---
AUDIO_DIR = "audio_files"
SCHEDULE_FILE = "schedule.txt"
os.makedirs(AUDIO_DIR, exist_ok=True)

# --- Глобальные переменные ---
user_data = {}  # Временное хранилище данных
authorized_users = {}  # Словарь авторизованных пользователей

# --- Классы и функции ---
class LessonEvent:
    def __init__(self, lesson_number, event_type, time, audio_file):
        self.lesson_number = lesson_number
        self.event_type = event_type  # 'start' или 'end'
        self.time = time  # Время в формате "hh:mm"
        self.audio_file = audio_file  # Имя аудиофайла

def validate_time(time_str):
    try:
        hours, minutes = map(int, time_str.split(':'))
        return 0 <= hours < 24 and 0 <= minutes < 60
    except:
        return False

def time_to_minutes(time_str):
    h, m = map(int, time_str.split(':'))
    return h * 60 + m

def save_audio_file(file_id, file_name):
    file_info = bot.get_file(file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    save_path = os.path.join(AUDIO_DIR, file_name)
    with open(save_path, 'wb') as new_file:
        new_file.write(downloaded_file)
    return save_path

def validate_events(events):
    if not events:
        return False, "Список событий пуст"
    
    lesson_numbers = set(ev.lesson_number for ev in events)
    for num in lesson_numbers:
        starts = [e for e in events if e.lesson_number == num and e.event_type == "start"]
        ends = [e for e in events if e.lesson_number == num and e.event_type == "end"]
        if len(starts) != 1 or len(ends) != 1:
            return False, f"Для урока {num} должно быть ровно одно начало и один конец"
    
    sorted_events = sorted(events, key=lambda x: (int(x.lesson_number), x.event_type))
    prev_end_time = 0
    prev_lesson = 0
    
    for ev in sorted_events:
        current_time = time_to_minutes(ev.time)
        current_lesson = int(ev.lesson_number)
        
        if current_lesson == prev_lesson:
            continue
        
        if current_lesson > prev_lesson + 1:
            return False, f"Пропущен урок {prev_lesson + 1}"
        
        if current_lesson > prev_lesson and current_time < prev_end_time:
            return False, (f"Ошибка порядка: урок {current_lesson} (время {ev.time}) "
                          f"не может начинаться раньше окончания урока {prev_lesson}")
        
        if ev.event_type == "end":
            prev_end_time = current_time
            prev_lesson = current_lesson
    
    return True, "Проверка пройдена успешно"

def save_schedule_to_file(events):
    try:
        with open(SCHEDULE_FILE, 'w', encoding='utf-8') as f:
            for ev in sorted(events, key=lambda x: (int(x.lesson_number), x.event_type)):
                line = f"{ev.event_type} {ev.lesson_number} {ev.time} {ev.audio_file}\n"
                f.write(line)
        return True
    except Exception as e:
        print(f"Ошибка при сохранении файла: {str(e)}")
        return False

def load_schedule_from_file():
    if not os.path.exists(SCHEDULE_FILE):
        return []
    
    events = []
    try:
        with open(SCHEDULE_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(maxsplit=3)
                if len(parts) != 4:
                    continue
                event_type, lesson_num, time, audio_file = parts
                events.append(LessonEvent(lesson_num, event_type, time, audio_file))
    except Exception as e:
        print(f"Ошибка при чтении файла: {str(e)}")
    return events

def format_schedule(events):
    if not events:
        return "📭 Расписание пусто."
    
    sorted_events = sorted(events, key=lambda x: (int(x.lesson_number), x.event_type))
    result = "📅 Текущее расписание:\n\n"
    current_lesson = None
    
    for ev in sorted_events:
        if ev.lesson_number != current_lesson:
            result += f"🔔 Урок {ev.lesson_number}:\n"
            current_lesson = ev.lesson_number
        event_type = "🟢 Начало" if ev.event_type == "start" else "🔴 Конец"
        result += f"{event_type} в {ev.time}\n"
    return result

# --- Обработчики команд ---
@bot.message_handler(commands=['start'])
def ask_password(message):
    bot.send_message(message.chat.id, "🔒 Введите пароль для доступа к боту:")
    bot.register_next_step_handler(message, check_password)

def check_password(message):
    if message.text == PASSWORD:
        authorized_users[message.chat.id] = True
        bot.send_message(
            message.chat.id,
            "✅ Пароль верный! Теперь вы можете использовать бота.\n\n"
            "Доступные команды:\n"
            "/add_lesson - Добавить урок\n"
            "/show_schedule - Показать расписание\n"
            "/help - Справка"
        )
    else:
        bot.send_message(message.chat.id, "❌ Неверный пароль! Попробуйте снова /start")

@bot.message_handler(commands=['help'])
def show_help(message):
    if message.chat.id not in authorized_users:
        bot.send_message(message.chat.id, "❌ Сначала введите пароль! /start")
        return
    bot.send_message(
        message.chat.id,
        "📌 Помощь по командам:\n\n"
        "/add_lesson - Добавить новый урок\n"
        "/show_schedule - Показать текущее расписание\n"
        "/help - Эта справка"
    )

@bot.message_handler(commands=['add_lesson'])
def start_adding_lesson(message):
    if message.chat.id not in authorized_users:
        bot.send_message(message.chat.id, "❌ Сначала введите пароль! /start")
        return
    msg = bot.send_message(message.chat.id, "Введите номер урока (1-99):")
    bot.register_next_step_handler(msg, process_lesson_number)

def process_lesson_number(message):
    try:
        lesson_num = message.text.strip()
        if not lesson_num.isdigit() or not 1 <= int(lesson_num) <= 99:
            bot.send_message(message.chat.id, "❌ Номер урока должен быть числом от 1 до 99")
            return
        user_data[message.chat.id] = {'lesson_num': lesson_num}
        msg = bot.send_message(message.chat.id, f"Урок {lesson_num} - начало:\nВведите время начала (hh:mm):")
        bot.register_next_step_handler(msg, process_start_time)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

def process_start_time(message):
    try:
        start_time = message.text.strip()
        if not validate_time(start_time):
            bot.send_message(message.chat.id, "❌ Некорректный формат времени. Используйте hh:mm")
            return
        user_data[message.chat.id]['start_time'] = start_time
        msg = bot.send_message(
            message.chat.id,
            f"Урок {user_data[message.chat.id]['lesson_num']} - начало в {start_time}\n"
            "Отправьте аудиофайл для начала урока:"
        )
        bot.register_next_step_handler(msg, process_start_audio)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

def process_start_audio(message):
    try:
        if not (message.audio or message.voice):
            bot.send_message(message.chat.id, "❌ Отправьте аудиофайл или голосовое сообщение!")
            return
        file_id = message.voice.file_id if message.voice else message.audio.file_id
        file_name = f"lesson_{user_data[message.chat.id]['lesson_num']}_start_{int(time.time())}.ogg"
        save_audio_file(file_id, file_name)
        user_data[message.chat.id]['start_audio'] = file_name
        msg = bot.send_message(
            message.chat.id,
            f"Урок {user_data[message.chat.id]['lesson_num']} - конец:\nВведите время окончания (hh:mm):"
        )
        bot.register_next_step_handler(msg, process_end_time)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

def process_end_time(message):
    try:
        end_time = message.text.strip()
        if not validate_time(end_time):
            bot.send_message(message.chat.id, "❌ Некорректный формат времени. Используйте hh:mm")
            return
        start_time = user_data[message.chat.id]['start_time']
        if time_to_minutes(end_time) <= time_to_minutes(start_time):
            bot.send_message(message.chat.id, "❌ Время окончания должно быть позже времени начала!")
            return
        user_data[message.chat.id]['end_time'] = end_time
        msg = bot.send_message(
            message.chat.id,
            f"Урок {user_data[message.chat.id]['lesson_num']} - конец в {end_time}\n"
            "Отправьте аудиофайл для окончания урока:"
        )
        bot.register_next_step_handler(msg, process_end_audio)
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

def process_end_audio(message):
    try:
        if not (message.audio or message.voice):
            bot.send_message(message.chat.id, "❌ Отправьте аудиофайл или голосовое сообщение!")
            return
        file_id = message.voice.file_id if message.voice else message.audio.file_id
        file_name = f"lesson_{user_data[message.chat.id]['lesson_num']}_end_{int(time.time())}.ogg"
        save_audio_file(file_id, file_name)
        
        # Создаем события
        lesson_num = user_data[message.chat.id]['lesson_num']
        start_event = LessonEvent(
            lesson_num,
            'start',
            user_data[message.chat.id]['start_time'],
            user_data[message.chat.id]['start_audio']
        )
        end_event = LessonEvent(
            lesson_num,
            'end',
            user_data[message.chat.id]['end_time'],
            file_name
        )
        
        # Загружаем и проверяем расписание
        events = load_schedule_from_file()
        events.extend([start_event, end_event])
        is_valid, msg_text = validate_events(events)
        
        if not is_valid:
            bot.send_message(message.chat.id, f"❌ Ошибка: {msg_text}")
            return
        
        if save_schedule_to_file(events):
            bot.send_message(
                message.chat.id,
                f"✅ Урок {lesson_num} успешно добавлен!\n\n"
                f"🟢 Начало: {start_event.time}\n"
                f"🔴 Конец: {end_event.time}"
            )
        else:
            bot.send_message(message.chat.id, "❌ Ошибка при сохранении расписания")
        
        # Очищаем временные данные
        if message.chat.id in user_data:
            del user_data[message.chat.id]
    except Exception as e:
        bot.send_message(message.chat.id, f"⚠️ Ошибка: {str(e)}")

@bot.message_handler(commands=['show_schedule'])
def show_schedule(message):
    if message.chat.id not in authorized_users:
        bot.send_message(message.chat.id, "❌ Сначала введите пароль! /start")
        return
    events = load_schedule_from_file()
    bot.send_message(message.chat.id, format_schedule(events))

# --- Запуск бота ---
if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling()
