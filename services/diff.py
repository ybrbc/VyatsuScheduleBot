def get_diff(previous, current):
    difference = []

    for new_week in current:
        week_diff = {"week": new_week.get("week", ""), "days": []}

        for new_day in new_week.get("days", []):
            date = new_day["date"]
            old_day = None

            for week in previous:
                for d in week.get("days", []):
                    if d["date"] == date:
                        old_day = d
                        break

            day_diff = {"date": date, "schedule": {}}

            for time_slot, subjects in new_day.get("schedule", {}).items():
                old_subjects = set()
                if old_day:
                    old_subjects = set(old_day.get("schedule", {}).get(time_slot, []))

                new_subjects = [s for s in subjects if s not in old_subjects]
                if new_subjects:
                    day_diff["schedule"][time_slot] = new_subjects

            if day_diff["schedule"]:
                week_diff["days"].append(day_diff)

        if week_diff["days"]:
            difference.append(week_diff)

    return difference