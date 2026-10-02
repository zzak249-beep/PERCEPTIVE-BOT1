import html
import logging

import requests

from config import cfg

log = logging.getLogger("telegram")


def esc(s):
    return html.escape(str(s))


def send(text):
    if not (cfg.TELEGRAM_TOKEN and cfg.TELEGRAM_CHAT_ID):
        log.info("TG (sin config): %s", text)
        return
    url = f"https://api.telegram.org/bot{cfg.TELEGRAM_TOKEN}/sendMessage"
    for chunk in [text[i:i + 3900] for i in range(0, len(text), 3900)] or [""]:
        try:
            r = requests.post(url, json={"chat_id": cfg.TELEGRAM_CHAT_ID, "text": chunk,
                                         "parse_mode": "HTML",
                                         "disable_web_page_preview": True}, timeout=15)
            if r.status_code != 200:
                log.warning("Telegram %s: %s", r.status_code, r.text[:200])
        except Exception as e:
            log.warning("Telegram error: %s", e)
