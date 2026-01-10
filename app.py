
import streamlit as st
import pandas as pd
import random
from pyuca import Collator  # <- import

collator = Collator()  

# ---------- Page config ----------
st.set_page_config(page_title="Craft Beer List", layout="wide")

# ---------- Defaults ----------
EXCEL_PATH = "beer_data.xlsx"
DEFAULT_BEER_IMG = "https://assets.untappd.com/site/assets/images/temp/badge-beer-default.png"
DEFAULT_BREWERY_IMG = "https://assets.untappd.com/site/assets/images/temp/badge-brewery-default.png"

# ---------- Country master ----------
COUNTRY_INFO = {
    "Japan":{"jp":"日本","flag":"https://freesozai.jp/sozai/nation_flag/ntf_131/ntf_131.png",},
    "Belgium":{"jp":"ベルギー","flag":"https://freesozai.jp/sozai/nation_flag/ntf_330/ntf_330.png",},
    "Germany":{"jp":"ドイツ","flag":"https://freesozai.jp/sozai/nation_flag/ntf_322/ntf_322.png",},
    "United States":{"jp":"アメリカ","flag":"https://freesozai.jp/sozai/nation_flag/ntf_401/ntf_401.png",},
    "Netherlands":{"jp":"オランダ","flag":"https://freesozai.jp/sozai/nation_flag/ntf_310/ntf_310.png",},
    "Czech Republic":{"jp":"チェコ","flag":"https://freesozai.jp/sozai/nation_flag/ntf_320/ntf_320.png",},
    "Italy":{"jp": "イタリア","flag": "https://freesozai.jp/sozai/nation_flag/ntf_306/ntf_306.png",},
    "Austria":{"jp":"オーストリア","flag":"https://freesozai.jp/sozai/nation_flag/ntf_309/ntf_309.svg",},
}

# ---------- Helpers ----------

def safe_str(v):
    if pd.isna(v) or v is None: return ""
    return str(v)

def stock_status(val):
    """
    Excel の in_stock を ○ / △ / × で扱う
    ○ = 在庫あり
    △ = 取り寄せ
    × = 在庫なし
    """
    if pd.isna(val):
        return "×"  # デフォルト

    v = str(val).strip()

    if v in ["○", "◯", "o", "O", "あり", "yes", "1", "true"]:
        return "○"

    if v in ["△", "取り寄せ"]:
        return "△"

    return "×"


def try_number(v):
    if pd.isna(v): return None
    s = str(v)
    digits = ''.join(ch for ch in s if ch.isdigit() or ch=='.')
    if digits=="": return None
    try:
        if '.' in digits: return float(digits)
        return int(float(digits))
    except:
        return None

def locale_key(x):
    s = "" if x is None else str(x).strip()
    return collator.sort_key(s)


def get_countries_for_filter(df):
    return sorted(
        df[df["stock_status"] == "○"]["country"]
        .replace("", pd.NA)
        .dropna()
        .unique()
    )

@st.cache_data
def get_style_candidates(df):
    return sorted(
        df["style_main_jp"]
        .replace("", pd.NA)
        .dropna()
        .unique(),
        key=locale_key
    )


@st.cache_data(
    hash_funcs={pd.DataFrame: lambda _: None}
)
def build_filtered_df(
    df,
    search_text,
    size_choice,
    abv_min, abv_max,
    price_min, price_max,
    country_choice,  
):
    d = df_instock.copy()

    # --- フリー検索 ---
    if search_text and search_text.strip():
        kw = search_text.strip().lower()
        d = d[d["search_blob"].str.contains(kw, na=False)]

    # --- サイズ ---
    if size_choice == "小瓶（≤500ml）":
        d = d[d["volume_num"] <= 500]
    elif size_choice == "大瓶（≥500ml）":
        d = d[d["volume_num"] >= 500]

    # --- ABV ---
    d = d[
        (d["abv_num"].fillna(-1) >= abv_min) &
        (d["abv_num"].fillna(999) <= abv_max)
    ]

    # --- 価格 ---
    d = d[
        (d["price_num"].fillna(-1) >= price_min) &
        (d["price_num"].fillna(10**9) <= price_max)
    ]

    # --- 国フィルタ（ここだけ） ---
    if country_choice != "すべて":
        d = d[d["country"] == country_choice]

    return d

# ---------- Load data ----------
@st.cache_data
def load_data(path=EXCEL_PATH):
    df = pd.read_excel(path, engine="openpyxl")

    expected = [
        "id","name_jp","name_local","yomi","brewery_local","brewery_jp","country","city",
        "brewery_description","brewery_image_url","style_main","style_main_jp",
        "style_sub","style_sub_jp","abv","volume","vintage","price","comment","detailed_comment",
        "in_stock","untappd_url","jan","beer_image_url"
    ]
    for c in expected:
        if c not in df.columns:
            df[c] = pd.NA

    df["abv_num"] = pd.to_numeric(df["abv"], errors="coerce")
    df["volume_num"] = df["volume"].apply(try_number)
    df["price_num"] = df["price"].apply(try_number)

    str_cols = [
        "name_jp","name_local","brewery_local","brewery_jp","country","city",
        "brewery_description","brewery_image_url","style_main","style_main_jp",
        "style_sub","style_sub_jp","comment","detailed_comment","untappd_url","jan","beer_image_url"
    ]
    for c in str_cols:
        df[c] = df[c].fillna("").astype(str)

    df["stock_status"] = df["in_stock"].apply(stock_status)

    # --- 国旗URL付与 ---
    df["flag_url"] = df["country"].map(
        lambda c: COUNTRY_INFO.get(c, {}).get("flag", "")
    )


    # --- yomi 正規化 ---
    df["yomi"] = df["yomi"].astype(str).str.strip()
    df["yomi_sort"] = df["yomi"].apply(lambda x: collator.sort_key(x))

    # --- フリー検索用結合列（軽量化） ---
    search_cols = [
        "name_local","name_jp","brewery_local","brewery_jp",
        "style_main_jp","style_sub_jp","comment",
        "detailed_comment","untappd_url","jan"
    ]

    df["search_blob"] = (
        df[search_cols]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
        .str.lower()
    )

    return df
# --- load_data の外 ---
df_all = load_data()

# 在庫ありのみ（前処理）
df_instock = df_all[df_all["stock_status"] == "○"]

# ---------- ランダム順用 state 初期化 ----------
import random

if "prev_sort_option" not in st.session_state:
    st.session_state.prev_sort_option = None

if "random_seed" not in st.session_state:
    st.session_state.random_seed = None

# ---------- style checkbox state 初期化 ----------
if "style_state_init" not in st.session_state:
    for s in df_all["style_main_jp"].dropna().unique():
        st.session_state[f"style_{s}"] = False
    st.session_state["style_state_init"] = True


# ---------- Initialize show limit and filter signature ----------
if "show_limit" not in st.session_state:
    st.session_state.show_limit = 10   # ▼ Step1: 初期表示件数（10件）

# helper: compute a signature for current filters so we can reset show_limit when filters change
def compute_filter_signature():
    # include keys that affect filtered result
    keys = [
        st.session_state.get("search_text",""),
        st.session_state.get("sort_option",""),
        st.session_state.get("size_choice",""),
        str(st.session_state.get("abv_slider","")),
        str(st.session_state.get("price_slider","")),
        st.session_state.get("country_radio","")
    ]
    # include style selections
    style_keys = [k for k in st.session_state.keys() if k.startswith("style_")]
    style_vals = [f"{k}:{st.session_state.get(k)}" for k in sorted(style_keys)]
    sig = "|".join(keys + style_vals)
    return sig

if "prev_filter_sig" not in st.session_state:
    st.session_state.prev_filter_sig = compute_filter_signature()
else:
    current_sig = compute_filter_signature()
    if current_sig != st.session_state.prev_filter_sig:
        # フィルタが変わったら表示上限をリセット
        st.session_state.show_limit = 10
        st.session_state.prev_filter_sig = current_sig
        for key in list(st.session_state.keys()):
            if key.startswith("detail_") or key == "open_detail":
                del st.session_state[key]

        st.session_state.prev_filter_sig = current_sig

# ---------- Custom CSS ----------
st.markdown("""
<style>

/* ビール1カード（columns 全体） */
div[data-testid="stHorizontalBlock"] {
    background: #f4f9ff;           /* 薄い青 */
    border: 1px solid #cfe3f8;     /* 青寄りの薄枠 */
    border-radius: 12px;
    padding: 14px 16px;
    margin-bottom: 14px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.06);
}

div[data-testid="stHorizontalBlock"]:hover {
    box-shadow: 0 4px 10px rgba(0,0,0,0.10);
}

</style>
""", unsafe_allow_html=True)

# ---------- Filters UI ----------
with st.expander("フィルター / 検索を表示", False):
    st.markdown('<div id="search_bar"></div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5, c6, c7 = st.columns([0.5,5,0.5,10,0.5,3.5,5])

    with c1:
        st.markdown("🔎", unsafe_allow_html=True)

    with c2:
        search_text = st.text_input(
            "検索",
            placeholder="フリー検索",
            label_visibility="collapsed",
            key="search_text",
            value=st.session_state.get("search_text", "")
        )

    with c3:
        st.markdown("国", unsafe_allow_html=True)

    with c4:
        countries = get_countries_for_filter(df_all)

        if "country_radio" not in st.session_state:
            st.session_state["country_radio"] = "すべて"

        countries_display = ["すべて"] + [
            COUNTRY_INFO.get(c, {}).get("jp", c)
            for c in countries
        ]

        country_choice_display = st.radio(
            "国",
            countries_display,
            horizontal=True,
            label_visibility="collapsed",
            key="country_radio"
        )

        if country_choice_display == "すべて":
            country_choice = "すべて"
        else:
            country_choice = next(
                (k for k, v in COUNTRY_INFO.items()
                if v.get("jp") == country_choice_display),
                country_choice_display
            )

    with c5:
        st.markdown("⇅", unsafe_allow_html=True)

    with c6:
        sort_options = [
            "名前順",
            "ABV（低）",
            "ABV（高）",
            "価格（低）",
            "ランダム順"
        ]

        sort_option = st.selectbox(
            "並び替え",
            options=sort_options,
            index=sort_options.index(st.session_state.get("sort_option", "名前順")),
            key="sort_option",
            label_visibility="collapsed"
        )

        # ---------- CSS でカーソルを非表示・文字入力不可にする ----------
        st.markdown("""
        <style>
        /* Streamlit selectbox の文字入力を固定化 */
        div[data-baseweb="select"] input {
            caret-color: transparent !important;  /* カーソルを消す */
            pointer-events: none !important;      /* 文字入力を無効化 */
        }
        </style>
        """, unsafe_allow_html=True)

    with c7:
        # ---------- 修正：完全リセット ----------
        if st.button("🔄 リセット", help="すべて初期化"):

            # 1. スタイルチェックボックスなどプレフィックス付きキーを削除
            for s in df["style_main_jp"].dropna().unique():
                st.session_state[f"style_{s}"] = False

            # 2. その他のUI状態も初期化
            for key in ["search_text", "sort_option", "size_choice", "abv_slider", "price_slider", "country_radio"]:
                st.session_state.pop(key, None)
         
            # 3. 必要に応じて初期値をセット
            st.session_state["search_text"] = ""
            st.session_state["sort_option"] = "名前順"
            st.session_state["size_choice"] = "小瓶（≤500ml）"
            st.session_state["abv_slider"] = (0.0, 20.0)
            st.session_state["price_slider"] = (0, 20000)
            st.rerun()

            # 4.詳細コメント state を全削除
            for key in list(st.session_state.keys()):
                if key.startswith("detail_"):
                    del st.session_state[key]


    # ===== 2行目：サイズ・ABV・価格 =====
    col_size, col_abv, col_price = st.columns([2.5, 1.5, 1.5])

    with col_size:    
        if "size_choice" not in st.session_state :
            st.session_state["size_choice"] = "小瓶（≤500ml）"
        size_choice = st.radio(
        "サイズ",
        ("すべて", "小瓶（≤500ml）", "大瓶（≥500ml）"),
        horizontal=True,
        key="size_choice"
        )

    with col_abv:
        if "abv_slider" not in st.session_state:
            st.session_state["abv_slider"] = (0.0, 20.0)

        abv_min, abv_max = st.slider(
            "ABV（%）",
            0.0, 20.0,
            step=0.5,
            key="abv_slider"
        )

    with col_price:
        if "price_slider" not in st.session_state:
            st.session_state["price_slider"] = (0, 20000)
        price_min, price_max = st.slider(
            "価格（円）",
            0, 20000,
            step=100,
            key="price_slider"
        )

    # ===== 4行目：スタイル（メイン） =====
    st.markdown("### スタイルで絞り込み")
    style_ui_placeholder = st.container()

# ---------- Filtering（★1回だけ） ----------
filtered_base = build_filtered_df(
    df_instock,
    search_text=search_text,
    size_choice=size_choice,
    abv_min=abv_min,
    abv_max=abv_max,
    price_min=price_min,
    price_max=price_max,
    country_choice=country_choice,
)

# ---------- Style UI（差し込み） ----------
with style_ui_placeholder:
    styles_available = get_style_candidates(filtered_base)

    selected_styles = []

    if styles_available:
        cols = st.columns(min(6, len(styles_available)))
        for i, s in enumerate(styles_available):
            key = f"style_{s}"
            if cols[i % len(cols)].checkbox(s, key=key):
                selected_styles.append(s)

# ----------style 選択を filtered に適用 ----------
filtered = filtered_base
if selected_styles:
    filtered = filtered[
        filtered["style_main_jp"].isin(selected_styles)
    ]

# ---------- Sorting ----------
if sort_option == "名前順":
    filtered = filtered.sort_values(by="yomi_sort", na_position="last")
elif sort_option == "ABV（低）":
    filtered = filtered.sort_values(by="abv_num", ascending=True, na_position="last")
elif sort_option == "ABV（高）":
    filtered = filtered.sort_values(by="abv_num", ascending=False, na_position="last")
elif sort_option == "価格（低）":
    # price_num が 0（ASK）は極端に大きい値に置き換えて最後に回す
    filtered["price_sort"] = filtered["price_num"].replace(0, 10**9)
    filtered = filtered.sort_values(by="price_sort", ascending=True)
elif sort_option == "醸造所順":
    filtered = filtered.sort_values(by="brewery_jp", key=lambda x: x.map(locale_key))
elif sort_option == "スタイル順":
    filtered = filtered.sort_values(
        by="style_main_jp",
        key=lambda x: x.map(locale_key)
    )
elif sort_option == "ランダム順":

    # ランダム順に「切り替わった瞬間」だけ seed 更新
    if st.session_state.prev_sort_option != "ランダム順":
        st.session_state.random_seed = random.randint(0, 10**9)

    filtered = filtered.sample(
        frac=1,
        random_state=st.session_state.random_seed
    )

st.session_state.prev_sort_option = sort_option

# ---------- Prepare display_df with limit (Step1: show_limit) ----------
total_count = len(filtered)

display_df = filtered.head(st.session_state.show_limit)
st.markdown("**表示件数：{} 件**".format(len(filtered)))

# --- カード描画関数（高速・安全版） ---
def render_beer_card(r, beer_id_safe):

    # --- 変数定義 ---
    beer_img = r.beer_image_url or DEFAULT_BEER_IMG
    untappd_url = r.untappd_url
    flag_img = r.flag_url
    style_line = " / ".join(filter(None, [r.style_main_jp, r.style_sub_jp]))


    st.markdown('<div class="beer-card">', unsafe_allow_html=True)

    left_col, right_col = st.columns([3, 5])

    # ===== 左：ビール画像のみ =====
    with left_col:
        beer_img = r.beer_image_url or DEFAULT_BEER_IMG
        st.markdown(
            f"""
            <div style="display:flex;justify-content:center;align-items:center;height:100%;">
                <img src="{beer_img}" style="height:170px;object-fit:contain" loading="lazy">
            </div>
            """,
            unsafe_allow_html=True
        )

    # ===== 右：情報（国 → 醸造所 → ビール）=====
    with right_col:
        # --- 国旗 + 醸造所名（1列） ---
        flag_img = r.flag_url

        brewery_name_html = f"""
        <div>
            {"<img src='"+flag_img+"' width='18' style='vertical-align:middle;margin-right:6px;'>" if flag_img else ""}
            <b>{r.brewery_local}</b> / <span style="color:#666;">{r.brewery_jp}</span>
        </div>
        """
        st.markdown(brewery_name_html, unsafe_allow_html=True)


        # ===== 旧 col3（ビール情報）ベース =====
        style_line = " / ".join(filter(None, [r.style_main_jp, r.style_sub_jp]))

        info_arr = []
        if pd.notna(r.abv_num):
            info_arr.append(f"ABV {r.abv_num}%")
        if pd.notna(r.volume_num):
            info_arr.append(f"{int(r.volume_num)}ml")
        if pd.notna(r.vintage) and str(r.vintage).strip():
            info_arr.append(str(r.vintage).strip())
        if pd.notna(r.price_num):
            info_arr.append("ASK" if r.price_num == 0 else f"¥{int(r.price_num)}")

        beer_info = " | ".join(info_arr)

        st.markdown(
            f"""
            <a href="{r.untappd_url}" target="_blank"
                style="text-decoration:none;color:inherit;">
                <b style="font-size:1.15em;">{r.name_local}</b><br>
                <span style="font-size:0.95em;">{r.name_jp}</span>
            </a><br>
            <span style="color:#666;">{style_line}</span><br>
            {beer_info}<br>
            {r.comment or ""}
            """,
            unsafe_allow_html=True
        )

        # ====== 詳細コメント（自前 toggle / 軽量）=====
        if r.detailed_comment and r.detailed_comment.strip():

            detail_key = f"detail_{beer_id_safe}"

            # 初期化（必要なカードだけ）
            if detail_key not in st.session_state:
                st.session_state[detail_key] = False

            # トグルボタン
            if st.button("詳細コメント", key=f"btn_{beer_id_safe}"):
                st.session_state[detail_key] = not st.session_state[detail_key]

            # 表示
            if st.session_state[detail_key]:
                st.markdown(
                    f"""
                    <div class="detail-comment">
                      {r.detailed_comment}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

# ---------- Render（統一版） ----------
for global_idx, r in enumerate(display_df.itertuples(index=False)):
    try:
        beer_id_safe = int(float(r.id))
    except (ValueError, TypeError):
        continue

    render_beer_card(r, beer_id_safe)

# ---------- トップへ戻るボタン ----------
st.markdown(
    f"""
    <div style="margin-bottom: 10px;">
        <a href="#search_bar">
            <button style="
                width: 100%;
                padding: 0.5rem;
                font-size: 16px;
                background-color: #f0f0f0;
                border: 1px solid #ccc;
                border-radius: 4px;
                cursor: pointer;
            ">🔼 トップへ戻る 🔼</button>
        </a>
    </div>
    """,
    unsafe_allow_html=True
)

# ---------- "もっと見る" ボタン (Step1 continuation) ----------
# Show button below the list; if clicked, increase limit by 10
if st.session_state.show_limit < len(filtered):
    # use container to place button nicely
    with st.container():
        if st.button("🔽もっと見る🔽", use_container_width=True):
            st.session_state.show_limit += 10
else:
    # optional: show nothing or a small message
    pass






















