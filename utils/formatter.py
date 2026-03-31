days_of_week = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")

def format_output(raw_output):
    formatted_output = ""
    for week in raw_output:
        itr = 0
        for day in week.get("days", []):
            formatted_output += day["date"] + " - " + days_of_week[itr] + "\n"
            for time_slot, subjects in day.get("schedule", {}).items():
                for subject in subjects:
                    formatted_output += f"  {time_slot} - {subject}\n"
            formatted_output += "\n"
            itr += 1
    return formatted_output