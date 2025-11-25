import streamlit as st
import pandas as pd
import unicodedata
from pyuca import Collator

collator = Collator()  

# ---------- Page config ----------
st.set_page_config(page_title="Craft Beer List", layout="wide")

# ---------- Defaults ----------
EXCEL_PATH = "beer_data.xlsx"
DEFAULT_BEER_IMG = "https://assets.untappd.com/site/assets/images/temp/badge-beer-default.png"
DEFAULT_BREWERY_IMG = "https://assets.untappd.com/site/assets/images/temp/badge-brewery-default.png"

# ---------- 国旗 URL ----------
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
    "Italy": "https://freesozai.jp/sozai/nation_flag/ntf_306/ntf_306.png"
}

# ---------- Helpers ----------
def safe_str(v):
    if pd.isna(v) or v is None: return ""
    return str(v)

def is_in_stock(val):
    if pd.isna(val): return False
    if isinstance(val,(int,float)):
        try: return int(val)!=0
        except: return False
    s = str(val).strip().lower()
    return s in ("1","true","あり","yes","y")

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

    df["_in_stock_bool"] = df["in_stock"].apply(is_in_stock)
    df["yomi"] = df["yomi"].astype(str).str.strip()
    df["yomi_sort"] = df["yomi"].apply(lambda x: collator.sort_key(x))
    return df

df_all = load_data()
df = df_all.copy()

# ---------- Custom CSS ----------
st.markdown("""
<style>
.beer-name {
    width: 120px;
    word-wrap: break-word;
    overflow-wrap: break-word;
    text-align: center;
}
.detail-card { 
    background-color: #f0f8ff; 
    border-radius: 8px; 
    padding: 10px; 
    margin:5px; 
    display:inline-block; 
    vertical-align:top; 
    width:140px;   
    text-align:center; 
}
.remove-btn div[data-testid="stButton"] > button:hover {
    opacity: 0.6 !important;
}
.remove-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
}
</style>
""", unsafe_allow_html=True)

# ---------- Filters UI ----------
with st.expander("フィルター / 検索を表示", True):
    c1, c2, c3, c4, c5 = st.columns([0.2,4,0.5,1,0.8])
    with c1:
        st.markdown("🔎", unsafe_allow_html=True)
    with c2:
        search_text = st.text_input(
            "検索",  # 空文字ではなくラベルを指定
            placeholder="フリー検索",
            label_visibility="collapsed",  # UI上は非表示
            key="search_text",
            value=st.session_state.get("search_text", "")
        )
    with c3:
        st.markdown("並び替え", unsafe_allow_html=True)
    with c4:
        sort_options = ["名前順","ABV（低）","ABV（高）","価格（低）","醸造所順","スタイル順"]
        sort_option = st.selectbox(
            "並び替え",  # 内部ラベル
            options=sort_options,
            index=sort_options.index(st.session_state.get("sort_option", "名前順")),
            key="sort_option",
            label_visibility="collapsed"
        )

    with c5:
        if st.button("🔄 リセット"):
            st.session_state.clear()
            st.rerun()

    # 国・サイズ・ABV・価格・スタイルUI
    country_map = {"Japan":"日本","Belgium":"ベルギー","Germany":"ドイツ","United States":"アメリカ",
                   "United Kingdom":"イギリス","Netherlands":"オランダ","Czech Republic":"チェコ",
                   "France":"フランス","Canada":"カナダ","Australia":"オーストラリア",
                   "Italy":"イタリア"}
    countries = sorted(df["country"].replace("", pd.NA).dropna().unique())
    countries_display = ["すべて"] + [country_map.get(c,c) for c in countries]
    if "country_radio" not in st.session_state: st.session_state["country_radio"]="すべて"
    country_choice_display = st.radio("国", countries_display, index=0, horizontal=True, key="country_radio")
    country_choice = "すべて" if country_choice_display=="すべて" else {v:k for k,v in country_map.items()}.get(country_choice_display,country_choice_display)
    show_out = st.checkbox("取り寄せ商品を表示", key="show_out_of_stock")
    if "size_choice" not in st.session_state: st.session_state["size_choice"]="小瓶（≤500ml）"
    size_choice = st.radio("サイズ", ("すべて","小瓶（≤500ml）","大瓶（≥500ml）"), horizontal=True, key="size_choice")
    if "abv_slider" not in st.session_state: st.session_state["abv_slider"]=(0.0,20.0)
    abv_min, abv_max = st.slider("ABV（%）",0.0,20.0, step=0.5, key="abv_slider")
    if "price_slider" not in st.session_state: st.session_state["price_slider"]=(0,20000)
    price_min, price_max = st.slider("価格（円）",0,20000, step=100, key="price_slider")
    st.markdown("**スタイル（メイン）で絞り込み**")
    styles_available = sorted(df["style_main_jp"].replace("", pd.NA).dropna().unique(), key=locale_key)
    selected_styles=[]
    if styles_available:
        ncols = min(6,len(styles_available))
        style_cols = st.columns(ncols)
        for i,s in enumerate(styles_available):
            col=style_cols[i%ncols]
            state_key=f"style_{s}"
            checked=col.checkbox(s,key=state_key)
            if checked: selected_styles.append(s)

# ---------- Filtering ----------
# 「すべて表示」ボタン用フラグ
if "show_all" not in st.session_state:
    st.session_state["show_all"] = False

if st.button("🔎 すべて表示"):
    st.session_state["show_all"] = True

filtered = df_all.copy()

if st.session_state["show_all"]:
    # 全表示（フィルターなし）
    pass
else:
    # 検索がある場合だけ絞り込み
    if search_text and search_text.strip():
        kw = search_text.strip().lower()
        def matches_row(r):
            for c in ["name_local","name_jp","brewery_local","brewery_jp",
                      "style_main_jp","style_sub_jp","comment","detailed_comment",
                      "untappd_url","jan"]:
                if kw in safe_str(r.get(c,"")).lower():
                    return True
            return False
        filtered = filtered[filtered.apply(matches_row, axis=1)]
    else:
        # 検索前は空にする
        filtered = filtered.iloc[0:0]

    # サイズフィルタ
    if size_choice=="小瓶（≤500ml）":
        filtered = filtered[filtered["volume_num"].notna() & (filtered["volume_num"].astype(float)<=500.0)]
    elif size_choice=="大瓶（≥500ml）":
        filtered = filtered[filtered["volume_num"].notna() & (filtered["volume_num"].astype(float)>=500.0)]

    # ABVフィルタ
    filtered = filtered[
        (filtered["abv_num"].fillna(-1) >= float(abv_min)) & 
        (filtered["abv_num"].fillna(999) <= float(abv_max))
    ]

    # 価格フィルタ
    filtered = filtered[
        (filtered["price_num"].fillna(-1) >= int(price_min)) & 
        (filtered["price_num"].fillna(10**9) <= int(price_max))
    ]

    # スタイルフィルタ
    if selected_styles:
        filtered = filtered[filtered["style_main_jp"].isin(selected_styles)]

    # 国フィルタ
    if country_choice != "すべて":
        filtered = filtered[filtered["country"] == country_choice]

    # 在庫なしフィルタ
    if not st.session_state.get("show_out_of_stock", False):
        filtered = filtered[filtered["_in_stock_bool"] == True]


# ---------- Sorting ----------
if sort_option=="名前順": filtered=filtered.sort_values(by="yomi_sort",na_position="last")
elif sort_option=="ABV（低）": filtered=filtered.sort_values(by="abv_num",ascending=True,na_position="last")
elif sort_option=="ABV（高）": filtered=filtered.sort_values(by="abv_num",ascending=False,na_position="last")
elif sort_option=="価格（低）": filtered=filtered.sort_values(by="price_num",ascending=True,na_position="last")
elif sort_option=="醸造所順": filtered=filtered.sort_values(by="brewery_jp",key=lambda x:x.map(locale_key))
elif sort_option=="スタイル順": filtered=filtered.sort_values(by="style_main_jp",key=lambda x:x.map(locale_key))

st.markdown(f"**表示件数：{len(filtered)} 件**")

# ---------- Removed beers ----------
if "removed_ids" not in st.session_state: st.session_state["removed_ids"]=set()
def remove_beer(beer_id):
    beer_id_int=int(float(beer_id))
    st.session_state["removed_ids"].add(beer_id_int)

# ---------- Render Cards ----------
for brewery in filtered["brewery_jp"].unique():
    brewery_beers=filtered[filtered["brewery_jp"]==brewery]
    brewery_data=brewery_beers.iloc[0]
    for _,r in brewery_beers.iterrows():
        try: beer_id_safe=int(float(r["id"]))
        except: continue
        if beer_id_safe in st.session_state["removed_ids"]: continue
        col1,col2,col3,col4=st.columns([3,3,6,1], vertical_alignment="center")

        # 左
        with col1:
            st.image(r.get("brewery_image_url") or DEFAULT_BREWERY_IMG,width=100)
            st.markdown(f"<b>{r.get('brewery_local')}</b><br>{r.get('brewery_jp')}", unsafe_allow_html=True)
            brewery_city=safe_str(r.get('city'))
            brewery_country=safe_str(r.get('country'))
            flag_img=country_flag_url.get(brewery_country,"")
            if flag_img: st.markdown(f"{brewery_city}<br><img src='{flag_img}' width='20'> {brewery_country}", unsafe_allow_html=True)
            else: st.markdown(f"{brewery_city}<br>{brewery_country}", unsafe_allow_html=True)

        # 中央・右
        with col2:
            st.image(r.get("beer_image_url") or DEFAULT_BEER_IMG,width=100)
            st.markdown(f'<div style="text-align:center; margin-top:3px;"><a href="{r.get("untappd_url")}" target="_blank">Untappd</a></div>', unsafe_allow_html=True)
        with col3:
            st.markdown(f"<b>{r.get('name_local')}</b><br>{r.get('name_jp')}", unsafe_allow_html=True)
            style_line=" / ".join(filter(None,[r.get("style_main_jp"),r.get("style_sub_jp")]))
            st.markdown(style_line,unsafe_allow_html=True)
            info_arr=[]
            if pd.notna(r.get("abv_num")): info_arr.append(f"ABV {r.get('abv_num')}%")
            if pd.notna(r.get("volume_num")): info_arr.append(f"{int(r.get('volume_num'))}ml")
            vintage_val=r.get("vintage")
            if pd.notna(vintage_val) and str(vintage_val).strip()!="": info_arr.append(str(vintage_val).strip())
            if pd.notna(r.get("price_num")):
                if r.get("price_num")==0: info_arr.append("ASK")
                else: info_arr.append(f"¥{int(r.get('price_num'))}")
            st.markdown(" | ".join(info_arr),unsafe_allow_html=True)
            if r.get("comment"): st.markdown(r.get("comment"),unsafe_allow_html=True)
            if r.get("detailed_comment"): st.markdown(f"<details><summary>詳細コメント</summary>{r.get('detailed_comment')}</details>", unsafe_allow_html=True)

        # ❌ボタン
        with col4:
            button_key=f"remove_btn_{beer_id_safe}"
            if st.button("❌", key=button_key):
                remove_beer(beer_id_safe)
