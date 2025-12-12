
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
df = df_all.copy()

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

            # 2. その他のUI状態も初期化
            for key in ["search_text", "sort_option", "size_choice", "abv_slider", "price_slider", "country_radio"]:
                if key in st.session_state:
                    del st.session_state[key]

            # 3. 醸造所詳細・ビール詳細のキーも削除
                for key in list(st.session_state.keys()):
                    if key.startswith("show_detail_") or key.startswith("brewery_btn_"):
                        del st.session_state[key]


            # 4. 必要に応じて初期値をセット
            st.session_state["search_text"] = ""
            st.session_state["sort_option"] = "名前順"
            st.session_state["size_choice"] = "小瓶（≤500ml）"
            st.session_state["abv_slider"] = (0.0, 20.0)
            st.session_state["price_slider"] = (0, 20000)
            st.session_state["show_out_of_stock"] = False

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

    # 国リスト生成（取り寄せ表示OFFの場合は在庫商品の国だけに絞る）
    df_country_source = df.copy()

    # ○（在庫あり）を常に表示
    # △（取り寄せ）は show_take_order が True の時だけ表示
    # ×（在庫なし）は show_no_stock が True の時だけ表示
    filtered = df.copy()

    filtered = filtered[
        (filtered["stock_status"] == "○")
        | (show_take_order & (filtered["stock_status"] == "△"))
        | (show_no_stock & (filtered["stock_status"] == "×"))
    ]

    countries = sorted(
        df_country_source["country"].replace("", pd.NA).dropna().unique()
    )

    # 日本語表示用に変換
    countries_display = ["すべて"] +[country_map.get(c, c) for c in countries]

    # session_state 初期化
    if "country_radio" not in st.session_state:
        st.session_state["country_radio"] = "すべて"

    country_choice_display = col_country.radio(
        "国",
        countries_display,
        index=0,
        horizontal=True,
        key="country_radio"
    )

    # 選択された日本語名を元の英語名に変換してフィルター用に格納
    if country_choice_display == "すべて":
        country_choice = "すべて"
    else:
        # 日本語 → 英語
        country_choice = {v: k for k, v in country_map.items()}.get(country_choice_display, country_choice_display)


    # ---- 在庫切り替えによってスタイル用データを変更 ----
    df_style_source = filtered.copy()

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

    # スタイル一覧（他のフィルターを反映した候補を出す）
    st.markdown("**スタイル（メイン）で絞り込み**")

    # ベースデータ（在庫表示設定に応じて切替）
    df_style_candidates = filtered.copy()

    # --- 他フィルターを反映（ただし「スタイルの選択」はここでは適用しない） ---
    # 1) 検索テキスト（フリー検索）を反映
    if search_text and search_text.strip():
        kw = search_text.strip().lower()
        text_cols = ["name_local","name_jp","brewery_local","brewery_jp","style_main_jp","style_sub_jp",
                     "comment","detailed_comment","untappd_url","jan"]
        temp = df_style_candidates[text_cols].fillna("").astype(str).apply(lambda col: col.str.lower())
        mask = False
        for c in temp.columns:
            mask = mask | temp[c].str.contains(kw, na=False)
        df_style_candidates = df_style_candidates[mask]

    # 2) サイズフィルター（radio）を反映
    if size_choice == "小瓶（≤500ml）":
        df_style_candidates = df_style_candidates[df_style_candidates["volume_num"].notna() & (df_style_candidates["volume_num"].astype(float) <= 500.0)]
    elif size_choice == "大瓶（≥500ml）":
        df_style_candidates = df_style_candidates[df_style_candidates["volume_num"].notna() & (df_style_candidates["volume_num"].astype(float) >= 500.0)]

    # 3) ABV / 価格フィルターを反映
    df_style_candidates = df_style_candidates[
        (df_style_candidates["abv_num"].fillna(-1) >= float(abv_min)) &
        (df_style_candidates["abv_num"].fillna(999) <= float(abv_max))
    ]
    df_style_candidates = df_style_candidates[
        (df_style_candidates["price_num"].fillna(-1) >= int(price_min)) &
        (df_style_candidates["price_num"].fillna(10**9) <= int(price_max))
    ]

    # 4) 国フィルターを反映
    if country_choice != "すべて":
        df_style_candidates = df_style_candidates[df_style_candidates["country"] == country_choice]

    # ここまでで style 候補を決定（空文字を除去してソート）
    styles_available = sorted(
        df_style_candidates["style_main_jp"].replace("", pd.NA).dropna().unique(),
        key=locale_key
    )

    selected_styles = []

    # チェックボックス描画（既存ロジックそのまま）
    if len(styles_available) > 0:
        ncols = min(6, len(styles_available))
        style_cols = st.columns(ncols)

        for i, s in enumerate(styles_available):
            col = style_cols[i % ncols]
            state_key = f"style_{s}"

            # キーが存在しない場合は False に初期化しておく（既存の挙動を維持）
            if state_key not in st.session_state:
                st.session_state[state_key] = False

            checked = col.checkbox(s, key=state_key)

            if checked:
                selected_styles.append(s)


# ---------- Filtering ----------
filtered = df.copy()

# ▼ Step2: vectorized search (apply を避ける)
if search_text and search_text.strip():
    kw = search_text.strip().lower()
    # select columns to search
    text_cols = ["name_local","name_jp","brewery_local","brewery_jp","style_main_jp","style_sub_jp",
                 "comment","detailed_comment","untappd_url","jan"]
    # prepare a DataFrame of lower-cased strings
    temp = filtered[text_cols].fillna("").astype(str).apply(lambda col: col.str.lower())
    mask = False
    for c in temp.columns:
        mask = mask | temp[c].str.contains(kw, na=False)
    filtered = filtered[mask]

# size
if size_choice=="小瓶（≤500ml）":
    filtered=filtered[filtered["volume_num"].notna() & (filtered["volume_num"].astype(float)<=500.0)]
elif size_choice=="大瓶（≥500ml）":
    filtered=filtered[filtered["volume_num"].notna() & (filtered["volume_num"].astype(float)>=500.0)]

# abv / price
filtered = filtered[
    (filtered["abv_num"].fillna(-1) >= float(abv_min)) & 
    (filtered["abv_num"].fillna(999) <= float(abv_max))
]
filtered = filtered[
    (filtered["price_num"].fillna(-1) >= int(price_min)) & 
    (filtered["price_num"].fillna(10**9) <= int(price_max))
]

if selected_styles:
    filtered = filtered[filtered["style_main_jp"].isin(selected_styles)]

# country
if country_choice != "すべて":
    filtered = filtered[filtered["country"] == country_choice]

# 在庫なしチェックの適用はメイン一覧のみ
filtered = filtered[
    (filtered["stock_status"] == "○") |
    (show_take_order & (filtered["stock_status"] == "△")) |
    (show_no_stock & (filtered["stock_status"] == "×"))
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
    filtered = filtered.sort_values(by="style_main_jp", key=lambda x: x.map(locale_key))
if sort_option == "ランダム順":
    import numpy as np
    # ID列に対してランダムな数を割り当ててソート
    filtered = filtered.assign(
        _rand=np.random.rand(len(filtered))
    ).sort_values('_rand').drop('_rand', axis=1)

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


    col1, col2, col3, col4 = st.columns([1.5,2,4,0.5], vertical_alignment="center")

    # 左：醸造所情報
    with col1:
        # use img tag here to allow lazy loading; Streamlit's st.image always loads immediately
        brewery_img = r.get("brewery_image_url") or DEFAULT_BREWERY_IMG
        st.markdown(f'<img src="{brewery_img}" width="100" loading="lazy">', unsafe_allow_html=True)
        st.markdown(f"<b>{r.get('brewery_local')}</b><br>{r.get('brewery_jp')}", unsafe_allow_html=True)

        brewery_city = safe_str(r.get('city'))
        brewery_country = safe_str(r.get('country'))
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
    if detail_key not in st.session_state:
        st.session_state[detail_key] = False
    show_key = f"brewery_btn_{brewery}_{beer_id_safe}"
    if st.button("醸造所詳細を見る", key=show_key):
        st.session_state[detail_key] = not st.session_state[detail_key]

    # 醸造所詳細
    if st.session_state[detail_key]:
        if brewery_data.get("brewery_description"):
            st.markdown(f"**醸造所説明:** {brewery_data.get('brewery_description')}")

        st.markdown("### この醸造所のビール一覧")

        # 「○/△/×」チェックを反映

        brewery_beers_all = df_all[df_all["brewery_jp"] == brewery]

        brewery_beers_all = brewery_beers_all[
            (brewery_beers_all["stock_status"] == "○") |
            (show_take_order & (brewery_beers_all["stock_status"] == "△")) |
            (show_no_stock & (brewery_beers_all["stock_status"] == "×"))
        ]


        cards = ['<div class="brewery-beer-list"><div style="white-space: nowrap; overflow-x: auto;">']

        for _, b in brewery_beers_all.iterrows():
            abv = f"ABV {b.get('abv_num')}%" if pd.notna(b.get('abv_num')) else ""
            vol = f"{int(b.get('volume_num'))}ml" if pd.notna(b.get('volume_num')) else ""
            price = ""
            if pd.notna(b.get('price_num')):
                price = "ASK" if b.get('price_num') == 0 else f"¥{int(b.get('price_num'))}"
            # ★★ vintage 追加 ★★
            vintage_val = b.get("vintage")
            vintage = ""
            if pd.notna(vintage_val) and str(vintage_val).strip() != "":
                vintage = str(vintage_val).strip()  # Excel の値だけ表示
              
            name_local = (b.get('name_local') or "").split('/', 1)[-1].strip()
            name_local_html = f'<div class="beer-name">{name_local}</div>'
            name_jp = (b.get('name_jp') or "").split('/', 1)[-1].strip()
            name_jp_html = f'<div class="beer-name">{name_jp}</div>'

                
            specs = " | ".join(filter(None, [abv, vol, vintage, price]))

            card_html = (
                '<div class="detail-card" style="display:inline-block; margin-right:10px;text-align:center;">'
                f'<img src="{b.get("beer_image_url") or DEFAULT_BEER_IMG}" loading="lazy"><br>'
                f'<b>{name_local_html}</b><br>'
                f'{name_jp_html}<br>'
                f'<div class="beer-spec" style="text-align:center; width:100%;">{specs}</div>'
                '</div>'
            )
            cards.append(card_html)
        cards.append('</div></div>')
        cards_html = "".join(cards)
        st.markdown(cards_html, unsafe_allow_html=True)

    # 中央：ビール画像
    with col2:
        beer_img = r.get("beer_image_url") or DEFAULT_BEER_IMG
          
        untappd_url = r.get("untappd_url")
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
                <a href="{r.get("untappd_url")}" target="_blank"
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
        st.markdown(f"<b>{r.get('name_local')}</b><br>{r.get('name_jp')}", unsafe_allow_html=True)
        style_line = " / ".join(filter(None, [r.get("style_main_jp"), r.get("style_sub_jp")]))
        st.markdown(style_line, unsafe_allow_html=True)
        info_arr = []
        if pd.notna(r.get("abv_num")): info_arr.append(f"ABV {r.get('abv_num')}%")
        if pd.notna(r.get("volume_num")): info_arr.append(f"{int(r.get('volume_num'))}ml")
        vintage_val = r.get("vintage")
        if pd.notna(vintage_val) and str(vintage_val).strip() != "":
            info_arr.append(str(vintage_val).strip())
        if pd.notna(r.get("price_num")):
            if r.get("price_num") == 0:
                info_arr.append("ASK")
            else:
                info_arr.append(f"¥{int(r.get('price_num'))}")
        st.markdown(" | ".join(info_arr), unsafe_allow_html=True)
        if r.get("comment"):
            st.markdown(r.get("comment"), unsafe_allow_html=True)
        if r.get("detailed_comment"):
            st.markdown(
                f"<details><summary>詳細コメント</summary>{r.get('detailed_comment')}</details>",
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


# Step1: 並び替えがランダム順かどうか
is_random_sort = st.session_state.get("sort_option") == "ランダム順"


# --- ランダム順の処理 ---
if is_random_sort:
    # 完全ランダム表示：display_df をシャッフル
    import numpy as np
    display_df = (
        display_df
        .assign(_rand=np.random.rand(len(display_df)))
        .sort_values('_rand')
        .drop('_rand', axis=1)
    )

    # ランダム順は醸造所でまとめない
    for _, r in display_df.iterrows():
        try:
            beer_id_safe = int(float(r["id"]))
        except (ValueError, TypeError):
            continue

        # 削除リストに入っていればスキップ
        if beer_id_safe in st.session_state["removed_ids"]:
            continue

        # カード描画
        render_beer_card(r, beer_id_safe, r["brewery_jp"])

# --- 通常（醸造所ごと）の処理 ---
else:
    breweries_to_show = display_df["brewery_jp"].unique()

    for brewery in breweries_to_show:
        brewery_beers = display_df[display_df["brewery_jp"] == brewery]

        # カード描画
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


