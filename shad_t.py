import os
from datetime import datetime

class LessonEvent:
    def __init__(self, lesson_number, event_type, time, sound_file):
        self.lesson_number = lesson_number
        self.event_type = event_type  # 'start' или 'end'
        self.time = time  # Время в формате "hh:mm"
        self.sound_file = sound_file
    
    def __repr__(self):
        return f"{self.event_type} {self.lesson_number} {self.time} {self.sound_file}"

def validate_time(time_str):
    try:
        hours, minutes = map(int, time_str.split(':'))
        return 0 <= hours < 24 and 0 <= minutes < 60
    except:
        return False

def time_to_minutes(time_str):
    h, m = map(int, time_str.split(':'))
    return h * 60 + m

def collect_events():
    events = []
    print("Введите данные о уроках. Для завершения введите 'q'")
    
    while True:
        lesson_num = input("\nНомер урока (1-99): ").strip()
        if lesson_num.lower() == 'q':
            break
        
        if not lesson_num.isdigit() or not 1 <= int(lesson_num) <= 99:
            print("Ошибка: номер урока должен быть числом от 1 до 99")
            continue
        
        print(f"\nУрок {lesson_num} - начало:")
        start_time = input("Время начала (hh:mm): ").strip()
        if not validate_time(start_time):
            print("Некорректный формат времени. Используйте hh:mm")
            continue
        
        start_file = input("Путь к звуковому файлу для начала: ").strip()
        if not os.path.exists(os.path.expanduser(start_file)):
            print(f"Файл {start_file} не существует!")
            continue
        
        print(f"\nУрок {lesson_num} - конец:")
        end_time = input("Время окончания (hh:mm): ").strip()
        if not validate_time(end_time):
            print("Некорректный формат времени. Используйте hh:mm")
            continue
        
        if time_to_minutes(end_time) <= time_to_minutes(start_time):
            print("Ошибка: время окончания должно быть позже времени начала")
            continue
        
        end_file = input("Путь к звуковому файлу для окончания: ").strip()
        if not os.path.exists(os.path.expanduser(end_file)):
            print(f"Файл {end_file} не существует!")
            continue
        
        events.append(LessonEvent(lesson_num, "start", start_time, start_file))
        events.append(LessonEvent(lesson_num, "end", end_time, end_file))
        print(f"Урок {lesson_num} успешно добавлен!")
    
    return events

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

def save_events_to_file(events, filename):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            for ev in sorted(events, key=lambda x: (int(x.lesson_number), x.event_type)):
                line = f"{ev.event_type} {ev.lesson_number} {ev.time} {ev.sound_file}\n"
                f.write(line)
        print(f"\nДанные успешно сохранены в файл {filename}")
        return True
    except Exception as e:
        print(f"\nОшибка при сохранении файла: {str(e)}")
        return False

def print_schedule(filename):
    if not os.path.exists(filename):
        print(f"Файл {filename} не существует!")
        return
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            print("\nТекущее расписание:")
            print("="*50)
            print(f"{'Урок':<6}{'Тип':<8}{'Время':<8}{'Звуковой файл'}")
            print("-"*50)
            
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split(maxsplit=3)
                if len(parts) != 4:
                    continue
                
                event_type, lesson_num, time, sound_file = parts
                event_type_ru = "Начало" if event_type == "start" else "Конец "
                print(f"{lesson_num:<6}{event_type_ru:<8}{time:<8}{sound_file}")
            
            print("="*50)
    except Exception as e:
        print(f"Ошибка при чтении файла: {str(e)}")

def main():
    print("Программа составления расписания уроков\n")
    schedule_file = "schedule.txt"
    
    while True:
        print("\nМеню:")
        print("1. Добавить новое расписание")
        print("2. Показать текущее расписание")
        print("3. Выход")
        
        choice = input("Выберите действие (1-3): ").strip()
        
        if choice == '1':
            events = collect_events()
            if not events:
                print("Не введено ни одного урока.")
                continue
            
            is_valid, message = validate_events(events)
            print(f"\nРезультат проверки: {message}")
            
            if is_valid:
                save_events_to_file(events, schedule_file)
        
        elif choice == '2':
            print_schedule(schedule_file)
        
        elif choice == '3':
            print("Выход из программы.")
            break
        
        else:
            print("Некорректный выбор. Попробуйте снова.")

if __name__ == "__main__":
    main()
