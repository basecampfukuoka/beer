import streamlit as st
import pandas as pd
import random
from pyuca import Collator  # <- 日本語ソート用
import os

# ---------- Google Sheets 用ライブラリ ----------
import gspread
from google.oauth2.service_account import Credentials

# ---------- Google Sheets 設定 ----------
SHEET_KEY = "1VxyGPBc4OoLEf6GeqVGKk3m1BCEcsBMKMHJsmGmc62A"
SHEET_NAME = "Sheet1"  # 読み書きするシート名


# ---------- Page config ----------
st.set_page_config(page_title="Craft Beer List", layout="wide")

# ---------- 管理バー描画関数 ----------
def render_admin_bar():
    color = "#ff7878"  # 通常の赤
    if st.session_state.get("save_success_flash", False):
        color = "#78ff78"  # 保存成功時は緑

    st.markdown(f"""
    <style>
    .admin-top-bar {{
        background: {color};
        border-bottom: 1px solid #ffcccc;
        color: #7a0000;
        font-weight: 600;
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 999999;m
        backdrop-filter: blur(2px);
        height: 44px;
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
    }}
    </style>
    <div class="admin-top-bar">
        🛠 管理モード（yakuzen_beer）
    </div>
    """, unsafe_allow_html=True)

    # フラッシュフラグはページ描画後リセット
    if st.session_state.get("save_success_flash", False):
        st.session_state["save_success_flash"] = False


# ---------- 管理者ページ ----------
is_admin = "yakuzen_beer" in st.query_params

if is_admin:
    render_admin_bar()

    st.markdown("""
    <style>

    /* 背景 */
    .stApp {
        background-color: #ffe6e6;
    }

    /* 上固定 管理バー */
    .admin-top-bar {
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 44px;
        background: rgba(255, 120, 120, 0.18);
        border-bottom: 1px solid #ffcccc;
        color: #7a0000;
        font-weight: 600;
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 999999;
        backdrop-filter: blur(2px);
    }

    /* 上バー分の余白 */
    .block-container {
        padding-top: 60px !important;
    }

    /* ❌ バツ消す */
    .admin-top-bar button,
    .admin-top-bar svg {
        display: none !important;
    }

    button[title="Close"] {
        display: none !important;
    }

    /* ❌ 左サイドバー削除 */
    section[data-testid="stSidebar"] {
        display: none !important;
    }

    /* メイン横幅最大化 */
    .main .block-container {
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }

    </style>

    <div class="admin-top-bar">
        🛠 管理モード（yakuzen_beer）
    </div>
    """, unsafe_allow_html=True)


# ---------- Defaults ----------
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

def get_countries_for_filter(df, admin=False):

    target = df if admin else df[df["stock_status"] == "○"]

    return sorted(
        target["country"]
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
    d = df.copy(deep=True)

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

@st.cache_resource
def get_collator():
    from pyuca import Collator
    return Collator()

def locale_key(x):
    collator = get_collator()
    s = "" if x is None else str(x).strip()
    return collator.sort_key(s)

# ---------- Load data ----------
@st.cache_data
def load_data():

    # --- Google 認証 ---
    info = st.secrets["gcp_service_account"]
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_KEY).worksheet(SHEET_NAME)

    
    # --- 全データ取得 ---
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

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
    df["yomi_sort"] = df["yomi"].apply(locale_key)

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

def update_row(beer_id, stock, price, comment, detailed_comment):
    try:
        df = load_data()

        mask = df["id"] == beer_id
        if not mask.any():
            st.error("IDが見つかりません")
            return

        # --- 単純代入 ---
        df.loc[mask, "in_stock"] = stock
        df.loc[mask, "price"] = price
        df.loc[mask, "comment"] = comment
        df.loc[mask, "detailed_comment"] = detailed_comment

        # ==========================
        # 🔥 ここから超重要
        # ==========================

        df = df.fillna("")

        # list → 文字列化
        df = df.map(
            lambda x: ", ".join(map(str, x)) if isinstance(x, list) else x
        )
        # すべて文字列化（Sheets安全）
        df = df.astype(str)

        # ==========================

        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=SCOPES
        )

        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY).worksheet(SHEET_NAME)

        sheet.update([df.columns.tolist()] + df.values.tolist())

        st.cache_data.clear()
        st.session_state.edit_id = None
        st.session_state["save_success_flash"] = True

        st.success("保存しました")
        st.rerun()

    except Exception as e:
        st.error(f"保存中にエラーが発生しました: {e}")

# --- load_data の外 ---
df_all = load_data()

if is_admin:
    base_df = df_all
else:
    base_df = df_all[df_all["stock_status"] == "○"]

# ---------- 新規追加 master ----------
def get_brewery_master(df):
    return (
        df[
            (df["brewery_jp"] != "") &
            (df["brewery_local"] != "")
        ][["brewery_jp", "brewery_local"]]
        .drop_duplicates()
        .sort_values("brewery_jp")
        .to_dict("records")
    )

def get_style_master(df):
    styles = (
        df[["style_main_jp", "style_sub_jp"]]
        .fillna("")
    )

    main = styles["style_main_jp"].unique().tolist()
    sub  = styles["style_sub_jp"].unique().tolist()

    main = sorted({s for s in main if s.strip()})
    sub  = sorted({s for s in sub if s.strip()})

    return main, sub

def add_new_beer_simple(
    name_jp, name_local, brewery_jp, brewery_local,
    country, style_main_jp, style_sub_jp,
    abv, volume, price, in_stock,
    beer_image_url, untappd_url, comment, detailed_comment
):
    try:
        # --- 認証 ---
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]

        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"],
            scopes=SCOPES
        )

        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY).worksheet(SHEET_NAME)

        # --- 既存データ取得（ID採番用） ---
        df = load_data()

        if "id" in df.columns and not df["id"].isna().all():
            new_id = int(pd.to_numeric(df["id"], errors="coerce").max()) + 1
        else:
            new_id = 1

        # --- 新規行 ---
        new_row = {
            "id": new_id,
            "name_jp": name_jp,
            "name_local": name_local,
            "yomi": "",
            "brewery_local": brewery_local,
            "brewery_jp": brewery_jp,
            "country": country,
            "city": "",
            "brewery_description": "",
            "brewery_image_url": "",
            "style_main": "",
            "style_main_jp": style_main_jp,
            "style_sub": "",
            "style_sub_jp": style_sub_jp,
            "abv": abv,
            "volume": volume,
            "vintage": "",
            "price": price,
            "comment": comment,
            "detailed_comment": detailed_comment,
            "in_stock": in_stock,
            "untappd_url": untappd_url,
            "jan": "",
            "beer_image_url": beer_image_url,
        }

        # --- ヘッダー順に合わせる ---
        headers = sheet.row_values(1)
        row_data = [str(new_row.get(col, "")) for col in headers]

        sheet.append_row(row_data)

        st.cache_data.clear()
        st.success("ビールを追加しました！")
        st.rerun()

    except Exception as e:
        st.error(f"追加中にエラーが発生しました: {e}")


# ---------- ランダム順用 state 初期化 ----------
if "prev_sort_option" not in st.session_state:
    st.session_state.prev_sort_option = None

if "random_seed" not in st.session_state:
    st.session_state.random_seed = None

if "edit_id" not in st.session_state:
    st.session_state.edit_id = None


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

    # 国ラジオ（日本語） → country_choice（英語） に変換
    country_radio = st.session_state.get("country_radio", "すべて")
    if country_radio == "すべて":
        country_choice = "すべて"
    else:
        country_choice = next(
            (k for k, v in COUNTRY_INFO.items() if v.get("jp") == country_radio),
            country_radio
        )

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

# ---------- 管理モード ----------
if is_admin:
    st.sidebar.success("管理モード")

# ---------- Filters UI ----------
with st.expander("フィルター / 検索を表示", False):
    st.markdown('<div id="search_bar"></div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns([0.5,8,0.5,3.5,5])

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
        st.markdown("⇅", unsafe_allow_html=True)

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
            for s in df_all["style_main_jp"].dropna().unique():
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
            

            # 4.詳細コメント state を全削除
            for key in list(st.session_state.keys()):
                if key.startswith("detail_"):
                    del st.session_state[key]

            st.rerun()

    # ===== 2行目：国（Excel から自動取得・日本語化） =====
    col_country_title, col_country, col_stock1 = st.columns([0.2,4,1.5])

    # 国リストを在庫フィルタに合わせて取得
    countries = get_countries_for_filter(base_df, admin=is_admin)

    with col_country_title:
        st.markdown("国", unsafe_allow_html=True)


    # session_state 初期化
    if "country_radio" not in st.session_state:
        st.session_state["country_radio"] = "すべて" if is_admin else "ベルギー"
    # 日本語表示用に変換
    countries_display = ["すべて"] + [COUNTRY_INFO.get(c, {}).get("jp", c) for c in countries]

    with col_country:
        country_choice_display = col_country.radio(
            "国",
            countries_display,
            horizontal=True,
            key="country_radio",
            label_visibility="collapsed"
        )

    # ---- 取り寄せ表示 ----
    with col_stock1:
        show_take_order = col_stock1.checkbox(
            "取り寄せを表示",
            key="show_take_order"
        )


    # 日本語表示 → 内部用（英語）変換
    if country_choice_display == "すべて":
        country_choice = "すべて"
    else:
        country_choice = next(
            (k for k, v in COUNTRY_INFO.items() if v.get("jp") == country_choice_display),
            country_choice_display
        )


    # ===== 3行目：サイズ・ABV・価格 =====
    col_size, col_abv, col_price = st.columns([2.5, 1.5, 1.5])

    with col_size:
        if "size_choice" not in st.session_state:
            st.session_state["size_choice"] = "すべて" if is_admin else "小瓶（≤500ml）"
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
    if not is_admin:
        st.markdown("### スタイルで絞り込み")
    style_ui_placeholder = st.container()

    # ===== 管理画面:醸造所 =====
    brewery_choice = "すべて"  # デフォルト値

    if is_admin:
        # 醸造所リスト取得（重複削除＆ソート）
        breweries = sorted(base_df[["brewery_local","brewery_jp"]].drop_duplicates("brewery_local").values, key=lambda x: x[1])
        # ["すべて"] + 日本語名リスト
        breweries_display = ["すべて"] + [b[1] for b in breweries]

        brewery_choice_display = st.selectbox(
            "醸造所で絞り込み",
            breweries_display,
            key="brewery_filter"
        )

        # 日本語表示 → 内部用（brewery_local）変換
        if brewery_choice_display == "すべて":
            brewery_choice = "すべて"
        else:
            # brewery_local を取得
            brewery_choice = next((b[0] for b in breweries if b[1] == brewery_choice_display), brewery_choice_display)

        
# ---------- Filtering ----------
filtered_base = build_filtered_df(
    base_df,
    search_text=search_text,
    size_choice=size_choice,
    abv_min=abv_min,
    abv_max=abv_max,
    price_min=price_min,
    price_max=price_max,
    country_choice=country_choice,
)

# 管理モード以外は在庫ありだけ
if not is_admin:
    filtered_base = filtered_base[filtered_base["stock_status"] == "○"]

# 管理モード: brewery_choice フィルター適用
if brewery_choice != "すべて":
    filtered_base = filtered_base[filtered_base["brewery_local"] == brewery_choice]
# ---------- Filtering（★1回だけ） ----------
filtered_base = build_filtered_df(
    base_df,
    search_text=search_text,
    size_choice=size_choice,
    abv_min=abv_min,
    abv_max=abv_max,
    price_min=price_min,
    price_max=price_max,
    country_choice=country_choice,
)

# ---------- スタイルフィルター ----------
selected_styles = []  # 管理モードでも未定義エラーを防ぐ

if not is_admin:
    with style_ui_placeholder:
        styles_available = get_style_candidates(filtered_base)
        if styles_available:
            cols = st.columns(min(6, len(styles_available)))
            for i, s in enumerate(styles_available):
                key = f"style_{s}"
                if cols[i % len(cols)].checkbox(s, key=key):
                    selected_styles.append(s)

# ---------- style 選択を filtered に適用 ----------
filtered = filtered_base.copy()
if selected_styles:
    filtered = filtered[filtered["style_main_jp"].isin(selected_styles)]

# ---------- Sorting ----------
if sort_option == "名前順":
    filtered = filtered.sort_values(by="yomi_sort", na_position="last")
elif sort_option == "ABV（低）":
    filtered = filtered.sort_values(by="abv_num", ascending=True, na_position="last")
elif sort_option == "ABV（高）":
    filtered = filtered.sort_values(by="abv_num", ascending=False, na_position="last")
elif sort_option == "価格（低）":
    filtered = (filtered
        .assign(price_sort=filtered["price_num"].replace(0, 10**9))
        .sort_values(by="price_sort", ascending=True, na_position="last")
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

# ---------- Prepare display_df ----------
filtered_count = len(filtered)

st.markdown(f"**表示件数：{filtered_count} 件**")

display_df = filtered.head(st.session_state.show_limit)

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

        # ===== 管理モード 編集UI =====
        if is_admin:

            if st.button("✏ 編集", key=f"edit_{beer_id_safe}"):
                st.session_state.edit_id = beer_id_safe

            if st.session_state.edit_id == beer_id_safe:

                new_stock = st.selectbox(
                    "在庫",
                    ["○","△","×"],
                    index=["○","△","×"].index(r.stock_status),
                    key=f"stock_{beer_id_safe}"
                )

                new_price = st.number_input(
                    "価格",
                    value=int(r.price_num) if r.price_num else 0,
                    step=100,
                    key=f"price_{beer_id_safe}"
                )

                new_comment = st.text_area(
                    "コメント",
                    value=r.comment,
                    key=f"comment_{beer_id_safe}"
                )

                new_detailed_comment = st.text_area(
                    "詳細コメント",
                    value=r.detailed_comment,
                    key=f"detailed_{beer_id_safe}"
                )

                col1, col2 = st.columns(2)

                with col1:
                    if st.button("保存", key=f"save_{beer_id_safe}"):
                        update_row(
                            beer_id_safe,
                            new_stock,
                            new_price,
                            new_comment,
                            new_detailed_comment
                        )

                with col2:
                    if st.button("キャンセル"):
                        st.session_state.edit_id = None


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


# ---------- 新規作成 ----------
st.markdown("---")  # 区切り線

if is_admin:

    # 新規作成フォーム表示フラグの初期化
    if "show_new_beer_form" not in st.session_state:
        st.session_state.show_new_beer_form = False

    # ボタン
    if st.button("➕ 新規ビールを追加"):
        st.session_state.show_new_beer_form = not st.session_state.show_new_beer_form

    # フラグがTrueならフォームを表示
    if st.session_state.show_new_beer_form:
        with st.form("new_beer_form"):
            st.markdown("### 新規ビール追加フォーム")

            # 入力項目
            name_jp = st.text_input("ビール名（日）")
            name_local = st.text_input("ビール名（英）")

            country = st.selectbox("国", list(COUNTRY_INFO.keys()))

            brewery_master = get_brewery_master(df_all)

            brewery_options = ["（新規入力）"] + [
                b["brewery_jp"] for b in brewery_master
            ]

            brewery_choice = st.selectbox(
                "醸造所（日）",
                brewery_options
            )

            if brewery_choice == "（新規入力）":
            # 新規だけど、入力は「別UI」でやらない
                brewery_jp = ""          # or 後続処理で決める
                brewery_local = ""

            else:
                selected = next(
                    (b for b in brewery_master if b["brewery_jp"] == brewery_choice),
                    None
                )

                if selected is None:
                    st.error("選択された醸造所が見つかりません")
                    st.stop()

                brewery_jp = selected["brewery_jp"]
                brewery_local = selected["brewery_local"]


            style_main_list, style_sub_list = get_style_master(df_all)

            style_main_options = ["（未選択）"] + style_main_list
            style_sub_options  = ["（未選択）"] + style_sub_list

            style_main_jp = st.selectbox(
                "スタイル（メイン）",
                style_main_options
            )

            style_sub_jp = st.selectbox(
                "スタイル（サブ）",
                style_sub_options
            )

            # 未選択は空文字で保存
            if style_main_jp == "（未選択）":
                style_main_jp = ""

            if style_sub_jp == "（未選択）":
                style_sub_jp = ""


            abv = st.number_input("ABV (%)", min_value=0.0, max_value=100.0, step=0.1)
            vintage = st.text_input("ヴィンテージ", placeholder="例：20○○ / OLD / 瓶・缶")

            volume = st.number_input("容量 (ml)", min_value=0, step=50)
            price = st.number_input("価格 (円)", min_value=0, step=100)
            in_stock = st.selectbox("在庫", ["○","△","×"])
            beer_image_url = st.text_input("ビール画像URL")
            untappd_url = st.text_input("Untappd URL")
            comment = st.text_area("コメント")
            detailed_comment = st.text_area("詳細コメント")

            submitted = st.form_submit_button("追加")

            if submitted:
                add_new_beer_simple(
                    name_jp, name_local, brewery_jp, brewery_local,
                    country, style_main_jp, style_sub_jp,
                    abv, volume, price, in_stock,
                    beer_image_url, untappd_url, comment, detailed_comment
                )
                st.success("🍺 ビールを追加しました！")












