import streamlit as st
import pandas as pd
import random
import os
from pyuca import Collator  # 日本語ソート用

# ---------- Google Sheets 用ライブラリ ----------
import gspread
from google.oauth2.service_account import Credentials

# ---------- Google Sheets 設定 ----------
SHEET_KEY = "1VxyGPBc4OoLEf6GeqVGKk3m1BCEcsBMKMHJsmGmc62A"
SHEET_NAME = "Sheet1"

# ---------- Page config ----------
st.set_page_config(page_title="Craft Beer List", layout="wide")

# ---------- Constants ----------
DEFAULT_BEER_IMG = "https://assets.untappd.com/site/assets/images/temp/badge-beer-default.png"
DEFAULT_BREWERY_IMG = "https://assets.untappd.com/site/assets/images/temp/badge-brewery-default.png"

COUNTRY_INFO = {
    "Japan": {"jp":"日本","flag":"https://freesozai.jp/sozai/nation_flag/ntf_131/ntf_131.png"},
    "Belgium": {"jp":"ベルギー","flag":"https://freesozai.jp/sozai/nation_flag/ntf_330/ntf_330.png"},
    "Germany": {"jp":"ドイツ","flag":"https://freesozai.jp/sozai/nation_flag/ntf_322/ntf_322.png"},
    "United States": {"jp":"アメリカ","flag":"https://freesozai.jp/sozai/nation_flag/ntf_401/ntf_401.png"},
    "Netherlands": {"jp":"オランダ","flag":"https://freesozai.jp/sozai/nation_flag/ntf_310/ntf_310.png"},
    "Czech Republic": {"jp":"チェコ","flag":"https://freesozai.jp/sozai/nation_flag/ntf_320/ntf_320.png"},
    "Italy": {"jp":"イタリア","flag":"https://freesozai.jp/sozai/nation_flag/ntf_306/ntf_306.png"},
    "Austria": {"jp":"オーストリア","flag":"https://freesozai.jp/sozai/nation_flag/ntf_309/ntf_309.svg"},
}

# ---------- Helpers ----------
def safe_str(v):
    if pd.isna(v) or v is None: return ""
    return str(v)

def stock_status(val):
    if pd.isna(val): return "×"
    v = str(val).strip()
    if v in ["○","◯","o","O","あり","yes","1","true"]: return "○"
    if v in ["△","取り寄せ"]: return "△"
    return "×"

def try_number(v):
    if pd.isna(v): return None
    s = str(v)
    digits = ''.join(ch for ch in s if ch.isdigit() or ch=='.')
    if digits=="": return None
    try:
        return float(digits) if '.' in digits else int(float(digits))
    except:
        return None

@st.cache_resource
def get_collator():
    return Collator()

def locale_key(x):
    collator = get_collator()
    s = "" if x is None else str(x).strip()
    return collator.sort_key(s)

def get_countries_for_filter(df, admin=False):
    target = df if admin else df[df["stock_status"]=="○"]
    return sorted(target["country"].replace("", pd.NA).dropna().unique())

@st.cache_data
def get_style_candidates(df):
    return sorted(df["style_main_jp"].replace("", pd.NA).dropna().unique(), key=locale_key)

# ---------- Load / Update Data ----------
@st.cache_data
def load_data():
    info = st.secrets["gcp_service_account"]
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_KEY).worksheet(SHEET_NAME)
    data = sheet.get_all_records()
    df = pd.DataFrame(data)
    
    # 必要列を補完
    expected = [
        "id","name_jp","name_local","yomi","brewery_local","brewery_jp","country","city",
        "brewery_description","brewery_image_url","style_main","style_main_jp",
        "style_sub","style_sub_jp","abv","volume","vintage","price","comment","detailed_comment",
        "in_stock","untappd_url","jan","beer_image_url"
    ]
    for c in expected:
        if c not in df.columns: df[c] = pd.NA

    # 数値列変換
    df["abv_num"] = pd.to_numeric(df["abv"], errors="coerce")
    df["volume_num"] = df["volume"].apply(try_number)
    df["price_num"] = df["price"].apply(try_number)

    # 文字列列変換
    str_cols = [
        "name_jp","name_local","brewery_local","brewery_jp","country","city",
        "brewery_description","brewery_image_url","style_main","style_main_jp",
        "style_sub","style_sub_jp","comment","detailed_comment","untappd_url","jan","beer_image_url"
    ]
    for c in str_cols:
        df[c] = df[c].fillna("").astype(str)

    # 在庫ステータス
    df["stock_status"] = df["in_stock"].apply(stock_status)

    # 国旗付与
    df["flag_url"] = df["country"].map(lambda c: COUNTRY_INFO.get(c, {}).get("flag",""))

    # yomi 正規化
    df["yomi"] = df["yomi"].astype(str).str.strip()
    df["yomi_sort"] = df["yomi"].apply(locale_key)

    # 検索用結合列
    search_cols = [
        "name_local","name_jp","brewery_local","brewery_jp",
        "style_main_jp","style_sub_jp","comment",
        "detailed_comment","untappd_url","jan"
    ]
    df["search_blob"] = df[search_cols].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
    return df

def update_row(beer_id, stock, price, comment, detailed_comment):
    try:
        df = load_data()
        idx = df[df["id"]==beer_id].index
        if len(idx)==0:
            st.error("IDが見つかりません")
            return
        df.loc[idx, ["in_stock","price","comment","detailed_comment"]] = stock, price, comment, detailed_comment
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"])
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY).worksheet(SHEET_NAME)
        sheet.update([df.columns.values.tolist()] + df.values.tolist())
        st.cache_data.clear()
        st.session_state.edit_id = None
        st.session_state["save_success_flash"] = True
        st.success("保存しました")
        st.rerun()
    except Exception as e:
        st.error(f"保存中にエラーが発生しました: {e}")

# ---------- Data ----------
df_all = load_data()
is_admin = "yakuzen_beer" in st.query_params
base_df = df_all if is_admin else df_all[df_all["stock_status"]=="○"]

# ---------- Session State 初期化 ----------
for key, default in [
    ("prev_sort_option", None),
    ("random_seed", None),
    ("edit_id", None),
    ("show_limit", 10),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# style_state 初期化
if "style_state_init" not in st.session_state:
    for s in df_all["style_main_jp"].dropna().unique():
        st.session_state[f"style_{s}"] = False
    st.session_state["style_state_init"] = True

# ---------- 管理バー ----------
def render_admin_bar():
    color = "#ff7878"
    if st.session_state.get("save_success_flash", False):
        color = "#78ff78"
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
        z-index: 999999;
        backdrop-filter: blur(2px);
        height: 44px;
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
    }}
    </style>
    <div class="admin-top-bar">🛠 管理モード（yakuzen_beer）</div>
    """, unsafe_allow_html=True)
    if st.session_state.get("save_success_flash", False):
        st.session_state["save_success_flash"] = False

if is_admin:
    render_admin_bar()

# ---------- Filter 関連 ----------
def build_filtered_df(df, search_text, size_choice, abv_min, abv_max, price_min, price_max, country_choice):
    d = df.copy()
    if search_text.strip():
        d = d[d["search_blob"].str.contains(search_text.strip().lower(), na=False)]
    if size_choice=="小瓶（≤500ml）": d = d[d["volume_num"]<=500]
    elif size_choice=="大瓶（≥500ml）": d = d[d["volume_num"]>=500]
    d = d[(d["abv_num"].fillna(-1)>=abv_min) & (d["abv_num"].fillna(999)<=abv_max)]
    d = d[(d["price_num"].fillna(-1)>=price_min) & (d["price_num"].fillna(10**9)<=price_max)]
    if country_choice!="すべて": d = d[d["country"]==country_choice]
    return d

# ---------- Filter Signature ----------
def compute_filter_signature():
    country_radio = st.session_state.get("country_radio","すべて")
    country_choice = country_radio
    keys = [
        st.session_state.get("search_text",""),
        st.session_state.get("sort_option",""),
        st.session_state.get("size_choice",""),
        str(st.session_state.get("abv_slider","")),
        str(st.session_state.get("price_slider","")),
        st.session_state.get("country_radio","")
    ]
    style_keys = [k for k in st.session_state.keys() if k.startswith("style_")]
    style_vals = [f"{k}:{st.session_state.get(k)}" for k in sorted(style_keys)]
    return "|".join(keys+style_vals)

if "prev_filter_sig" not in st.session_state:
    st.session_state.prev_filter_sig = compute_filter_signature()
else:
    current_sig = compute_filter_signature()
    if current_sig != st.session_state.prev_filter_sig:
        st.session_state.show_limit = 10
        st.session_state.prev_filter_sig = current_sig
        for key in list(st.session_state.keys()):
            if key.startswith("detail_") or key=="open_detail":
                del st.session_state[key]

# ---------- フィルター構築 ----------
search_text = st.session_state.get("search_text","")
size_choice = st.session_state.get("size_choice","すべて")
abv_min, abv_max = st.session_state.get("abv_slider",(0.0,20.0))
price_min, price_max = st.session_state.get("price_slider",(0,20000))
country_choice = "すべて"

filtered_base = build_filtered_df(base_df, search_text, size_choice, abv_min, abv_max, price_min, price_max, country_choice)

# ---------- Sorting ----------
sort_option = st.session_state.get("sort_option","名前順")
filtered = filtered_base.copy()
if sort_option=="名前順": filtered = filtered.sort_values("yomi_sort", na_position="last")
elif sort_option=="ABV（低）": filtered = filtered.sort_values("abv_num", ascending=True, na_position="last")
elif sort_option=="ABV（高）": filtered = filtered.sort_values("abv_num", ascending=False, na_position="last")
elif sort_option=="価格（低）":
    filtered = filtered.assign(price_sort=filtered["price_num"].replace(0,10**9)).sort_values("price_sort", ascending=True, na_position="last")
elif sort_option=="ランダム順":
    if st.session_state.prev_sort_option!="ランダム順":
        st.session_state.random_seed = random.randint(0, 10**9)
    filtered = filtered.sample(frac=1, random_state=st.session_state.random_seed)
st.session_state.prev_sort_option = sort_option

# ---------- Display ----------
filtered_count = len(filtered)
st.markdown(f"**表示件数：{filtered_count} 件**")
display_df = filtered.head(st.session_state.show_limit)

# ---------- カード描画 ----------
def render_beer_card(r, beer_id_safe):
    beer_img = r.beer_image_url or DEFAULT_BEER_IMG
    flag_img = r.flag_url
    style_line = " / ".join(filter(None,[r.style_main_jp, r.style_sub_jp]))
    st.markdown('<div class="beer-card">', unsafe_allow_html=True)
    left_col, right_col = st.columns([3,5])
    with left_col:
        st.markdown(f'<div style="display:flex;justify-content:center;align-items:center;height:100%;"><img src="{beer_img}" style="height:170px;object-fit:contain" loading="lazy"></div>', unsafe_allow_html=True)
    with right_col:
        st.markdown(f'{"<img src=\'"+flag_img+"\' width=18 style=vertical-align:middle;margin-right:6px;>" if flag_img else ""}<b>{r.brewery_local}</b> / <span style="color:#666;">{r.brewery_jp}</span>', unsafe_allow_html=True)
        info_arr = []
        if pd.notna(r.abv_num): info_arr.append(f"ABV {r.abv_num}%")
        if pd.notna(r.volume_num): info_arr.append(f"{int(r.volume_num)}ml")
        if pd.notna(r.vintage) and str(r.vintage).strip(): info_arr.append(str(r.vintage).strip())
        if pd.notna(r.price_num): info_arr.append("ASK" if r.price_num==0 else f"¥{int(r.price_num)}")
        beer_info = " | ".join(info_arr)
        st.markdown(f'<a href="{r.untappd_url}" target="_blank" style="text-decoration:none;color:inherit;"><b style="font-size:1.15em;">{r.name_local}</b><br><span style="font-size:0.95em;">{r.name_jp}</span></a><br><span style="color:#666;">{style_line}</span><br>{beer_info}<br>{r.comment or ""}', unsafe_allow_html=True)

for r in display_df.itertuples(index=False):
    try: beer_id_safe = int(float(r.id))
    except: continue
    render_beer_card(r, beer_id_safe)

# ---------- トップへ戻るボタン ----------
st.markdown(
    """
    <div style="margin-bottom:10px;">
        <a href="#search_bar">
            <button style="
                width:100%;
                padding:0.5rem;
                font-size:16px;
                background-color:#f0f0f0;
                border:1px solid #ccc;
                border-radius:4px;
                cursor:pointer;
            ">🔼 トップへ戻る 🔼</button>
        </a>
    </div>
    """,
    unsafe_allow_html=True
)

# ---------- "もっと見る" ボタン ----------
if st.session_state.show_limit < len(filtered):
    with st.container():
        if st.button("🔽もっと見る🔽", use_container_width=True):
            st.session_state.show_limit += 10

# ---------- 管理モード: 新規ビール追加 ----------
def add_new_beer_simple(
    name_jp, name_local, brewery_jp, brewery_local,
    country, style_main_jp, style_sub_jp,
    abv, volume, price, in_stock,
    beer_image_url, untappd_url, comment, detailed_comment
):
    try:
        df = load_data()
        new_id = int(df["id"].max()) + 1 if not df.empty else 1
        new_row = {
            "id": new_id,
            "name_jp": name_jp,
            "name_local": name_local,
            "brewery_jp": brewery_jp,
            "brewery_local": brewery_local,
            "country": country,
            "style_main_jp": style_main_jp,
            "style_sub_jp": style_sub_jp,
            "abv": abv,
            "volume": volume,
            "price": price,
            "in_stock": in_stock,
            "beer_image_url": beer_image_url,
            "untappd_url": untappd_url,
            "comment": comment,
            "detailed_comment": detailed_comment,
            "yomi": name_jp,  # シンプルに日本語名
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"])
        client = gspread.authorize(creds)
        sheet = client.open_by_key(SHEET_KEY).worksheet(SHEET_NAME)
        sheet.update([df.columns.values.tolist()] + df.values.tolist())
        st.cache_data.clear()
        st.success("新しいビールを追加しました")
        st.rerun()
    except Exception as e:
        st.error(f"追加中にエラーが発生しました: {e}")

if is_admin:
    # 新規作成フォームフラグ初期化
    if "show_new_beer_form" not in st.session_state:
        st.session_state.show_new_beer_form = False

    if st.button("➕ 新規ビールを追加"):
        st.session_state.show_new_beer_form = not st.session_state.show_new_beer_form

    if st.session_state.show_new_beer_form:
        with st.form("new_beer_form"):
            st.markdown("### 新規ビール追加フォーム")
            name_jp = st.text_input("ビール名（日本語）")
            name_local = st.text_input("ビール名（現地語）")
            brewery_jp = st.text_input("醸造所名（日本語）")
            brewery_local = st.text_input("醸造所名（現地語）")
            country = st.selectbox("国", list(COUNTRY_INFO.keys()))
            style_main_jp = st.text_input("スタイル（メイン）")
            style_sub_jp = st.text_input("スタイル（サブ）")
            abv = st.number_input("ABV (%)", min_value=0.0, max_value=100.0, step=0.1)
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

# ---------- 管理モード: 編集UI ----------
def render_admin_edit_ui(r, beer_id_safe):
    if st.session_state.edit_id == beer_id_safe:
        new_stock = st.selectbox("在庫", ["○","△","×"], index=["○","△","×"].index(r.stock_status), key=f"stock_{beer_id_safe}")
        new_price = st.number_input("価格", value=int(r.price_num) if r.price_num else 0, step=100, key=f"price_{beer_id_safe}")
        new_comment = st.text_area("コメント", value=r.comment, key=f"comment_{beer_id_safe}")
        new_detailed_comment = st.text_area("詳細コメント", value=r.detailed_comment, key=f"detailed_{beer_id_safe}")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("保存", key=f"save_{beer_id_safe}"):
                update_row(beer_id_safe, new_stock, new_price, new_comment, new_detailed_comment)
        with col2:
            if st.button("キャンセル"):
                st.session_state.edit_id = None

# ---------- ビールカード描画（管理モード統合） ----------
for r in display_df.itertuples(index=False):
    try: beer_id_safe = int(float(r.id))
    except: continue
    render_beer_card(r, beer_id_safe)
    if is_admin:
        if st.button("✏ 編集", key=f"edit_{beer_id_safe}"):
            st.session_state.edit_id = beer_id_safe
        render_admin_edit_ui(r, beer_id_safe)

