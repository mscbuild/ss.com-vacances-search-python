import threading
import time
import tkinter as tk
from parser import get_all_links, parse_vacancy
from telegram_bot import send_message
from storage import load_sent_links, save_sent_link, save_csv

sent_links = load_sent_links()
vacancies = []

def check_vacancies():
    global vacancies
    links = get_all_links()

    for link in links:
        if link in sent_links:
            continue

        title, salary, url = parse_vacancy(link)
        sent_links.add(link)
        save_sent_link(link)

        vacancies.append((title, salary, url))

        send_message(
            f"💼 {title}\n💰 {salary}\n{url}"
        )

def auto_check():
    while True:
        check_vacancies()
        time.sleep(1800)

threading.Thread(target=auto_check, daemon=True).start()

root = tk.Tk()
root.title("Job Monitor")

btn = tk.Button(root, text="Сохранить CSV",
                command=lambda: save_csv(vacancies))
btn.pack(padx=20, pady=20)

root.mainloop()
