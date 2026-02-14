import streamlit as st
from duckduckgo_search import DDGS
import requests
import os
import re
from urllib.parse import unquote

# 設定頁面配置
st.set_page_config(page_title="PDF 搜尋與下載器", page_icon="📚", layout="centered")

# === 核心功能函式 ===

def search_pdfs(query, max_results=8):
    """
    使用 DuckDuckGo 搜尋 PDF 檔案。
    """
    results = []
    try:
        # filetype:pdf 強制搜尋 PDF，並限制地區以獲得較佳連線
        search_query = f"{query} filetype:pdf"
        
        # 初始化 DDGS
        with DDGS() as ddgs:
            # 獲取搜尋結果
            ddgs_gen = ddgs.text(search_query, max_results=max_results)
            
            for r in ddgs_gen:
                results.append({
                    "title": r.get('title', '未命名文件'),
                    "link": r.get('href', ''),
                    "snippet": r.get('body', '')
                })
    except Exception as e:
        st.error(f"搜尋時發生錯誤: {e}")
    
    return results

def get_filename_from_cd(cd):
    """
    從 Content-Disposition 標頭獲取檔名
    """
    if not cd:
        return None
    fname = re.findall('filename=(.+)', cd)
    if len(fname) == 0:
        return None
    return fname[0].replace('"', '')

def download_file_with_progress(url, download_folder="downloads"):
    """
    下載檔案並顯示進度條。
    回傳: (success: bool, file_path: str, error_msg: str)
    """
    if not os.path.exists(download_folder):
        os.makedirs(download_folder)

    try:
        # 偽裝 User-Agent
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # 使用 stream=True 進行串流下載
        response = requests.get(url, stream=True, headers=headers, timeout=15)
        response.raise_for_status() # 檢查請求是否成功

        # 嘗試取得檔案大小
        total_size = int(response.headers.get('content-length', 0))
        
        # 嘗試從 URL 或 Header 解析檔名
        filename = get_filename_from_cd(response.headers.get('content-disposition'))
        if not filename:
            filename = unquote(url.split("/")[-1])
        
        # 清理檔名，避免非法字元
        filename = re.sub(r'[\\/*?:"<>|]', "", filename)
        if not filename.lower().endswith('.pdf'):
            filename += ".pdf"
            
        file_path = os.path.join(download_folder, filename)

        # 寫入檔案並更新 UI
        progress_bar = st.progress(0, text="準備下載...")
        block_size = 8192 # 8KB chunk
        downloaded_size = 0
        
        with open(file_path, 'wb') as file:
            for data in response.iter_content(block_size):
                file.write(data)
                downloaded_size += len(data)
                if total_size > 0:
                    percent = min(downloaded_size / total_size, 1.0)
                    progress_bar.progress(percent, text=f"下載中: {int(percent*100)}%")
                else:
                    # 如果伺服器沒給檔案大小，顯示已下載量
                    progress_bar.progress(0.5, text=f"下載中 (已下載 {downloaded_size/1024:.0f} KB)...")
        
        progress_bar.progress(1.0, text="下載完成！")
        return True, file_path, None

    except Exception as e:
        return False, None, str(e)

# === 使用者介面 (UI) ===

def main():
    st.title("📚 書籍/論文 PDF 搜尋器")
    st.markdown("---")
    
    # 法律免責聲明
    st.info("⚠️ **免責聲明**：本工具僅供搜尋公開資源（如學術論文、公開報告、公版書）。請尊重版權，勿下載受版權保護的書籍。")

    # 初始化 Session State
    if 'search_results' not in st.session_state:
        st.session_state.search_results = []
    
    # 輸入區
    col1, col2 = st.columns([4, 1])
    with col1:
        query = st.text_input("請輸入書名或關鍵字", placeholder="例如: Python Programming, Deep Learning Paper...")
    with col2:
        st.write("") 
        st.write("") 
        search_btn = st.button("🔍 開始搜尋", type="primary")

    # 處理搜尋邏輯
    if search_btn and query:
        with st.spinner(f"正在網路上搜尋 '{query}' 的 PDF 資源..."):
            st.session_state.search_results = search_pdfs(query)
            if not st.session_state.search_results:
                st.warning("找不到相關結果，請嘗試更換關鍵字。")

    # 顯示結果列表
    if st.session_state.search_results:
        st.subheader("搜尋結果")
        st.markdown(f"找到 {len(st.session_state.search_results)} 個相關連結：")
        
        # 建立選項列表 (Title + Link 預覽)
        options = {f"{i+1}. {item['title']}": item for i, item in enumerate(st.session_state.search_results)}
        selected_option_key = st.radio("請選擇要下載的檔案：", list(options.keys()))
        
        if selected_option_key:
            selected_item = options[selected_option_key]
            st.markdown(f"**來源連結:** `{selected_item['link']}`")
            st.markdown(f"**摘要:** {selected_item['snippet'][:100]}...")
            
            # 下載按鈕與邏輯
            if st.button("⬇️ 確認並下載選取的檔案"):
                with st.status("正在建立連線...", expanded=True) as status:
                    st.write("正在請求檔案...")
                    success, file_path, error = download_file_with_progress(selected_item['link'])
                    
                    if success:
                        status.update(label="下載成功！", state="complete", expanded=False)
                        file_name = os.path.basename(file_path)
                        
                        # 讀取檔案以供 Streamlit 下載按鈕使用
                        with open(file_path, "rb") as f:
                            file_bytes = f.read()
                            
                        st.success(f"檔案 `{file_name}` 已成功下載到伺服器。")
                        st.download_button(
                            label="💾 儲存到我的電腦",
                            data=file_bytes,
                            file_name=file_name,
                            mime="application/pdf"
                        )
                    else:
                        status.update(label="下載失敗", state="error")
                        st.error(f"無法下載檔案。原因：{error}")
                        st.caption("可能原因：連結已失效、網站有防爬蟲機制、或檔案非公開。")

if __name__ == "__main__":
    main()
