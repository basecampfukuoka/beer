
import streamlit as st
import pandas as pd
import locale
import unicodedata
from pyuca import Collator  # <- import

collator = Collator()  

# ---------- Page config ----------
st.set_page_config(page_title="Craft Beer List", layout="wide")

# ---------- Defaults ----------
EXCEL_PATH = "beer_data.xlsx"
DEFAULT_BEER_IMG = "https://assets.untappd.com/site/assets/images/temp/badge-beer-default.png"
DEFAULT_BREWERY_IMG = "https://assets.untappd.com/site/assets/images/temp/badge-brewery-default.png"

# ---------- 国旗 URL マッピング (ここが「1」) ----------
country_flag_url = {
    "Japan": "https://freesozai.jp/sozai/nation_flag/ntf_131/ntf_131.png",
    "Belgium": "https://freesozai.jp/sozai/nation_flag/ntf_330/ntf_330.png",
    "Germany": "https://freesozai.jp/sozai/nation_flag/ntf_322/ntf_322.png",
    "United States": "https://freesozai.jp/sozai/nation_flag/ntf_401/ntf_401.png",
    "United Kingdom": "https://freesozai.jp/sozai/nation_flag/ntf_305/ntf_305.png",
    "Netherlands": "https://freesozai.jp/sozai/nation_flag/ntf_310/ntf_310.png",
    "Czech Republic": "https://freesozai.jp/sozai/nation_flag/ntf_320/ntf_320.png",
    "France": "https://freesozai.jp/sozai/nation_flag/ntf_327/ntf_327.png",
    "Canada": "https://freesozai.jp/sozai/nation_flag/ntf_404/ntf_404.png",
    "Italy": "https://freesozai.jp/sozai/nation_flag/ntf_306/ntf_306.png",
    "Sweden": "https://freesozai.jp/sozai/nation_flag/ntf_315/ntf_315.svg"
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

def get_countries_for_filter(df, show_take_order, show_no_stock):
    d = apply_stock_filter(df, show_take_order, show_no_stock)
    countries = (
        d["country"]
        .replace("", pd.NA)
        .dropna()
        .unique()
    )
    return sorted(countries)


# 在庫フィルタ共通化
def apply_stock_filter(df, show_take_order, show_no_stock):
    return df[
        (df["stock_status"] == "○")
        | (show_take_order & (df["stock_status"] == "△"))
        | (show_no_stock & (df["stock_status"] == "×"))
    ]

# 醸造所ビール map（キャッシュ）
@st.cache_data
def build_brewery_beers_map(df, show_take_order, show_no_stock):
    d = apply_stock_filter(df, show_take_order, show_no_stock)
    return {
        brewery: g
        for brewery, g in d.groupby("brewery_jp")
    }

@st.cache_data
def build_brewery_beers_map_instock(df):
    d = df[df["stock_status"] == "○"]  # 在庫アリだけ
    return {brewery: g for brewery, g in d.groupby("brewery_jp")}



# ---------- Style candidates (cached) ----------
@st.cache_data
def get_style_candidates(df):
    return sorted(
        df["style_main_jp"]
        .replace("", pd.NA)
        .dropna()
        .unique(),
        key=locale_key
    )


@st.cache_data
def build_filtered_df(
    df,
    search_text,
    size_choice,
    abv_min, abv_max,
    price_min, price_max,
    show_take_order,
    show_no_stock,
    removed_ids,
    country_choice,  
):


    # ★ 最初に df をそのまま使う
    d = df

    # --- 在庫フィルタ（共通関数） ---
    d = apply_stock_filter(d, show_take_order, show_no_stock)

    # --- フリー検索 ---
    if search_text and search_text.strip():
        kw = search_text.strip().lower()
        text_cols = [
            "name_local","name_jp","brewery_local","brewery_jp",
            "style_main_jp","style_sub_jp","comment",
            "detailed_comment","untappd_url","jan"
        ]
        temp = d[text_cols].fillna("").astype(str).apply(lambda c: c.str.lower())
        mask = False
        for c in temp.columns:
            mask |= temp[c].str.contains(kw, na=False)
        d = d[mask]

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

    # --- 削除済み ---
    if removed_ids:
        d = d[~d["id"].astype(int).isin(removed_ids)]

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



    # --- yomi 正規化 ---
    df["yomi"] = df["yomi"].astype(str).str.strip()
    df["yomi_sort"] = df["yomi"].apply(lambda x: collator.sort_key(x))

    # debug print
    print(df.columns.tolist())

    return df


# --- load_data の外 ---
df_all = load_data()
df = df_all


df_instock = df[df["stock_status"] == "○"]



# ---------- Initialize show limit and filter signature ----------
if "show_limit" not in st.session_state:
    st.session_state.show_limit = 10   # ▼ Step1: 初期表示件数（10件）
if "removed_ids" not in st.session_state:
    st.session_state["removed_ids"] = set()

# helper: compute a signature for current filters so we can reset show_limit when filters change
def compute_filter_signature():
    # include keys that affect filtered result
    keys = [
        st.session_state.get("search_text",""),
        st.session_state.get("sort_option",""),
        st.session_state.get("size_choice",""),
        str(st.session_state.get("abv_slider","")),
        str(st.session_state.get("price_slider","")),
        st.session_state.get("country_radio",""),
        str(st.session_state.get("show_out_of_stock", False))
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
        # ▼ Step2: フィルタが変わったら表示上限をリセット
        st.session_state.show_limit = 10
        st.session_state.prev_filter_sig = current_sig

# ---------- Custom CSS ----------
st.markdown("""
<style>
/* ビール名統一（英語・日本語） */
.beer-name {
    width: 180px;             /* カード幅に合わせる */
    display: block;
    margin: 0 auto;
    text-align: center;       /* 中央揃え */
    white-space: normal;      /* 折り返し有効 */
    word-wrap: break-word;
    overflow-wrap: break-word;
}

/* 詳細カードデザイン */
.detail-card { 
    background-color: #f0f8ff; 
    border-radius: 8px; 
    padding: 10px; 
    margin:6px; 
    display:inline-block; 
    vertical-align:top; 
    min-width: 150px;  /* 任意で最小幅を設定 */
    max-width: 450px;       /* 任意で最大幅 */
    text-align:center !important; 
}

/* コメント用カード */
.comment-card {
    background-color: #eaf4ff;
    padding: 10px 14px;
    margin: 10px 0 16px 0;
    border-radius: 6px;
    line-height: 1.6;
}

/* ビール画像を固定幅にして横スクロール可能に */
.detail-card img {
    width: 100px;          /* 画像は固定幅 */
    height: 100px;
    object-fit: contain;
}

/* 横スクロール用ラッパー */
.brewery-beer-list > div {
    white-space: nowrap;
    overflow-x: auto;
}

/* brewery-beer-list 横スクロール */
.brewery-beer-list { margin-top:10px; }

/* ビール画像（UNTAPPD 上）を固定幅に */
.beer-image {
    width: 150px;        /* ← 好きな幅に調整 */
    height: 150px;       /* 高さも固定したい場合 */
    object-fit: contain; /* 画像を切らずに収める */
}

/* remove btn hover */
.remove-btn div[data-testid="stButton"] > button:hover {
    opacity: 0.6 !important;
}

/* ボタン中央寄せ */
.remove-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
}

.left-center {
    display: flex;
    justify-content: center;
    width: 100%;
}


</style>
""", unsafe_allow_html=True)

# ---------- Filters UI ----------
with st.expander("フィルター / 検索を表示", False):
    st.markdown('<div id="search_bar"></div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns([0.2, 4, 0.5, 1,0.8])

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
        st.markdown("並び替え", unsafe_allow_html=True)

    with c4:
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

    with c5:
        # ---------- 修正：完全リセット ----------
        if st.button("🔄 リセット", help="すべて初期化"):

            # 1. スタイルチェックボックスなどプレフィックス付きキーを削除
            for s in df["style_main_jp"].dropna().unique():
                st.session_state[f"style_{s}"] = False

            # 2. removed_ids をリセット ← ★これが抜けてた
            st.session_state["removed_ids"] = set()

            # 3. その他のUI状態も初期化
            for key in ["search_text", "sort_option", "size_choice", "abv_slider", "price_slider", "country_radio"]:
                st.session_state.pop(key, None)
         
            # 4. 醸造所詳細・ビール詳細のキーも削除
            for key in list(st.session_state.keys()):
                if (
                    key.startswith("show_detail_")
                    or key.startswith("brewery_btn_")
                    or key.startswith("show_comment_")
                    or key.startswith("comment_btn_")
                ):
                    del st.session_state[key]

            # 5. 必要に応じて初期値をセット
            st.session_state["search_text"] = ""
            st.session_state["sort_option"] = "名前順"
            st.session_state["size_choice"] = "小瓶（≤500ml）"
            st.session_state["abv_slider"] = (0.0, 20.0)
            st.session_state["price_slider"] = (0, 20000)
            st.session_state["show_take_order"] = False
            st.session_state["show_no_stock"] = False

            st.rerun()

    # ===== 2行目：国（Excel から自動取得・日本語化） =====
    col_country, col_stock1, col_stock2 = st.columns([4,1,1])

    country_map = {
        "Japan": "日本", "Belgium": "ベルギー", "Germany": "ドイツ", "United States": "アメリカ",
        "United Kingdom": "イギリス", "Netherlands": "オランダ", "Czech Republic": "チェコ",
        "France": "フランス", "Canada": "カナダ", "Australia": "オーストラリア",
        "Italy": "イタリア", "Sweden": "スウェーデン",
    }

    # ---- 取り寄せ・在庫なし表示 ----
    show_take_order = col_stock1.checkbox(
        "取り寄せを表示",
        key="show_take_order"
    )

    show_no_stock = col_stock2.checkbox(
        "在庫なしを表示",
        key="show_no_stock"
    )


    # session_state 初期化
    if "country_radio" not in st.session_state:
        st.session_state["country_radio"] = "ベルギー"

    # ---- 国一覧（在庫フィルタ反映）----
    countries = get_countries_for_filter(df_all, show_take_order, show_no_stock)

    # 日本語表示用に変換
    countries_display = ["すべて"] + [country_map.get(c, c) for c in countries]


    country_choice_display = col_country.radio(
        "国",
        countries_display,
        horizontal=True,
        key="country_radio"
    )

    # 日本語表示 → 内部用（英語）変換
    if country_choice_display == "すべて":
        country_choice = "すべて"
    else:
        country_choice = {v: k for k, v in country_map.items()}.get(
            country_choice_display, country_choice_display
        )


    # ===== 3行目：サイズ・ABV・価格 =====
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
    st.markdown("### スタイル（メイン）で絞り込み")
    style_ui_placeholder = st.container()

# ---------- Filtering（★1回だけ） ----------
filtered_base = build_filtered_df(
    df_all,
    search_text=search_text,
    size_choice=size_choice,
    abv_min=abv_min,
    abv_max=abv_max,
    price_min=price_min,
    price_max=price_max,
    show_take_order=show_take_order,
    show_no_stock=show_no_stock,
    removed_ids=tuple(sorted(st.session_state.get("removed_ids", set()))),
    country_choice=country_choice,
)

# ---------- Brewery beers map ----------
# 醸造所のビール一覧は在庫ありだけを表示
brewery_beers_map = build_brewery_beers_map(
    df_all,
    show_take_order=False,
    show_no_stock=False
)

# ---------- Style UI（差し込み） ----------
with style_ui_placeholder:
    styles_available = get_style_candidates(filtered_base)

    selected_styles = []

    if styles_available:
        cols = st.columns(min(6, len(styles_available)))
        for i, s in enumerate(styles_available):
            key = f"style_{s}"
            if key not in st.session_state:
                st.session_state[key] = False

            if cols[i % len(cols)].checkbox(s, key=key):
                selected_styles.append(s)

# ---------- 表示条件スナップショット ----------
current_view_state = (
    tuple(sorted(selected_styles)),
    st.session_state.get("sort_option"),
    st.session_state.get("country_radio"),
    st.session_state.get("search_text"),
    st.session_state.get("size_choice"),
    st.session_state.get("abv_slider"),
    st.session_state.get("price_slider"),
    st.session_state.get("show_take_order"),
    st.session_state.get("show_no_stock"),
)

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
    display_limit = st.session_state.show_limit
    filtered = filtered.sample(n=min(display_limit, len(filtered)))


# ===== 表示処理用 sort flags =====
is_price_sort = sort_option == "価格（低）"
is_abv_low_sort = sort_option == "ABV（低）"
is_abv_high_sort = sort_option == "ABV（高）"
is_random_sort = sort_option == "ランダム順"

disable_grouping = (
    is_price_sort or is_abv_low_sort or is_abv_high_sort or is_random_sort
)

st.markdown("**表示件数：{} 件**".format(len(filtered)))

# ---------- Prepare display_df with limit (Step1: show_limit) ----------
display_df = filtered.head(st.session_state.show_limit)

# ---------- Removed beers tracking ----------
def remove_beer(beer_id):
    beer_id_int = int(float(beer_id))
    st.session_state["removed_ids"].add(beer_id_int)



# --- カード描画関数 ---
def render_beer_card(r, beer_id_safe, brewery, idx, brewery_beers):

    # ---------- 変数定義（必ず col の外） ----------
    brewery_img = r.brewery_image_url or DEFAULT_BREWERY_IMG
    brewery_city = safe_str(r.city)
    brewery_country = safe_str(r.country)
    flag_img = country_flag_url.get(brewery_country, "")

    brewery_html = f"""
    <img src="{brewery_img}" width="100" loading="lazy"><br>
    <b>{r.brewery_local}</b><br>
    {r.brewery_jp}<br>
    {brewery_city}<br>
    {"<img src='"+flag_img+"' width='20'> "+brewery_country if flag_img else brewery_country}
    """

    beer_img = r.beer_image_url or DEFAULT_BEER_IMG
    untappd_url = r.untappd_url

    image_html = f"""
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;">
        <img src="{beer_img}" style="height:150px;object-fit:contain" loading="lazy">
        <a href="{untappd_url}" target="_blank"
           style="background:#FFD633;padding:4px 10px;border-radius:6px;
                  text-decoration:none;color:#000;font-weight:600;margin-top:6px;">
           UNTAPPD
        </a>
    </div>
    """

    # ---------- レイアウト ----------

    left_col, right_col = st.columns([4, 4], vertical_alignment="top")
    with left_col:
        st.markdown('<div class="left-center">', unsafe_allow_html=True)
        inner1, inner2 = st.columns([0.8, 0.8], gap="small")

        # ---------- col1 左：醸造所・ビール画像 ----------
        with inner1:
            brewery_img = r.brewery_image_url or DEFAULT_BREWERY_IMG
            brewery_city = safe_str(r.city)
            brewery_country = safe_str(r.country)
            flag_img = country_flag_url.get(brewery_country, "")

            brewery_html = f"""
            <img src="{brewery_img}" width="100" loading="lazy"><br>
            <b>{r.brewery_local}</b><br>
            {r.brewery_jp}<br>
            {brewery_city}<br>
            {"<img src='"+flag_img+"' width='20'> "+brewery_country if flag_img else brewery_country}
            """
            st.markdown(brewery_html, unsafe_allow_html=True)


            # ▼ トグル（1つだけ開く）
            if st.button("醸造所詳細を見る", key=f"brewery_btn_{brewery}_{beer_id_safe}_{idx}"):
                if st.session_state.open_beer_id == beer_id_safe:
                    st.session_state.open_beer_id = None   # もう一度押したら閉じる
                else:
                    st.session_state.open_beer_id = beer_id_safe  # 他は自動で閉じる


        # ====== 旧 col2（ビール画像）=====
        with inner2:
            beer_img = r.beer_image_url or DEFAULT_BEER_IMG
            untappd_url = r.untappd_url

            image_html = f"""
            <div style="display:flex;flex-direction:column;align-items:center;">
                <img src="{beer_img}" class="beer-image" loading="lazy">
                <a href="{untappd_url}" target="_blank"
                   style="background:#FFD633;padding:4px 10px;border-radius:6px;
                          text-decoration:none;color:#000;font-weight:600;margin-top:6px;">
                   UNTAPPD
                </a>
            </div>
            """
            st.markdown(image_html, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    # ---------- 醸造所詳細（そのまま） ----------
    def render_beer_card(r, beer_id_safe, brewery, idx, brewery_beers):

        if st.session_state.open_beer_id == beer_id_safe:

            # --- 醸造所コメント ---
            if r.brewery_description:
                st.markdown(
                    f"""
                    <div style="background:#f7f7f7;padding:10px 14px;margin:10px 0 16px 0;">
                    <b>{r.brewery_jp}</b><br>
                    {r.brewery_description}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            if brewery_beers.empty:
                st.info("現在表示できるビールがありません")
                return

            st.markdown("### この醸造所のビール一覧")

            cards = ['<div class="brewery-beer-list"><div style="white-space: nowrap; overflow-x: auto;">']

            for b in brewery_beers.itertuples(index=False):
                abv = f"ABV {b.abv_num}%" if pd.notna(b.abv_num) else ""
                vol = f"{int(b.volume_num)}ml" if pd.notna(b.volume_num) else ""
                price = ""
                if pd.notna(b.price_num):
                    price = "ASK" if b.price_num == 0 else f"¥{int(b.price_num)}"
                vintage = str(b.vintage).strip() if pd.notna(b.vintage) and str(b.vintage).strip() else ""

                name_local = (b.name_local or "").split("/", 1)[-1].strip()
                name_jp = (b.name_jp or "").split("/", 1)[-1].strip()
                specs = " | ".join(filter(None, [abv, vol, vintage, price]))

                cards.append(
                    '<div class="detail-card">'
                    f'<img src="{b.beer_image_url or DEFAULT_BEER_IMG}" loading="lazy"><br>'
                    f'<div class="beer-name"><b>{name_local}</b></div>'
                    f'<div class="beer-name">{name_jp}</div>'
                    f'<div class="beer-spec">{specs}</div>'
                    '</div>'
                )

            cards.append("</div></div>")
            st.markdown("".join(cards), unsafe_allow_html=True)


    with right_col:
        info_col, remove_col = st.columns([6, 1])

        # ====== 旧 col3（ビール情報）=====
        with info_col:
            style_line = " / ".join(filter(None, [r.style_main_jp, r.style_sub_jp]))

            info_arr = []
            if pd.notna(r.abv_num): info_arr.append(f"ABV {r.abv_num}%")
            if pd.notna(r.volume_num): info_arr.append(f"{int(r.volume_num)}ml")
            if pd.notna(r.vintage) and str(r.vintage).strip():
                info_arr.append(str(r.vintage).strip())
            if pd.notna(r.price_num):
                info_arr.append("ASK" if r.price_num == 0 else f"¥{int(r.price_num)}")

            beer_info = " | ".join(info_arr)

            st.markdown(
                f"""
                <b>{r.name_local}</b><br>
                {r.name_jp}<br>
                {style_line}<br>
                {beer_info}<br>
                {r.comment or ""}
                """,
                unsafe_allow_html=True
            )


        # ====== 詳細コメント（トグル：必ず Streamlit）=====
        with info_col:
            detail_key = f"show_comment_{beer_id_safe}"
            if detail_key not in st.session_state:
                st.session_state[detail_key] = False

            if r.detailed_comment:
                if st.button("詳細コメント", key=f"comment_btn_{beer_id_safe}"):
                    st.session_state[detail_key] = not st.session_state[detail_key]

                if st.session_state[detail_key]:
                    st.markdown(
                        f'<div class="comment-card">{r.detailed_comment}</div>',
                        unsafe_allow_html=True
                    )

        # ====== 旧 col4（❌ボタン）=====
        with remove_col:
            if st.button("❌", key=f"remove_btn_{beer_id_safe}"):
                remove_beer(beer_id_safe)

# ---------- 表示モード判定 ----------
is_price_sort     = sort_option == "価格（低）"
is_abv_low_sort   = sort_option == "ABV（低）"
is_abv_high_sort  = sort_option == "ABV（高）"
is_random_sort    = sort_option == "ランダム順"

# 並び順を最優先する条件
disable_grouping = (
    is_price_sort
    or is_abv_low_sort
    or is_abv_high_sort
    or is_random_sort
)

# ===== セッション状態の初期化（必須・1回だけ）=====
if "open_beer_id" not in st.session_state:
    st.session_state.open_beer_id = None


# ---------- 表示条件が変わったら詳細系を閉じる ----------
if "prev_view_state" not in st.session_state:
    st.session_state["prev_view_state"] = current_view_state

if st.session_state["prev_view_state"] != current_view_state:
    # 詳細コメントを閉じる
    for key in list(st.session_state.keys()):
        if key.startswith("show_comment_"):
            del st.session_state[key]

    # ★ 醸造所詳細を閉じる
    st.session_state.open_beer_id = None

st.session_state["prev_view_state"] = current_view_state



# ---------- Render ----------
if disable_grouping:
    for r in display_df.itertuples(index=False):
        try:
            beer_id_safe = int(float(r.id))
        except (ValueError, TypeError):
            continue

        if beer_id_safe in st.session_state["removed_ids"]:
            continue

        render_beer_card(
            r,
            beer_id_safe,
            r.brewery_jp,
            f"nogroup_{beer_id_safe}",   # ← ダミーでOK
            brewery_beers_map.get(r.brewery_jp, pd.DataFrame())
        )

else:
    breweries_to_show = display_df["brewery_jp"].unique()

    for b_idx, brewery in enumerate(breweries_to_show):
        brewery_beers = brewery_beers_map.get(brewery, pd.DataFrame())
        brewery_beers = brewery_beers[brewery_beers["stock_status"] == "○"]

    for i, r in enumerate(brewery_beers.itertuples(index=False)):
            beer_id_safe = int(float(r.id))

        if beer_id_safe in st.session_state["removed_ids"]:
            continue

        render_beer_card(
            r,
            beer_id_safe,
            brewery,
            f"{b_idx}_{i}",   # ← これが決定打
            brewery_beers
        )

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
            st.rerun()
else:
    # optional: show nothing or a small message
    pass






















