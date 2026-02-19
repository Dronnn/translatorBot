from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from bot.lang_codes import LANGUAGE_LABELS, SUPPORTED_LANGUAGES


def build_default_pair_keyboard() -> InlineKeyboardMarkup:
    buttons: list[InlineKeyboardButton] = []
    for src in SUPPORTED_LANGUAGES:
        for dst in SUPPORTED_LANGUAGES:
            if src == dst:
                continue
            label = f"{LANGUAGE_LABELS[src]} -> {LANGUAGE_LABELS[dst]}"
            callback_data = f"setpair:{src}:{dst}"
            buttons.append(InlineKeyboardButton(label, callback_data=callback_data))

    rows: list[list[InlineKeyboardButton]] = []
    row_size = 2
    for i in range(0, len(buttons), row_size):
        rows.append(buttons[i : i + row_size])

    rows.append([InlineKeyboardButton("Auto (all 3 targets)", callback_data="setpair:auto")])
    return InlineKeyboardMarkup(rows)


def build_language_clarification_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(LANGUAGE_LABELS["ru"], callback_data="clarify:ru"),
            InlineKeyboardButton(LANGUAGE_LABELS["en"], callback_data="clarify:en"),
        ],
        [
            InlineKeyboardButton(LANGUAGE_LABELS["de"], callback_data="clarify:de"),
            InlineKeyboardButton(LANGUAGE_LABELS["hy"], callback_data="clarify:hy"),
        ],
    ]
    return InlineKeyboardMarkup(rows)
