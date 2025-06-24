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
SCHEDULE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schedule.txt")
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
def get_cron_path():
    """Определяет путь к crontab пользователя"""
    # Варианты расположения crontab для разных систем
    possible_paths = [
        f"/var/spool/cron/crontabs/{os.getenv('USER')}",  # Ubuntu/Debian
        f"/var/spool/cron/{os.getenv('USER')}",           # CentOS/RHEL
        os.path.expanduser("~/.crontab")                  # Альтернативный вариант
    ]
    
    for path in possible_paths:
        if os.path.exists(os.path.dirname(path)):
            return path
    return None
def check_file_permissions():
    try:
        test_file = SCHEDULE_FILE + '.test'
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        return True
    except:
        return False
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
    """Сохраняет события в файл и автоматически устанавливает cron"""
def save_events(events):
    try:
        logging.info(f"Попытка сохранения {len(events)} событий")
        logging.info(f"Путь к файлу: {os.path.abspath(SCHEDULE_FILE)}")
        logging.info(f"Права на директорию: {oct(os.stat(os.path.dirname(SCHEDULE_FILE)).st_mode)}")
        
        # Полный абсолютный путь
        schedule_path = os.path.abspath(SCHEDULE_FILE)
        os.makedirs(os.path.dirname(schedule_path), exist_ok=True)
        
        # Временный файл для безопасной записи
        temp_path = schedule_path + '.tmp'
        
        lesson_records = {}
        for event in events:
            key = (event.lesson_num, event.event_type)
            lesson_records[key] = event

        with open(temp_path, 'w') as f:
            for key in sorted(lesson_records.keys()):
                event = lesson_records[key]
                line = f"{event.event_type} {event.lesson_num} {event.time} {event.audio_file}\n"
                f.write(line)
        
        # Атомарная замена файла
        if os.path.exists(schedule_path):
            os.remove(schedule_path)
        os.rename(temp_path, schedule_path)
        
        return True
        
    except Exception as e:
        logging.error(f"Ошибка сохранения расписания: {str(e)}", exc_info=True)
        return False

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
#------------------------------>
def install_cron_jobs():
    """Устанавливает задания в crontab с полной диагностикой"""
    try:
        events = load_events()
        if not events:
            return False, "Нет событий для установки"
        
        # Генерируем содержимое cron
        cron_content = generate_cron_jobs(events)
        
        # Сохраняем во временный файл
        with open(CRON_FILE, 'w') as f:
            f.write(cron_content)
        
        # 1. Пробуем стандартную установку
        exit_code = os.system(f"crontab {CRON_FILE} 2>&1")
        if exit_code == 0:
            return True, "Cron успешно установлен"
        
        # 2. Получаем информацию об ошибке
        error = os.popen(f"crontab {CRON_FILE} 2>&1").read()
        
        # 3. Проверяем возможные причины
        if "permission denied" in error.lower():
            # Пробуем через sudo
            username = os.getenv('USER')
            exit_code = os.system(f"sudo crontab -u {username} {CRON_FILE}")
            if exit_code == 0:
                return True, "Cron установлен через sudo"
            else:
                sudo_error = os.popen(f"sudo crontab -u {username} {CRON_FILE} 2>&1").read()
                manual_install = (
                    "Требуются права администратора.\n"
                    "Выполните вручную:\n"
                    f"1. nano {os.path.abspath(CRON_FILE)}\n"
                    f"2. sudo crontab -u {username} {os.path.abspath(CRON_FILE)}"
                )
                return False, f"{sudo_error}\n\n{manual_install}"
        
        elif "no crontab for" in error.lower():
            # Пробуем создать новый crontab
            exit_code = os.system(f"crontab -l >/dev/null 2>&1 || crontab {CRON_FILE}")
            if exit_code == 0:
                return True, "Создан новый crontab"
            else:
                return False, "Не удалось создать crontab"
        
        else:
            # Неизвестная ошибка
            return False, f"Неизвестная ошибка: {error}"
            
    except Exception as e:
        logging.error(f"Cron error: {str(e)}", exc_info=True)
        return False, f"Ошибка: {str(e)}"

#---------------------------------------------------------->
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

@bot.message_handler(commands=['debug_cron'])
def debug_cron(message):
    """Команда для диагностики проблем с cron"""
    try:
        # 1. Проверяем доступность crontab
        crontab_path = os.popen("which crontab").read().strip()
        exists = "✅ Доступен" if crontab_path else "❌ Не установлен"
        
        # 2. Проверяем права
        test_file = "test_cron_job"
        with open(test_file, 'w') as f:
            f.write("* * * * * echo 'test'\n")
        
        exit_code = os.system(f"crontab {test_file} 2>/dev/null")
        permissions = "✅ Есть права" if exit_code == 0 else "❌ Нет прав"
        
        # 3. Пробуем получить текущие задания
        current_jobs = os.popen("crontab -l 2>&1").read()
        if "no crontab" in current_jobs:
            jobs_status = "Нет заданий"
        elif "permission denied" in current_jobs:
            jobs_status = "Ошибка прав доступа"
        else:
            jobs_status = f"{len(current_jobs.splitlines())} заданий"
        
        # 4. Проверяем системный cron.d
        cron_d_status = "✅ Доступен" if os.path.exists("/etc/cron.d") else "❌ Недоступен"
        
        report = (
            "Диагностика cron:\n"
            f"1. crontab: {exists} ({crontab_path})\n"
            f"2. Права: {permissions}\n"
            f"3. Текущие задания: {jobs_status}\n"
            f"4. Системный cron.d: {cron_d_status}"
        )
        
        bot.reply_to(message, report)
        
    except Exception as e:
        bot.reply_to(message, f"Ошибка диагностики: {str(e)}")
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

def is_valid_audio_file(file_info):
    """Проверяет, что файл является аудио"""
    audio_extensions = ['.mp3', '.wav', '.ogg', '.m4a']
    file_ext = os.path.splitext(file_info.file_path)[1].lower()
    return file_ext in audio_extensions

def calculate_end_time(start_time, duration):
    """Вычисляет время окончания урока"""
    h, m = map(int, start_time.split(':'))
    total_minutes = h * 60 + m + duration
    end_h = total_minutes // 60
    end_m = total_minutes % 60
    return f"{end_h:02d}:{end_m:02d}"

def process_start_audio(message):
    try:
        # Проверяем, что прислан аудиофайл или документ
        if not message.audio and not message.document:
            raise ValueError("Пожалуйста, отправьте аудиофайл (MP3, WAV и т.д.)")
            
        # Получаем информацию о файле
        file_info = None
        if message.audio:
            file_info = bot.get_file(message.audio.file_id)
        elif message.document:
            file_info = bot.get_file(message.document.file_id)
            
        if not file_info:
            raise ValueError("Не удалось получить информацию о файле")
            
        # Проверяем тип файла
        if not is_valid_audio_file(file_info):
            raise ValueError("Файл должен быть аудио (MP3, WAV, OGG и т.д.)")
            
        # Скачиваем файл
        downloaded_file = bot.download_file(file_info.file_path)
        if not downloaded_file:
            raise ValueError("Не удалось скачать файл")
            
        # Создаем имя файла
        file_ext = os.path.splitext(file_info.file_path)[1]
        if not file_ext:  # Если нет расширения
            file_ext = '.mp3'  # Устанавливаем по умолчанию
            
        filename = f"start_{current_lessons[message.chat.id]['lesson_num']}{file_ext}"
        filepath = os.path.join(AUDIO_DIR, filename)
        
        # Сохраняем файл
        with open(filepath, 'wb') as f:
            f.write(downloaded_file)
            
        # Обновляем данные урока
        current_lessons[message.chat.id]['start_audio'] = filename
        
        # Вычисляем время окончания
        settings = load_settings()
        duration = settings['lesson_duration']
        start_time = current_lessons[message.chat.id]['start_time']
        end_time = calculate_end_time(start_time, duration)
        
        current_lessons[message.chat.id]['end_time'] = end_time
        
        # Запрашиваем аудио для конца урока
        msg = bot.send_message(
            message.chat.id,
            f"Время окончания урока автоматически установлено: {end_time}\n"
            "Отправьте аудиофайл для звонка на конец урока:"
        )
        bot.register_next_step_handler(msg, process_end_audio)
        
    except Exception as e:
        # Очищаем временные данные при ошибке
        if message.chat.id in current_lessons:
            if 'start_audio' in current_lessons[message.chat.id]:
                audio_file = os.path.join(AUDIO_DIR, current_lessons[message.chat.id]['start_audio'])
                if os.path.exists(audio_file):
                    try:
                        os.remove(audio_file)
                    except:
                        pass
            del current_lessons[message.chat.id]
            
        bot.send_message(message.chat.id, f"Ошибка: {str(e)}")
        start(message)

def process_end_audio(message):
    try:
        # Проверяем, что пользователь действительно отправил аудиофайл
        if not message.audio and not message.document:
            raise ValueError("Пожалуйста, отправьте аудиофайл для звонка на конец урока")

        # Получаем информацию о файле
        file_info = bot.get_file(message.audio.file_id if message.audio else message.document.file_id)
        if not file_info:
            raise ValueError("Не удалось получить информацию о файле")

        # Проверяем расширение файла
        file_ext = os.path.splitext(file_info.file_path)[1]
        if not file_ext:  # Если нет расширения
            file_ext = '.mp3'  # Устанавливаем по умолчанию

        # Скачиваем и сохраняем файл
        downloaded_file = bot.download_file(file_info.file_path)
        filename = f"end_{current_lessons[message.chat.id]['lesson_num']}{file_ext}"
        filepath = os.path.join(AUDIO_DIR, filename)
        
        with open(filepath, 'wb') as f:
            f.write(downloaded_file)

        # Обновляем данные урока
        current_lessons[message.chat.id]['end_audio'] = filename

        # Сохраняем урок в расписание
        lesson_data = current_lessons[message.chat.id]
        events = load_events()

        # Удаляем старые записи для этого урока
        events = [e for e in events if e.lesson_num != lesson_data['lesson_num']]

        # Добавляем новые события
        events.extend([
            LessonEvent(
                lesson_num=lesson_data['lesson_num'],
                event_type='start',
                time=lesson_data['start_time'],
                audio_file=lesson_data['start_audio']
            ),
            LessonEvent(
                lesson_num=lesson_data['lesson_num'],
                event_type='end',
                time=lesson_data['end_time'],
                audio_file=lesson_data['end_audio']
            )
        ])

        # Проверка перед сохранением
        schedule_dir = os.path.dirname(os.path.abspath(SCHEDULE_FILE))
        if not os.path.exists(schedule_dir):
            os.makedirs(schedule_dir, exist_ok=True)
        
        if not os.access(schedule_dir, os.W_OK):
            raise Exception(f"Нет прав на запись в директорию {schedule_dir}")

        if not save_events(events):
            raise Exception("Не удалось сохранить файл расписания")

        # Устанавливаем cron
        success, cron_msg = install_cron_jobs()
        if not success:
            raise Exception(f"Расписание сохранено, но не удалось обновить cron: {cron_msg}")

        # Отправляем подтверждение
        bot.send_message(
            message.chat.id,
            f"✅ Урок {lesson_data['lesson_num']} успешно добавлен!\n"
            f"⏰ Начало: {lesson_data['start_time']} ({lesson_data['start_audio']})\n"
            f"⏰ Конец: {lesson_data['end_time']} ({lesson_data['end_audio']})"
        )

    except Exception as e:
        # В случае ошибки - удаляем сохраненные файлы
        if message.chat.id in current_lessons:
            lesson_data = current_lessons[message.chat.id]
            for file_type in ['start_audio', 'end_audio']:
                if file_type in lesson_data:
                    filepath = os.path.join(AUDIO_DIR, lesson_data[file_type])
                    if os.path.exists(filepath):
                        try:
                            os.remove(filepath)
                        except:
                            pass
            del current_lessons[message.chat.id]
        
        bot.send_message(message.chat.id, f"❌ Ошибка: {str(e)}")
        logging.error(f"Ошибка в process_end_audio: {str(e)}", exc_info=True)
    
    finally:
        start(message)
        
#-----------------Ручная проверка------------------->
@bot.message_handler(commands=['check_permissions'])
def check_permissions(message):
    try:
        schedule_path = os.path.abspath(SCHEDULE_FILE)
        dir_path = os.path.dirname(schedule_path)
        
        checks = [
            ("Директория существует", os.path.exists(dir_path)),
            ("Есть права на запись", os.access(dir_path, os.W_OK)),
            ("Файл расписания существует", os.path.exists(schedule_path)),
            ("Можно создать файл", os.access(dir_path, os.W_OK))
        ]
        
        report = "\n".join([f"{name}: {'✅' if result else '❌'}" for name, result in checks])
        bot.reply_to(message, f"Проверка прав:\n{report}")
        
    except Exception as e:
        bot.reply_to(message, f"Ошибка проверки: {str(e)}")        
        
if __name__ == "__main__":
    print("Бот запущен...")
    bot.infinity_polling()