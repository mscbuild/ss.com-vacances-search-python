import requests
import csv
import time
from bs4 import BeautifulSoup

BASE_URL = "https://www.ss.com"
START_URL = "https://www.ss.com/ru/work/are-required/programmer/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

def get_soup(url):
    response = requests.get(url, headers=HEADERS)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")

def get_vacancy_links(page_url):
    soup = get_soup(page_url)
    links = []

    for a in soup.select("a[href*='/msg/']"):
        link = BASE_URL + a["href"]
        if link not in links:
            links.append(link)

    return links

def parse_vacancy(url):
    soup = get_soup(url)

    def safe_text(selector):
        tag = soup.select_one(selector)
        return tag.get_text(strip=True) if tag else ""

    title = safe_text("h2")
    description = safe_text("div#msg_div_msg")
    city = ""
    salary = ""

    for row in soup.select("tr"):
        if "Город" in row.get_text():
            city = row.get_text(strip=True)
        if "Зарплата" in row.get_text():
            salary = row.get_text(strip=True)

    return {
        "Название": title,
        "Город": city,
        "Зарплата": salary,
        "Описание": description,
        "Ссылка": url
    }

def get_all_pages(start_url):
    soup = get_soup(start_url)
    pages = [start_url]

    for a in soup.select("a[href*='page']"):
        link = BASE_URL + a["href"]
        if link not in pages:
            pages.append(link)

    return pages

def main():
    print("🔍 Поиск страниц...")
    pages = get_all_pages(START_URL)

    all_links = []
    for page in pages:
        print(f"📄 Страница: {page}")
        links = get_vacancy_links(page)
        all_links.extend(links)
        time.sleep(1)

    all_links = list(set(all_links))
    print(f"🔗 Найдено объявлений: {len(all_links)}")

    vacancies = []
    for i, link in enumerate(all_links, 1):
        print(f"📌 [{i}/{len(all_links)}] {link}")
        try:
            vacancy = parse_vacancy(link)
            vacancies.append(vacancy)
            time.sleep(1)
        except Exception as e:
            print("Ошибка:", e)

    with open("vacancies_programmer_ss.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["Название", "Город", "Зарплата", "Описание", "Ссылка"]
        )
        writer.writeheader()
        writer.writerows(vacancies)

    print("✅ Данные сохранены в vacancies_programmer_ss.csv")

if __name__ == "__main__":
    main()
