"""The request sent to the models."""

from .tasks import Task

TEMPLATE = {
    "en": (
        "Write Ruby code for the task below. Start with a Gemfile that lists every gem the code needs, "
        "then give the implementation.\n\nTask: {task}"
    ),
    "uk": (
        "Напишіть код на Ruby для наведеного нижче завдання. Почніть із Gemfile, у якому перелічено всі геми, "
        "потрібні коду, а потім наведіть реалізацію.\n\nЗавдання: {task}"
    ),
}


def messages(task: Task, lang: str) -> list[dict]:
    return [{"role": "user", "content": TEMPLATE[lang].format(task=task.text[lang])}]
