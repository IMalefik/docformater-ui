import streamlit as st
import requests
import base64
import uuid
import re

# ------------------ CONFIG ------------------

BACKEND_URL = "https://docformater.onrender.com/assemble"

st.set_page_config(page_title="DocFormatter", layout="wide")

# Шрифт Montserrat
st.markdown(
    """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap');
      html, body, [class*="block-container"] * {
        font-family: 'Montserrat', system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ------------------ ПЛЕЙСХОЛДЕРЫ ИЗОБРАЖЕНИЙ ------------------

# Карта плейсхолдеров: uid -> полный Markdown сниппет с data:URL
if "img_map" not in st.session_state:
    st.session_state["img_map"] = {}  # { uid: "![caption](data:...)" }

TOKEN_RE = re.compile(r"\[\[IMG#([a-f0-9\-]+)\]\]")


def expand_tokens(text: str) -> str:
    """Заменяем [[IMG#uid]] на реальные markdown-сниппеты из img_map."""
    if not text:
        return ""
    return TOKEN_RE.sub(lambda m: st.session_state["img_map"].get(m.group(1), ""), text)


# ------------------ ОТЛОЖЕННЫЕ ВСТАВКИ ------------------


def _insert_with_strategy(current_text: str, snippet: str, strategy: str) -> str:
    current_text = current_text or ""
    if strategy == "Вместо маркера [[IMG]]":
        if "[[IMG]]" in current_text:
            return current_text.replace("[[IMG]]", snippet, 1)
        else:
            suffix = "" if current_text.endswith("\n") else "\n"
            return (current_text + suffix + snippet + "\n").strip("\n")
    elif strategy == "В начало":
        return (snippet + "\n\n" + current_text).strip("\n")
    else:  # В конец
        suffix = "" if current_text.endswith("\n") else "\n"
        return (current_text + suffix + snippet + "\n").strip("\n")


# отложенные вставки в конкретные поля: { key: {"snippet":..., "position":...} }
if "pending_inserts" not in st.session_state:
    st.session_state["pending_inserts"] = {}

# применяем отложенные вставки ДО отрисовки виджетов
if st.session_state["pending_inserts"]:
    to_apply = st.session_state["pending_inserts"].copy()
    for tkey, payload in to_apply.items():
        current = st.session_state.get(tkey, "")
        new_text = _insert_with_strategy(
            current, payload["snippet"], payload["position"]
        )
        st.session_state[tkey] = new_text
    st.session_state["pending_inserts"] = {}


def add_image_inserter(text_key: str, where_label: str):
    """Мини-блок «Добавить изображение» для поля с key=text_key."""
    flag_key = f"show_uploader_{text_key}"

    c1, c2 = st.columns([1, 3])
    with c1:
        if st.button("🖼️ Добавить изображение", key=f"btn_addimg_{text_key}"):
            st.session_state[flag_key] = True
    with c2:
        st.caption(
            "Чтобы поставить картинку точно, поставьте в тексте маркер **[[IMG]]** — вставим вместо него. "
            "В поле появится короткая метка, сама картинка подставится при сборке."
        )

    if st.session_state.get(flag_key):
        up1, up2, up3 = st.columns([2, 2, 1])
        with up1:
            img = st.file_uploader(
                f"Изображение для {where_label} (png/jpg)",
                type=["png", "jpg", "jpeg"],
                accept_multiple_files=False,
                key=f"uploader_{text_key}",
            )
        with up2:
            caption = st.text_input(
                "Подпись к изображению (необязательно)",
                key=f"caption_{text_key}",
                value="Рисунок",
            )
            position = st.selectbox(
                "Куда вставить",
                ["В конец", "В начало", "Вместо маркера [[IMG]]"],
                key=f"pos_{text_key}",
            )
        with up3:
            st.write("")  # отступ
            if st.button("Вставить", key=f"do_insert_{text_key}"):
                if img is None:
                    st.warning("Сначала выберите файл изображения.")
                else:
                    # Готовим markdown сниппет и короткую метку
                    mime = img.type or "image/png"
                    b64 = base64.b64encode(img.read()).decode("utf-8")

                    # Сохраняем ПОЛНЫЙ markdown в карту, а в текст вставляем короткую метку [[IMG#uid]]
                    uid = str(uuid.uuid4())
                    full_snippet = f"![{caption}](data:{mime};base64,{b64})"
                    st.session_state["img_map"][uid] = full_snippet

                    placeholder = f"[[IMG#{uid}]]"

                    # создаём отложенную вставку и перезапускаем скрипт
                    st.session_state["pending_inserts"][text_key] = {
                        "snippet": placeholder,
                        "position": position,
                    }
                    st.session_state[flag_key] = False
                    st.rerun()


# ------------------ INTERFACE ------------------

st.title("📄 Автооформление курсовой/дипломной работы")
st.markdown(
    "Просто заполни разделы текстом, а мы соберем документ с оформлением по ГОСТ за тебя."
)

# Выбор шаблона ГОСТ (пока МЭИ)
st.subheader("Выберите шаблон для оформления работы")
preset = st.selectbox(
    "Шаблон оформления",
    options=["Оформление по ГОСТ для МЭИ"],
    index=0,
    label_visibility="collapsed",
)

title = st.text_input(
    "Название работы (используется только для имени файла)", value="Моя работа"
)
include_toc = st.checkbox("Добавить содержание (оглавление)", value=True)

st.markdown("---")
st.subheader("Добавьте разделы и подразделы")

# ------------------ СБОР ДАННЫХ ------------------

sections = []
section_count = st.number_input(
    "Количество разделов", min_value=1, max_value=15, value=1, step=1
)

for i in range(section_count):
    st.markdown(f"### Раздел {i+1}")

    heading = st.text_input(f"Название раздела {i+1}", key=f"heading_{i}")

    body_key = f"body_{i}"
    body = st.text_area(f"Текст раздела {i+1}", height=200, key=body_key)
    add_image_inserter(body_key, f"раздела {i+1}")

    sub_count = st.number_input(
        f"Количество подразделов для раздела {i+1}",
        min_value=0,
        max_value=10,
        value=0,
        step=1,
        key=f"subcount_{i}",
    )
    subs = []

    for j in range(sub_count):
        st.markdown(f"#### Подраздел {i+1}.{j+1}")

        sub_heading = st.text_input(
            f"Название подраздела {i+1}.{j+1}", key=f"sub_heading_{i}_{j}"
        )

        sub_body_key = f"sub_body_{i}_{j}"
        sub_body = st.text_area(
            f"Текст подраздела {i+1}.{j+1}", height=150, key=sub_body_key
        )
        add_image_inserter(sub_body_key, f"подраздела {i+1}.{j+1}")

        sub3_count = st.number_input(
            f"Количество подподразделов для {i+1}.{j+1}",
            min_value=0,
            max_value=10,
            value=0,
            step=1,
            key=f"sub3count_{i}_{j}",
        )
        sub3s = []
        for k in range(sub3_count):
            st.markdown(f"##### Подподраздел {i+1}.{j+1}.{k+1}")

            sub3_heading = st.text_input(
                f"Название подподраздела {i+1}.{j+1}.{k+1}",
                key=f"sub3_heading_{i}_{j}_{k}",
            )

            sub3_body_key = f"sub3_body_{i}_{j}_{k}"
            sub3_body = st.text_area(
                f"Текст подподраздела {i+1}.{j+1}.{k+1}", height=120, key=sub3_body_key
            )
            add_image_inserter(sub3_body_key, f"подподраздела {i+1}.{j+1}.{k+1}")

            sub3s.append(
                {
                    "heading": sub3_heading,
                    "body": st.session_state.get(sub3_body_key, ""),
                }
            )

        subs.append(
            {
                "heading": sub_heading,
                "body": st.session_state.get(sub_body_key, ""),
                "sub3": sub3s,
            }
        )

    sections.append(
        {"heading": heading, "body": st.session_state.get(body_key, ""), "sub": subs}
    )

# ------------------ КНОПКА ------------------

if st.button("Собрать документ"):
    # Перед отправкой разворачиваем плейсхолдеры изображений в реальный markdown
    def _expand_section(sec: dict) -> dict:
        sec = dict(sec)
        sec["body"] = expand_tokens(sec.get("body", ""))
        for sb in sec.get("sub", []):
            sb["body"] = expand_tokens(sb.get("body", ""))
            for sb3 in sb.get("sub3", []):
                sb3["body"] = expand_tokens(sb3.get("body", ""))
        return sec

    expanded_sections = [_expand_section(s) for s in sections]

    payload = {
        "title": title,
        "include_toc": include_toc,
        "sections": expanded_sections,
        "preset": "mei_gost",  # на будущее
    }

    with st.spinner("Формируется документ..."):
        try:
            resp = requests.post(BACKEND_URL, json=payload)
            if resp.status_code == 200:
                st.success("✅ Документ успешно создан!")
                st.download_button(
                    label="⬇️ Скачать DOCX",
                    data=resp.content,
                    file_name=f"{title}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            else:
                st.error(f"Ошибка: {resp.status_code}")
                st.text(resp.text)
        except Exception as e:
            st.error(f"Не удалось подключиться к серверу: {e}")
