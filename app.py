
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


@st.cache_data(
    hash_funcs={pd.DataFrame: lambda _: None}
)
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

    d = df.copy()

    # --- 在庫フィルタ ---
    d = d[
        (d["stock_status"] == "○")
        | (show_take_order & (d["stock_status"] == "△"))
        | (show_no_stock & (d["stock_status"] == "×"))
    ]

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

# ===== ★ここに追加（③）=====
@st.cache_data
def get_brewery_beers(
    df_all,
    brewery_jp,
    show_take_order,
    show_no_stock
):
    d = df_all[df_all["brewery_jp"] == brewery_jp]

    d = d[
        (d["stock_status"] == "○") |
        (show_take_order & (d["stock_status"] == "△")) |
        (show_no_stock & (d["stock_status"] == "×"))
    ]

    return d

# --- load_data の外 ---
df_all = load_data()
df = df_all


df_instock = df[df["stock_status"] == "○"]

# ---------- Initialize show limit and filter signature ----------
if "show_limit" not in st.session_state:
    st.session_state.show_limit = 20   # ▼ Step1: 初期表示件数（20件）
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
        st.session_state.show_limit = 20
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
    margin:5px; 
    display:inline-block; 
    vertical-align:top; 
    min-width: 150px;  /* 任意で最小幅を設定 */
    max-width: 450px;       /* 任意で最大幅 */
    text-align:center !important; 
}
/* ビール画像を固定幅にして横スクロール可能に */
.detail-card img {
    width: 180px;          /* 画像は固定幅 */
    height: auto;
    object-fit: contain;
}

/* 横スクロール用ラッパー */
.brewery-beer-list > div {
    white-space: nowrap;
    overflow-x: auto;
}

/* brewery-beer-list 横スクロール */
.brewery-beer-list { margin-top:10px; }

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
            "醸造所順",
            "スタイル順",
            "ランダム順"
        ]

        sort_option = st.selectbox(
            "並び替え",
            options=sort_options,
            index=sort_options.index(st.session_state.get("sort_option", "名前順")),
            key="sort_option",
            label_visibility="collapsed"
        )

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
                if key in st.session_state:
                    del st.session_state[key]

            # 4. 醸造所詳細・ビール詳細のキーも削除
                for key in list(st.session_state.keys()):
                    if key.startswith("show_detail_") or key.startswith("brewery_btn_"):
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

    # ---- 国一覧（英語）----
    countries = sorted(
        df_all["country"]
        .replace("", pd.NA)
        .dropna()
        .unique()
    )


    # 日本語表示用に変換
    countries_display = ["すべて"] + [country_map.get(c, c) for c in countries]


    # session_state 初期化
    if "country_radio" not in st.session_state:
        st.session_state["country_radio"] = "ベルギー"

    # ---- UI（radio）----
    country_choice_display = col_country.radio(
        "国",
        countries_display,
        horizontal=True,
        key="country_radio"
    )


    # 表示用（日本語） → 内部用（英語）
    if country_choice_display == "すべて":
        country_choice = "すべて"
    else:
        country_choice = {
            v: k for k, v in country_map.items()
        }.get(country_choice_display, country_choice_display)



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

# ---------- Step4: style 選択を filtered に適用 ----------
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
    filtered = filtered.sort_values(by="price_num", ascending=True, na_position="last")
elif sort_option == "醸造所順":
    filtered = filtered.sort_values(by="brewery_jp", key=lambda x: x.map(locale_key))
elif sort_option == "スタイル順":
    filtered = filtered.sort_values(
        by="style_main_jp",
        key=lambda x: x.map(locale_key)
    )

elif sort_option == "ランダム順":
    import numpy as np
    filtered = (
        filtered
        .assign(_rand=np.random.rand(len(filtered)))
        .sort_values("_rand")
        .drop("_rand", axis=1)
    )


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


# ---------- Render Cards ----------

# --- カード描画関数 ---
def render_beer_card(r, beer_id_safe, brewery):

    # ★ brewery_dict が無い前提で安全に処理
    brewery_data = {}

    if "brewery_dict" in globals():
        brewery_data = brewery_dict.get(brewery, {})

    col1, col2, col3, col4 = st.columns(
        [1.5, 2, 4, 0.5],
        vertical_alignment="center"
    )

    if brewery_data.get("brewery_description"):
        st.caption(brewery_data["brewery_description"])


    # 左：醸造所情報
    with col1:
        # use img tag here to allow lazy loading; Streamlit's st.image always loads immediately
        brewery_img = r.brewery_image_url or DEFAULT_BREWERY_IMG
        st.markdown(f'<img src="{brewery_img}" width="100" loading="lazy">', unsafe_allow_html=True)
        st.markdown(f"<b>{r.brewery_local}</b><br>{r.brewery_jp}",unsafe_allow_html=True)

        brewery_city = safe_str(r.city)
        brewery_country = safe_str (r.country)
        flag_img = country_flag_url.get(brewery_country, "")

        # 国旗付きで city / country を表示
        if flag_img:
            st.markdown(
                f"{brewery_city}<br><img src='{flag_img}' width='20'> {brewery_country}",
                unsafe_allow_html=True
            )
        else:
            st.markdown(f"{brewery_city}<br>{brewery_country}", unsafe_allow_html=True)


    # 醸造所詳細ボタン
    detail_key = f"show_detail_{brewery}_{beer_id_safe}"
    for r in display_df.itertuples(index=False):
        key = f"show_detail_{r.brewery_jp}_{int(r.id)}"
        st.session_state[detail_key] = False
    show_key = f"brewery_btn_{brewery}_{beer_id_safe}"
    if st.button("醸造所詳細を見る", key=show_key):
        st.session_state[detail_key] = not st.session_state[detail_key]

    # 醸造所詳細
    if st.session_state[detail_key]:

    # ★ ここで必ず定義する ★
        brewery_beers_all = get_brewery_beers(
            filtered_base,
            brewery,
            show_take_order,
            show_no_stock
        )
        
        if brewery_data.get("brewery_description"):
            st.markdown(f"**醸造所説明:** {brewery_data.get('brewery_description')}")

        st.markdown("### この醸造所のビール一覧")

        cards = [
            '<div class="brewery-beer-list"><div style="white-space: nowrap; overflow-x: auto;">'
        ]

        # ★ iterrows → itertuples
        for b in brewery_beers_all.itertuples(index=False):

            abv = f"ABV {b.abv_num}%" if pd.notna(b.abv_num) else ""
            vol = f"{int(b.volume_num)}ml" if pd.notna(b.volume_num) else ""

            price = ""
            if pd.notna(b.price_num):
                price = "ASK" if b.price_num == 0 else f"¥{int(b.price_num)}"

            vintage = ""
            if pd.notna(b.vintage) and str(b.vintage).strip():
                vintage = str(b.vintage).strip()

            name_local = (b.name_local or "").split("/", 1)[-1].strip()
            name_jp    = (b.name_jp or "").split("/", 1)[-1].strip()

            specs = " | ".join(filter(None, [abv, vol, vintage, price]))

            cards.append(
                '<div class="detail-card" style="display:inline-block; margin-right:10px;text-align:center;">'
                f'<img src="{b.beer_image_url or DEFAULT_BEER_IMG}" loading="lazy"><br>'
                f'<div class="beer-name"><b>{name_local}</b></div>'
                f'<div class="beer-name">{name_jp}</div>'
                f'<div class="beer-spec">{specs}</div>'
                '</div>'
            )

        cards.append("</div></div>")
        st.markdown("".join(cards), unsafe_allow_html=True)

    # 中央：ビール画像
    with col2:
        beer_img = r.beer_image_url or DEFAULT_BEER_IMG
          
        untappd_url = r.untappd_url
        st.markdown(
            f"""
            <div style="
                display: flex;
                flex-direction: column;
                justify-content: center;  /* 上下中央寄せ */
                align-items: center;      /* 横中央寄せ */
                height: 100%;             /* 親コンテナいっぱい */
            ">
                <img src="{beer_img}" style="height:150px; object-fit: contain;" loading="lazy">
                <a href="{untappd_url}" target="_blank">
                    style="
                        display: inline-block;
                        background-color: #FFD633;
                        color: #000;
                        padding: 4px 10px;
                        border-radius: 6px;
                        text-decoration: none;
                        font-weight: 600;
                        margin-top: 6px;
                    ">
                    UNTAPPD
                </a>
            </div>
            """,
            unsafe_allow_html=True,
        )



    # 右：ビール情報
    with col3:
        st.markdown(f"<b>{r.name_local}</b><br>{r.name_jp}",unsafe_allow_html=True)
        style_line = " / ".join(filter(None, [r.style_main_jp, r.style_sub_jp]))
        st.markdown(style_line, unsafe_allow_html=True)
        info_arr = []
        if pd.notna(r.abv_num): info_arr.append(f"ABV {r.abv_num}%")
        if pd.notna(r.volume_num): info_arr.append(f"{int(r.volume_num)}ml")
        vintage_val = r.vintage
        if pd.notna(vintage_val) and str(vintage_val).strip() != "":
            info_arr.append(str(vintage_val).strip())
        if pd.notna(r."price_num"):
            if r.price_num == 0:
                info_arr.append("ASK")
            else:
                info_arr.append(f"¥{int(r.price_num)}")
        st.markdown(" | ".join(info_arr), unsafe_allow_html=True)
        if r."comment":
            st.markdown(r."comment", unsafe_allow_html=True)
        if r."detailed_comment":
            st.markdown(
                f"<details><summary>詳細コメント</summary>{r.detailed_comment}</details>",
                unsafe_allow_html=True
            )

    # ❌ボタン
    with col4:
        button_key = f"remove_btn_{beer_id_safe}"
        if st.button("❌", key=button_key):
            remove_beer(beer_id_safe)

# ---------- Removed beers tracking ----------
def remove_beer(beer_id):
    beer_id_int = int(float(beer_id))
    st.session_state["removed_ids"].add(beer_id_int)


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


# ---------- Render ----------
if disable_grouping:
    # 🔹 並び順をそのまま表示（醸造所でまとめない）
    for r in display_df.itertuples(index=False):
        try:
            beer_id_safe = int(float(r["id"]))
        except (ValueError, TypeError):
            continue

        if beer_id_safe in st.session_state["removed_ids"]:
            continue

        render_beer_card(r, beer_id_safe, r["brewery_jp"])

else:
    # 🔹 通常表示（醸造所ごとにまとめる）
    breweries_to_show = display_df["brewery_jp"].unique()

    for brewery in breweries_to_show:
        brewery_beers = display_df[display_df["brewery_jp"] == brewery]

        for _, r in brewery_beers.iterrows():
            try:
                beer_id_safe = int(float(r["id"]))
            except (ValueError, TypeError):
                continue

            if beer_id_safe in st.session_state["removed_ids"]:
                continue

            render_beer_card(r, beer_id_safe, brewery)


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
# Show button below the list; if clicked, increase limit by 20
if st.session_state.show_limit < len(filtered):
    # use container to place button nicely
    with st.container():
        if st.button("🔽もっと見る🔽", use_container_width=True):
            st.session_state.show_limit += 20
            st.rerun()
else:
    # optional: show nothing or a small message
    pass













