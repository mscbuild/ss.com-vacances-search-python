import requests
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re
import time

import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import plotly.express as px


# ============================================================
# НАСТРОЙКИ
# ============================================================

BASE_URL = "https://www.ss.com"

# Используем мобильную версию.
# Она намного проще для разбора.
START_URL = "https://m.ss.com/lv/work/are-required/today/"

UPDATE_INTERVAL_MS = 5 * 60 * 1000  # 5 минут

# Максимальное количество страниц
MAX_PAGES = 160

# Фильтры
TARGET_LOCATION = "jelgava"
TARGET_WORK_DAYS = "darbadienas"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10; K) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "lv-LV,lv;q=0.9,ru;q=0.8,en;q=0.7",
}


# ============================================================
# SESSION
# ============================================================

def create_session():

    session = requests.Session()

    session.headers.update(
        HEADERS
    )

    return session


# ============================================================
# ОЧИСТКА ТЕКСТА
# ============================================================

def clean_text(text):

    if not text:
        return ""

    text = text.replace(
        "\xa0",
        " "
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def normalize(text):

    return clean_text(
        text
    ).lower()


# ============================================================
# ЗАГРУЗКА СТРАНИЦЫ
# ============================================================

def get_soup(
    session,
    url
):

    try:

        response = session.get(
            url,
            timeout=20
        )

        print(
            f"HTTP {response.status_code}: {url}"
        )

        if response.status_code != 200:
            return None

        response.encoding = (
            response.apparent_encoding
            or "utf-8"
        )

        return BeautifulSoup(
            response.text,
            "html.parser"
        )

    except Exception as e:

        print(
            f"❌ Ошибка загрузки: {e}"
        )

        return None


# ============================================================
# ОПРЕДЕЛЕНИЕ ВРЕМЕНИ
# ============================================================

TIME_PATTERNS = [

    # 8:00-17:00
    r"\b\d{1,2}[:.]\d{2}\s*[-–—]\s*\d{1,2}[:.]\d{2}\b",

    # 8-17
    r"\b\d{1,2}\s*[-–—]\s*\d{1,2}\b",

    # 8:00 - 17
    r"\b\d{1,2}[:.]\d{2}\s*[-–—]\s*\d{1,2}\b",

]


def extract_time(text):

    text = clean_text(
        text
    )

    for pattern in TIME_PATTERNS:

        match = re.search(
            pattern,
            text
        )

        if match:
            return match.group(0)

    return ""


# ============================================================
# РАБОЧИЕ ДНИ
# ============================================================

def is_work_days(text):

    text = normalize(
        text
    )

    # SS.COM использует:
    # Darbadienas = Рабочие дни

    return (
        "darbadienas" in text
        or
        "darba dienas" in text
        or
        "рабочие" in text
        or
        "рабочие дни" in text
    )


# ============================================================
# ЕЛГАВА
# ============================================================

def is_jelgava(text):

    text = normalize(
        text
    )

    # Подойдут:
    #
    # Jelgava un raj., Jelgava
    # Jelgava un raj., Ozolnieku pag.
    # Jelgava un raj., Cenu pag.
    #
    # Не подойдут:
    #
    # Dobele un raj.
    # Rīga
    # Bauska un raj.

    return (
        "jelgava un raj." in text
        or
        "jelgava un raj" in text
    )


# ============================================================
# ПОИСК КОНТЕЙНЕРА ОБЪЯВЛЕНИЯ
# ============================================================

def find_ad_container(link):

    """
    Ищем ближайший HTML-контейнер,
    который относится только к одному объявлению.

    Не используем:
        soup.find_all("tr")

    потому что мобильная версия SS.COM
    не обязана хранить объявления в <tr>.
    """

    current = link

    for _ in range(10):

        current = current.parent

        if current is None:
            break

        # Сколько ссылок /msg/ внутри
        msg_links = current.select(
            "a[href*='/msg/']"
        )

        # Нам нужен контейнер ровно одного объявления
        if len(msg_links) == 1:

            text = clean_text(
                current.get_text(
                    " ",
                    strip=True
                )
            )

            # Контейнер объявления обычно содержит
            # местонахождение или рабочие дни.
            if (
                "Jelgava" in text
                or
                "Darbadienas" in text
                or
                "Jaukti" in text
                or
                "Maiņās" in text
                or
                "Pēc izvēles" in text
            ):
                return current

    return None


# ============================================================
# РАЗБОР ОДНОГО ОБЪЯВЛЕНИЯ
# ============================================================

def parse_ad(link):

    title = clean_text(
        link.get_text(
            " ",
            strip=True
        )
    )

    href = link.get(
        "href",
        ""
    )

    if not href:
        return None

    url = urljoin(
        "https://m.ss.com",
        href
    )

    container = find_ad_container(
        link
    )

    if container is None:
        return None

    # --------------------------------------------------------
    # Получаем текстовые элементы
    # --------------------------------------------------------

    parts = []

    for element in container.stripped_strings:

        text = clean_text(
            element
        )

        if text and text not in parts:

            parts.append(
                text
            )

    if not parts:
        return None

    full_text = " | ".join(
        parts
    )

    # --------------------------------------------------------
    # МЕСТОНАХОЖДЕНИЕ
    # --------------------------------------------------------

    location = ""

    for part in parts:

        if is_jelgava(
            part
        ):

            location = part

            break

    if not location:
        return None

    # --------------------------------------------------------
    # РАБОЧИЕ ДНИ
    # --------------------------------------------------------

    work_days = ""

    for part in parts:

        if is_work_days(
            part
        ):

            work_days = part

            break

    if not work_days:
        return None

    # --------------------------------------------------------
    # ВРЕМЯ РАБОТЫ
    # --------------------------------------------------------

    work_time = ""

    # Сначала проверяем отдельные элементы
    for part in parts:

        time_value = extract_time(
            part
        )

        if time_value:

            work_time = time_value

            break

    # --------------------------------------------------------
    # ПРОФЕССИЯ
    #
    # На SS.COM обычно идёт:
    #
    # название
    # местонахождение
    # профессия
    # рабочие дни
    # время
    #
    # Поэтому ищем элемент после location
    # и перед work_days.
    # --------------------------------------------------------

    profession = ""

    try:

        location_index = parts.index(
            location
        )

    except ValueError:

        location_index = -1

    if location_index >= 0:

        for i in range(
            location_index + 1,
            len(parts)
        ):

            part = parts[i]

            if part == work_days:
                break

            if part == work_time:
                continue

            if extract_time(part):
                continue

            # Не берём слишком длинные куски
            # как профессию.
            if len(part) <= 80:

                profession = part

                break

    # --------------------------------------------------------
    # ВАЖНО:
    #
    # Название вакансии берём ТОЛЬКО из <a>.
    #
    # Поэтому не получится:
    #
    # Palīgstrādnieki ... Palīgstrādnieki
    #
    # Профессия хранится отдельно.
    # --------------------------------------------------------

    if not title:

        title = "Без названия"

    return {

        "Название вакансии": title,

        "Местонахождение": location,

        "Профессия": profession,

        "Дни работы": work_days,

        "Время работы": work_time,

        "Ссылка": url,
    }


# ============================================================
# СЛЕДУЮЩАЯ СТРАНИЦА
# ============================================================

def get_next_page(
    soup,
    current_url
):

    if soup is None:
        return None

    # --------------------------------------------------------
    # На мобильной версии SS.COM есть ссылка
    # "Nākamie" = Следующие.
    # --------------------------------------------------------

    for link in soup.find_all(
        "a",
        href=True
    ):

        text = clean_text(
            link.get_text(
                " ",
                strip=True
            )
        )

        if text.lower() in [
            "nākamie",
            "следующие",
            "next",
        ]:

            return urljoin(
                current_url,
                link["href"]
            )

    # --------------------------------------------------------
    # Запасной вариант:
    # page2.html, page3.html...
    # --------------------------------------------------------

    match = re.search(
        r"/page(\d+)\.html",
        current_url
    )

    if match:

        current_page = int(
            match.group(1)
        )

        next_page = (
            current_page + 1
        )

        return (
            "https://m.ss.com/"
            "lv/work/are-required/"
            f"today/page{next_page}.html"
        )

    return (
        "https://m.ss.com/"
        "lv/work/are-required/"
        "today/page2.html"
    )


# ============================================================
# СБОР ВАКАНСИЙ
# ============================================================

def fetch_vacancies():

    print()
    print("=" * 70)
    print(
        "SS.COM — МОНИТОРИНГ ВАКАНСИЙ"
    )
    print("=" * 70)

    print(
        "Местонахождение: ТОЛЬКО ЕЛГАВА"
    )

    print(
        "Дни работы: РАБОЧИЕ"
    )

    print(
        "Специальность: ВСЕ"
    )

    print(
        f"Старт: {START_URL}"
    )

    print("=" * 70)

    session = create_session()

    current_url = START_URL

    visited = set()

    vacancies = []

    for page_number in range(
        1,
        MAX_PAGES + 1
    ):

        if not current_url:
            break

        if current_url in visited:

            print(
                "⚠️ Страница уже обработана."
            )

            break

        visited.add(
            current_url
        )

        print()
        print("=" * 70)

        print(
            f"СТРАНИЦА {page_number}"
        )

        print(
            current_url
        )

        print("=" * 70)

        soup = get_soup(
            session,
            current_url
        )

        if soup is None:
            break

        # ----------------------------------------------------
        # Ищем все ссылки на объявления
        # ----------------------------------------------------

        links = soup.select(
            "a[href*='/msg/']"
        )

        print(
            f"Найдено ссылок на объявления: "
            f"{len(links)}"
        )

        page_found = 0

        seen_links = set()

        for link in links:

            href = link.get(
                "href",
                ""
            )

            if not href:
                continue

            full_url = urljoin(
                "https://m.ss.com",
                href
            )

            # Дубликаты ссылок
            if full_url in seen_links:
                continue

            seen_links.add(
                full_url
            )

            # ------------------------------------------------
            # Разбираем объявление
            # ------------------------------------------------

            try:

                ad = parse_ad(
                    link
                )

            except Exception as e:

                print(
                    f"Ошибка разбора объявления: {e}"
                )

                continue

            if not ad:
                continue

            # ------------------------------------------------
            # ФИЛЬТР ЕЛГАВА
            # ------------------------------------------------

            if not is_jelgava(
                ad["Местонахождение"]
            ):
                continue

            # ------------------------------------------------
            # ФИЛЬТР РАБОЧИЕ ДНИ
            # ------------------------------------------------

            if not is_work_days(
                ad["Дни работы"]
            ):
                continue

            vacancies.append(
                ad
            )

            page_found += 1

        print(
            f"Подходящих вакансий: "
            f"{page_found}"
        )

        print(
            f"Всего найдено: "
            f"{len(vacancies)}"
        )

        # ----------------------------------------------------
        # Следующая страница
        # ----------------------------------------------------

        next_url = get_next_page(
            soup,
            current_url
        )

        if not next_url:
            break

        if next_url in visited:

            print(
                "⚠️ Следующая ссылка ведёт "
                "на уже обработанную страницу."
            )

            break

        current_url = next_url

        # Пауза
        time.sleep(
            0.3
        )

    # ========================================================
    # DATAFRAME
    # ========================================================

    columns = [

        "Название вакансии",

        "Местонахождение",

        "Профессия",

        "Дни работы",

        "Время работы",

        "Ссылка",
    ]

    if not vacancies:

        print()
        print(
            "❌ Вакансий в Елгаве "
            "с фильтром 'Рабочие дни' не найдено."
        )

        return pd.DataFrame(
            columns=columns
        )

    df = pd.DataFrame(
        vacancies
    )

    # --------------------------------------------------------
    # Удаляем дубликаты
    # --------------------------------------------------------

    df = df.drop_duplicates(
        subset=["Ссылка"]
    )

    # --------------------------------------------------------
    # Удаляем дубли внутри названия
    # --------------------------------------------------------

    for index in df.index:

        title = clean_text(
            df.at[
                index,
                "Название вакансии"
            ]
        )

        profession = clean_text(
            df.at[
                index,
                "Профессия"
            ]
        )

        # Если профессия случайно продублировалась
        # в начале названия — удаляем её.
        if (
            profession
            and
            title.lower().startswith(
                profession.lower()
                + " "
            )
        ):

            title = title[
                len(profession):
            ].strip(
                " -–—:,"
            )

        df.at[
            index,
            "Название вакансии"
        ] = title

    # --------------------------------------------------------
    # Сортировка
    # --------------------------------------------------------

    df = df.sort_values(
        by=[
            "Профессия",
            "Название вакансии"
        ],
        na_position="last"
    )

    df = df.reset_index(
        drop=True
    )

    print()
    print("=" * 70)

    print(
        f"ИТОГО УНИКАЛЬНЫХ ВАКАНСИЙ: "
        f"{len(df)}"
    )

    print("=" * 70)

    return df


# ============================================================
# DASH APP
# ============================================================

app = dash.Dash(
    __name__
)

app.title = (
    "SS.COM — вакансии Елгавы"
)


app.layout = html.Div(

    style={
        "width": "96%",
        "margin": "auto",
        "fontFamily": "Arial",
    },

    children=[

        html.H1(
            "💼 SS.COM — вакансии Елгавы",
            style={
                "textAlign": "center"
            }
        ),

        html.Div(
            "📍 Местонахождение: ЕЛГАВА | "
            "📅 Дни работы: РАБОЧИЕ | "
            "💼 Специальность: ВСЕ",

            style={
                "textAlign": "center",
                "fontSize": "18px",
                "fontWeight": "bold",
                "marginBottom": "20px",
            }
        ),

        html.Div(
            id="vacancy-count",
            children="⏳ Загрузка вакансий...",
            style={
                "fontSize": "20px",
                "fontWeight": "bold",
                "marginBottom": "15px",
            }
        ),

        dcc.Graph(
            id="vacancy-graph"
        ),

        html.H3(
            "📋 Вакансии"
        ),

        dash_table.DataTable(

            id="vacancy-table",

            columns=[

                {
                    "name":
                    "Название вакансии",
                    "id":
                    "Название вакансии",
                },

                {
                    "name":
                    "Местонахождение",
                    "id":
                    "Местонахождение",
                },

                {
                    "name":
                    "Профессия",
                    "id":
                    "Профессия",
                },

                {
                    "name":
                    "Дни работы",
                    "id":
                    "Дни работы",
                },

                {
                    "name":
                    "Время работы",
                    "id":
                    "Время работы",
                },

                {
                    "name":
                    "Ссылка",
                    "id":
                    "Ссылка",
                    "presentation":
                    "markdown",
                },
            ],

            data=[],

            page_size=20,

            filter_action="native",

            sort_action="native",

            sort_mode="multi",

            markdown_options={
                "link_target": "_blank"
            },

            style_table={
                "overflowX": "auto",
            },

            style_cell={

                "textAlign": "left",

                "padding": "8px",

                "whiteSpace": "normal",

                "height": "auto",

                "minWidth": "100px",
            },

            style_cell_conditional=[

                {
                    "if": {
                        "column_id":
                        "Название вакансии"
                    },

                    "minWidth":
                    "350px",

                    "width":
                    "40%",
                },

                {
                    "if": {
                        "column_id":
                        "Местонахождение"
                    },

                    "minWidth":
                    "200px",
                },

                {
                    "if": {
                        "column_id":
                        "Профессия"
                    },

                    "minWidth":
                    "150px",
                },

                {
                    "if": {
                        "column_id":
                        "Дни работы"
                    },

                    "minWidth":
                    "120px",
                },

                {
                    "if": {
                        "column_id":
                        "Время работы"
                    },

                    "minWidth":
                    "120px",
                },
            ],

            style_header={

                "fontWeight":
                "bold",

                "backgroundColor":
                "#e9ecef",

                "border":
                "1px solid #ccc",
            },

            style_data={

                "border":
                "1px solid #ddd",

            },
        ),

        html.Br(),

        html.Div(
            "Обновление данных каждые 5 минут.",
            style={
                "color": "#777"
            }
        ),

        dcc.Interval(

            id="interval-component",

            interval=
            UPDATE_INTERVAL_MS,

            n_intervals=0,
        ),
    ]
)


# ============================================================
# CALLBACK
# ============================================================

@app.callback(

    Output(
        "vacancy-table",
        "data"
    ),

    Output(
        "vacancy-graph",
        "figure"
    ),

    Output(
        "vacancy-count",
        "children"
    ),

    Input(
        "interval-component",
        "n_intervals"
    )
)


def update_vacancies(
    n
):

    print()
    print(
        "#" * 70
    )

    print(
        "ОБНОВЛЕНИЕ ВАКАНСИЙ"
    )

    print(
        f"Запуск обновления №{n + 1}"
    )

    print(
        "#" * 70
    )

    df = fetch_vacancies()

    # --------------------------------------------------------
    # НЕТ ВАКАНСИЙ
    # --------------------------------------------------------

    if df.empty:

        fig = px.bar(

            x=["Елгава"],

            y=[0],

            labels={
                "x": "",
                "y":
                "Количество вакансий",
            },

            title=
            "Вакансии в Елгаве",
        )

        return (
            [],
            fig,
            "❌ Вакансий не найдено"
        )

    # --------------------------------------------------------
    # ГРАФИК ПО ПРОФЕССИЯМ
    # --------------------------------------------------------

    graph_df = (
        df[
            "Профессия"
        ]
        .replace(
            "",
            "Не указана"
        )
        .value_counts()
        .reset_index()
    )

    graph_df.columns = [
        "Профессия",
        "Количество"
    ]

    fig = px.bar(

        graph_df,

        x="Профессия",

        y="Количество",

        title=
        "Вакансии в Елгаве по профессиям",

        labels={
            "Профессия":
            "Профессия",

            "Количество":
            "Количество вакансий",
        },
    )

    fig.update_layout(
        xaxis_tickangle=-45,
        height=500,
    )

    # --------------------------------------------------------
    # ССЫЛКА
    # --------------------------------------------------------

    output_df = df.copy()

    output_df[
        "Ссылка"
    ] = output_df[
        "Ссылка"
    ].apply(
        lambda url:
        f"[Открыть объявление]({url})"
    )

    count_text = (
        f"✅ Найдено вакансий в Елгаве: "
        f"{len(df)}"
    )

    return (

        output_df.to_dict(
            "records"
        ),

        fig,

        count_text
    )


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 70)

    print(
        "ЗАПУСК SS.COM МОНИТОРИНГА"
    )

    print("=" * 70)

    print(
        "Местонахождение: ЕЛГАВА"
    )

    print(
        "Дни работы: РАБОЧИЕ"
    )

    print(
        "Специальность: ВСЕ"
    )

    print(
        "Обновление: каждые 5 минут"
    )

    print("=" * 70)

    app.run(
        debug=True
    )
