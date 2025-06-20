import os
import telebot
from telebot import types
import time
from dotenv import load_dotenv
import json
import logging
import re

# --- Настройки ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
bot = telebot.TeleBot(TOKEN)

# Константы
AUDIO_DIR = "audio_files"
SCHEDULE_FILE = "schedule.txt"
CRON_FILE = "audio_schedule.cron"
SETTINGS_FILE = "settings.json"
CRON_BACKUP_FILE = "cron_backup.txt"
os.makedirs(AUDIO_DIR, exist_ok=True)

# --- Класс для событий ---
class LessonEvent:
    def __init__(self, lesson_num, event_type, time, audio_file):
        self.lesson_num = lesson_num
        self.event_type = event_type
        self.time = time
        self.audio_file = audio_file

# --- Логирование ---
logging.basicConfig(
    filename='bot_errors.log',
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filemode='a'
)

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
        logging.error(f"Ошибка загрузки расписания: {str(e)}")
    return events

def save_events(events):
    """Сохраняет события в файл"""
    lesson_records = {}
    
    for event in events:
        key = (event.lesson_num, event.event_type)
        lesson_records[key] = event
    
    with open(SCHEDULE_FILE, 'w') as f:
        for key in sorted(lesson_records.keys()):
            if key[1] == 'start':
                event = lesson_records[key]
                line = f"{event.event_type} {event.lesson_num} {event.time} {event.audio_file}\n"
                f.write(line)
        
        for key in sorted(lesson_records.keys()):
            if key[1] == 'end':
                event = lesson_records[key]
                line = f"{event.event_type} {event.lesson_num} {event.time} {event.audio_file}\n"
                f.write(line)

# --- Работа с настройками ---
def load_settings():
    """Загружает настройки из файла"""
    default_settings = {
        "lesson_duration": 45,
        "cron_paused": False
    }
    try:
        with open(SETTINGS_FILE, 'r') as f:
            return {**default_settings, **json.load(f)}
    except:
        return default_settings

def save_settings(settings):
    """Сохраняет настройки в файл"""
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f)

# --- Работа с cron ---
def generate_cron_jobs(events):
    """Генерирует crontab с абсолютными путями"""
    if not os.path.exists(AUDIO_DIR):
        os.makedirs(AUDIO_DIR, exist_ok=True)
    
    abs_audio_dir = os.path.abspath(AUDIO_DIR)
    cron_log = os.path.join(abs_audio_dir, 'cron.log')
    
    cron_content = "# Аудио расписание\n\n"
    
    for event in sorted(events, key=lambda x: x.time):
        try:
            audio_path = os.path.join(abs_audio_dir, event.audio_file)
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file {audio_path} not found")
            
            hour, minute = event.time.split(':')
            cron_content += (
                f"{minute} {hour} * * 1-5 "
                f"/usr/bin/mpg123 '{audio_path}' "
                f">>{cron_log} 2>&1\n"
            )
        except Exception as e:
            logging.error(f"Error processing event {event.lesson_num}: {str(e)}")
    
    return cron_content

def install_cron_jobs():
    """Устанавливает задания в crontab"""
    try:
        events = load_events()
        if not events:
            return False, "Нет событий для установки"
        
        cron_content = generate_cron_jobs(events)
        with open(CRON_FILE, 'w') as f:
            f.write(cron_content)
        
        exit_code = os.system(f"crontab {CRON_FILE}")
        return exit_code == 0, "Cron-задания успешно установлены!" if exit_code == 0 else "Ошибка установки crontab"
    except Exception as e:
        logging.error(f"Ошибка установки cron: {str(e)}")
        return False, f"Ошибка: {str(e)}"


# --- Команды бота ---
@bot.message_handler(commands=['start'])
def start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    buttons = [
        types.KeyboardButton('/add_lesson'),
        types.KeyboardButton('/show_schedule'),
        types.KeyboardButton('/settings')
    ]
    markup.add(*buttons)
    
    bot.send_message(
        message.chat.id,
        "📅 Бот для управления расписанием\n\n"
        "Доступные команды:\n"
        "/add_lesson - добавить урок\n"
        "/show_schedule - показать расписание\n"
        "/settings - настройки",
        reply_markup=markup
    )


################################Показ расписания##################################################

@bot.message_handler(commands=['show_schedule'])
def show_schedule(message):
    try:
        # Получаем текущие события из нашего расписания
        events = load_events()
        
        if not events:
            bot.send_message(message.chat.id, "Расписание пусто.")
            return
        
        # Группируем события по урокам для удобного отображения
        lessons = {}
        for event in events:
            if event.lesson_num not in lessons:
                lessons[event.lesson_num] = {'start': None, 'end': None}
            
            if event.event_type == 'start':
                lessons[event.lesson_num]['start'] = {
                    'time': event.time,
                    'audio': event.audio_file
                }
            elif event.event_type == 'end':
                lessons[event.lesson_num]['end'] = {
                    'time': event.time,
                    'audio': event.audio_file
                }
        
        # Формируем сообщение с расписанием
        schedule_text = "📅 Текущее расписание:\n\n"
        for lesson_num in sorted(lessons.keys(), key=lambda x: int(x)):
            lesson = lessons[lesson_num]
            schedule_text += (
                f"Урок {lesson_num}:\n"
                f"  🔔 Начало: {lesson['start']['time']} (аудио: {lesson['start']['audio']})\n"
                f"  🔕 Конец: {lesson['end']['time']} (аудио: {lesson['end']['audio']})\n\n"
            )
        
        # Добавляем информацию о cron
        cron_status = get_cron_status()
        schedule_text += f"\nСтатус cron: {cron_status}"
        
        bot.send_message(message.chat.id, schedule_text)
        
    except Exception as e:
        logging.error(f"Ошибка при показе расписания: {str(e)}")
        bot.send_message(message.chat.id, f"Произошла ошибка: {str(e)}")

def get_cron_status():
    """Проверяет статус cron и возвращает текстовое описание"""
    try:
        # Получаем содержимое crontab
        cron_output = os.popen("crontab -l 2>&1").read()
        
        if "no crontab" in cron_output.lower():
            return "Не установлен"
        
        # Проверяем наличие наших записей
        events = load_events()
        if not events:
            return "Установлен (нет наших записей)"
        
        # Подсчитываем наши записи в crontab
        our_entries = 0
        for event in events:
            if f"mpg123 '{os.path.join(os.path.abspath(AUDIO_DIR), event.audio_file)}'" in cron_output:
                our_entries += 1
        
        settings = load_settings()
        if settings.get("cron_paused", False):
            return f"Приостановлен (наших записей: {our_entries}/{len(events)*2})"
        
        return f"Активен (наших записей: {our_entries}/{len(events)*2})"
    
    except Exception as e:
        logging.error(f"Ошибка проверки статуса cron: {str(e)}")
        return "Неизвестен"
################################Конец показа расписания##################################################

@bot.message_handler(commands=['settings'])
def settings_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)
    buttons = [
        types.KeyboardButton('1. Продолжительность урока'),
        types.KeyboardButton('2. Приостановить звонки'),
        types.KeyboardButton('3. Запустить звонки'),
        types.KeyboardButton('/start')
    ]
    markup.add(*buttons)
    
    settings = load_settings()
    status = "приостановлены" if settings["cron_paused"] else "активны"
    
    bot.send_message(
        message.chat.id,
        f"⚙️ Настройки:\n\n"
        f"1. Текущая продолжительность урока: {settings['lesson_duration']} мин\n"
        f"2. Статус звонков: {status}\n\n"
        f"Выберите действие:",
        reply_markup=markup
    )

# Обработчики для меню настроек
@bot.message_handler(func=lambda message: message.text == '1. Продолжительность урока')
def set_lesson_duration(message):
    msg = bot.send_message(message.chat.id, "Сколько минут длится урок? (Введите число от 1 до 120):")
    bot.register_next_step_handler(msg, process_lesson_duration)

def process_lesson_duration(message):
    try:
        duration = int(message.text)
        if not 1 <= duration <= 120:
            raise ValueError("Длительность должна быть от 1 до 120 минут")
            
        settings = load_settings()
        settings["lesson_duration"] = duration
        save_settings(settings)
        
        bot.send_message(message.chat.id, f"✅ Продолжительность урока установлена: {duration} мин")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    finally:
        settings_menu(message)

@bot.message_handler(func=lambda message: message.text == '2. Приостановить звонки')
def pause_cron(message):
    try:
        with open(CRON_BACKUP_FILE, 'w') as f:
            f.write(os.popen("crontab -l").read())
        os.system("crontab -r")
        
        settings = load_settings()
        settings["cron_paused"] = True
        save_settings(settings)
        
        bot.send_message(message.chat.id, "✅ Звонки приостановлены. Cron очищен.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    finally:
        settings_menu(message)

@bot.message_handler(func=lambda message: message.text == '3. Запустить звонки')
def resume_cron(message):
    try:
        if os.path.exists(CRON_BACKUP_FILE):
            os.system(f"crontab {CRON_BACKUP_FILE}")
            status = "восстановлены"
        else:
            install_cron_jobs()
            status = "запущены (новые)"
            
        settings = load_settings()
        settings["cron_paused"] = False
        save_settings(settings)
        
        bot.send_message(message.chat.id, f"✅ Звонки {status}. Cron активирован.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
    finally:
        settings_menu(message)

# ... (остальные существующие функции process_lesson_number, 
# process_start_time, process_start_audio, process_end_time, 
# process_end_audio остаются без изменений)
current_lessons = {}  # Временное хранилище для уроков в процессе добавления

@bot.message_handler(commands=['add_lesson'])
def add_lesson(message):
    msg = bot.send_message(message.chat.id, "Введите номер урока (например, 1):")
    bot.register_next_step_handler(msg, process_lesson_number)

def process_lesson_number(message):
    try:
        lesson_num = message.text.strip()
        if not lesson_num.isdigit():
            raise ValueError("Номер урока должен быть числом")
            
        # Создаем запись для урока
        current_lessons[message.chat.id] = {
            'lesson_num': lesson_num,
            'start': None,
            'end': None
        }
        
        msg = bot.send_message(message.chat.id, f"Урок {lesson_num}. Введите время начала (формат ЧЧ:ММ):")
        bot.register_next_step_handler(msg, process_start_time)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
        start(message)

def process_start_time(message):
    try:
        time_str = message.text.strip()
        # Проверка формата времени
        if not re.match(r'^\d{1,2}:\d{2}$', time_str):
            raise ValueError("Неверный формат времени. Используйте ЧЧ:ММ")
            
        hour, minute = map(int, time_str.split(':'))
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("Некорректное время")
            
        current_lessons[message.chat.id]['start_time'] = time_str
        
        msg = bot.send_message(message.chat.id, "Отправьте аудиофайл для звонка на начало урока:")
        bot.register_next_step_handler(msg, process_start_audio)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
        start(message)

def process_start_audio(message):
    try:
        if not message.audio and not message.document:
            raise ValueError("Пожалуйста, отправьте аудиофайл")
            
        file_info = None
        if message.audio:
            file_info = bot.get_file(message.audio.file_id)
        elif message.document:
            file_info = bot.get_file(message.document.file_id)
            
        if not file_info:
            raise ValueError("Не удалось получить файл")
            
        downloaded_file = bot.download_file(file_info.file_path)
        file_ext = os.path.splitext(file_info.file_path)[1]
        filename = f"start_{current_lessons[message.chat.id]['lesson_num']}{file_ext}"
        filepath = os.path.join(AUDIO_DIR, filename)
        
        with open(filepath, 'wb') as f:
            f.write(downloaded_file)
            
        current_lessons[message.chat.id]['start_audio'] = filename
        
        settings = load_settings()
        duration = settings['lesson_duration']
        
        # Вычисляем время окончания урока
        start_time = current_lessons[message.chat.id]['start_time']
        h, m = map(int, start_time.split(':'))
        end_h = h + (m + duration) // 60
        end_m = (m + duration) % 60
        end_time = f"{end_h:02d}:{end_m:02d}"
        
        current_lessons[message.chat.id]['end_time'] = end_time
        
        msg = bot.send_message(
            message.chat.id,
            f"Время окончания урока автоматически установлено: {end_time}\n"
            "Отправьте аудиофайл для звонка на конец урока:"
        )
        bot.register_next_step_handler(msg, process_end_audio)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
        start(message)

def process_end_audio(message):
    try:
        if not message.audio and not message.document:
            raise ValueError("Пожалуйста, отправьте аудиофайл")
            
        file_info = None
        if message.audio:
            file_info = bot.get_file(message.audio.file_id)
        elif message.document:
            file_info = bot.get_file(message.document.file_id)
            
        if not file_info:
            raise ValueError("Не удалось получить файл")
            
        downloaded_file = bot.download_file(file_info.file_path)
        file_ext = os.path.splitext(file_info.file_path)[1]
        filename = f"end_{current_lessons[message.chat.id]['lesson_num']}{file_ext}"
        filepath = os.path.join(AUDIO_DIR, filename)
        
        with open(filepath, 'wb') as f:
            f.write(downloaded_file)
            
        current_lessons[message.chat.id]['end_audio'] = filename
        
        # Сохраняем урок в расписание
        lesson_data = current_lessons[message.chat.id]
        events = load_events()
        
        events.append(LessonEvent(
            lesson_num=lesson_data['lesson_num'],
            event_type='start',
            time=lesson_data['start_time'],
            audio_file=lesson_data['start_audio']
        ))
        
        events.append(LessonEvent(
            lesson_num=lesson_data['lesson_num'],
            event_type='end',
            time=lesson_data['end_time'],
            audio_file=lesson_data['end_audio']
        ))
        
        save_events(events)
        
        bot.send_message(
            message.chat.id,
            f"✅ Урок {lesson_data['lesson_num']} добавлен в расписание!\n"
            f"Начало: {lesson_data['start_time']}\n"
            f"Окончание: {lesson_data['end_time']}"
        )
        
        # Удаляем временные данные
        del current_lessons[message.chat.id]
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
    finally:
        start(message)
        
if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling()