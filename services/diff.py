def get_diff(old_text, new_text):
    if not old_text or not new_text:
        return None

    old_lines = set(old_text.splitlines())
    new_lines = set(new_text.splitlines())

    diff = new_lines - old_lines
    return "\n".join(diff)