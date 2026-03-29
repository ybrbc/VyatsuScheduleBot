def is_admin(user_id: int, secrets) -> bool:
    """
    Проверяет, является ли пользователь администратором.
    user_id — ID пользователя из Telegram.
    secrets — загруженный словарь из secrets.json.
    """
    admin_list = secrets.get("ADMIN_ID", [])
    return str(user_id) in admin_list