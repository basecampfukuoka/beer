import streamlit as st

st.set_page_config(page_title="Reset Streamlit", layout="centered")

st.title("⚠ Streamlit リセットアプリ ⚠")
st.markdown("""
このアプリは以下をリセットします：
- Streamlit キャッシュ
- セッションステート
""")

if st.button("リセット実行 🔄"):
    # セッションステートを削除
    for key in list(st.session_state.keys()):
        del st.session_state[key]

    # キャッシュデータ・リソースをクリア
    try:
        st.cache_data.clear()
    except AttributeError:
        pass
    try:
        st.cache_resource.clear()
    except AttributeError:
        pass

    st.success("✅ キャッシュとセッションをリセットしました。ページを再読み込みしてください。")
