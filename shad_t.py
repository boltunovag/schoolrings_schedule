import datetime
from random import randint

class ScheduleItem:
    def __init__(self, number, flag, time):
        self.number = number
        self.flag = flag
        self.time = time  # Ожидается datetime.time или строка "чч:мм"

    def __str__(self):
        time_str = self.time.strftime("%H:%M") if isinstance(self.time, datetime.time) else self.time
        return f"| {self.number:2} | {str(self.flag):5} | {time_str} |"

def create_schedule():
    schedule = []
    for number in range(1, 11):  # Номера от 1 до 10
        # Добавляем два объекта для каждого номера: один с False, другой с True
        time_false = datetime.time(randint(8, 12), 0)  # Случайное время утра
        time_true = datetime.time(randint(13, 18), 0)   # Случайное время дня
        
        schedule.append(ScheduleItem(number, False, time_false))
        schedule.append(ScheduleItem(number, True, time_true))
    return schedule

def print_schedule(schedule):
    print("+" + "-" * 6 + "+" + "-" * 7 + "+" + "-" * 7 + "+")
    print("| Номер | Признак | Время |")
    print("+" + "-" * 6 + "+" + "-" * 7 + "+" + "-" * 7 + "+")
    for item in schedule:
        print(item)
    print("+" + "-" * 6 + "+" + "-" * 7 + "+" + "-" * 7 + "+")

if __name__ == "__main__":
    schedule = create_schedule()
    print_schedule(schedule)

