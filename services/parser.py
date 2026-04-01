from datetime import datetime
import camelot
import json

class Day:
    def __init__(self, date: datetime):
        self.date = date
        self.schedule = {}

    def add_lesson(self, time_slot: str, subject: str):
        if not time_slot or not subject:
            return
        # Инициализируем список, если впервые
        self.schedule.setdefault(time_slot, []).append(subject)

    def to_dict(self):
        return {
            "date": self.date.strftime("%d.%m.%Y"),
            "schedule": self.schedule
        }


# Извлечение текста из PDF
def extract_text_from_pdf(file_path, filename):

    days_in_week = ("понедельник", "вторник", "среда", "четверг",
                    "пятница", "суббота", "воскресенье")

    def parse_day_string(day_str: str):
        parts = day_str.strip().split()
        if len(parts) >= 2:
            date_str = parts[-1]
            return datetime.strptime(date_str, "%d.%m.%y")
        return None
    try:
        tables = camelot.read_pdf(file_path, pages="1-end", flavor="lattice")
    except Exception as e:
        print(f"Ошибка парсинга PDF: {e}")
        return None
    days = []
    current_day = None
    last_time = None

    for table in tables:
        for raw_row in table.df.values.tolist():
            # чистим переносы строк
            row = [cell.replace('\n', ' ').strip() for cell in raw_row]
            day_cell, time_cell, subj_cell = row[0], row[1], row[2]

            # Начало нового дня
            if isinstance(day_cell, str) and day_cell.lower().startswith(days_in_week):
                # Сохраняем предыдущий день
                if current_day:
                    days.append(current_day.to_dict())
                # Новый объект Day
                date = parse_day_string(day_cell)
                current_day = Day(date)
                # Если есть время — обновляем last_time и добавляем пару
                if time_cell:
                    last_time = time_cell
                    current_day.add_lesson(last_time, subj_cell)
            # Продолжение того же дня
            elif current_day:
                # Если новая временная метка — обновляем
                if time_cell:
                    last_time = time_cell
                    # сразу добавляем, если есть
                    current_day.add_lesson(last_time, subj_cell)
                else:
                    # пустая ячейка времени — значит дополнительная пара к last_time
                    if last_time:
                        current_day.add_lesson(last_time, subj_cell)

    # Сохраняем последний день
    if current_day:
        days.append(current_day.to_dict())

    # Разбивка на две недели, если нужно
    if len(days) >= 14:
        # 7 дней в неделю
        week1 = days[:7]
        week2 = days[7:14]
        output = [
            {"week": f"{week1[0]['date']}-{week1[-1]['date']}", "days": week1},
            {"week": f"{week2[0]['date']}-{week2[-1]['date']}", "days": week2}
        ]
    else:
        output = [{"days": days}]
    with open(f"storage/parsed/{filename}", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output


def load_schedule_from_json(file_name):
    file_path = f"storage/parsed/{file_name}"
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except FileNotFoundError:
        print(f"Файл не найден: {file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"Ошибка чтения JSON: {e}")
        return None