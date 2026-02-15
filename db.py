import streamlit as st
import requests
import os
import re
from urllib.parse import unquote
import zipfile
import io
from bs4 import BeautifulSoup

# === 匯入搜尋函式庫 ===
from ddgs import DDGS
import arxiv
from googlesearch import search as google_unofficial_search
from googleapiclient.discovery import build # Google Official
from serpapi import GoogleSearch # SerpApi

# === 設定頁面 ===
st.set_page_config(page_title="全能 PDF 搜尋神器 (自動全選版)", page_icon="🕵️", layout="wide")

# === 核心：通用工具與下載功能 ===
def get_headers():
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
    }

def get_filename_from_cd(cd):
    if not cd: return None
    fname = re.findall('filename=(.+)', cd)
    return fname[0].replace('"', '') if fname else None

def download_file(url, folder="downloads", progress_bar=None):
    """下載單一檔案，若提供 progress_bar 則顯示進度"""
    if not os.path.exists(folder): os.makedirs(folder)
    try:
        response = requests.get(url, stream=True, headers=get_headers(), timeout=20)
        response.raise_for_status()
        
        total_size = int(response.headers.get('content-length', 0))
        filename = get_filename_from_cd(response.headers.get('content-disposition'))
        if not filename: filename = unquote(url.split("/")[-1])
        filename = re.sub(r'[\\/*?:"<>|]', "", filename)
        if len(filename) > 50: filename = filename[:50]
        if not filename.lower().endswith('.pdf'): filename += ".pdf"
        
        file_path = os.path.join(folder, filename)
        
        downloaded = 0
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(8192):
                f.write(chunk)
                downloaded += len(chunk)
                if progress_bar and total_size > 0:
                    progress_bar.progress(min(downloaded/total_size, 1.0), text=f"下載中: {filename} ({int(downloaded/total_size*100)}%)")
        return True, file_path, None
    except Exception as e:
        return False, None, str(e)

# === 核心：特殊網站爬蟲策略 ===
def search_yabook(query, max_results):
    """利用搜尋引擎的 site: 語法來抓取雅書，結果更準確且完全不卡頓"""
    results = []
    try:
        # 我們直接利用免金鑰的 DDGS (DuckDuckGo) 來執行 site: 搜尋，這與 Google site: 效果極度相似
        search_query = f"site:yabook.org {query}"
        
        for r in DDGS().text(search_query, max_results=max_results):
            # 稍微清理一下標題，把搜尋引擎帶入的網站後綴拿掉，讓畫面更乾淨
            title = r.get('title', '')
            title = title.replace(' - 雅书', '').replace(' | 雅书', '').replace(' - 雅書', '')
            
            results.append({
                "title": title[:60] + "..." if len(title) > 60 else title, 
                "link": r.get('href'), 
                "source": "雅書 (Yabook)", 
                "type": "webpage" # 依然標記為網頁，在右下區塊顯示超連結
            })
    except Exception as e: 
        st.error(f"雅書 (Yabook) 搜尋錯誤: {e}")
    return results

def search_oceanofpdf(query, max_results):
    results = []
    base_url = "https://oceanofpdf.com/"
    search_url = f"{base_url}?s={query.replace(' ', '+')}"
    try:
        response = requests.get(search_url, headers=get_headers(), timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            for i, article in enumerate(soup.find_all('article')):
                if i >= max_results: break
                title_tag = article.find('h2', class_='title')
                if title_tag and title_tag.find('a'):
                    results.append({"title": title_tag.get_text(strip=True), "link": title_tag.find('a')['href'], "source": "OceanofPDF", "type": "webpage"})
    except Exception as e: st.error(f"OceanofPDF 錯誤: {e}")
    return results

def search_annas_archive(query, max_results):
    results = []
    base_url = "https://annas-archive.li"
    search_url = f"{base_url}/search?q={query.replace(' ', '+')}"
    try:
        response = requests.get(search_url, headers=get_headers(), timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            count = 0
            for link in soup.find_all('a', href=True):
                if '/md5/' in link['href']:
                    title = link.get_text(strip=True)
                    if len(title) > 5:
                        full_link = base_url + link['href'] if link['href'].startswith('/') else link['href']
                        results.append({"title": title[:60] + "...", "link": full_link, "source": "Anna's Archive", "type": "webpage"})
                        count += 1
                        if count >= max_results: break
    except Exception as e: st.error(f"Anna's Archive 錯誤: {e}")
    return results

# === 核心：API 搜尋策略 ===
def search_duckduckgo(query, max_results):
    results = []
    try:
        for r in DDGS().text(f"{query} filetype:pdf", max_results=max_results):
            results.append({"title": r.get('title'), "link": r.get('href'), "source": "DuckDuckGo", "type": "pdf"})
    except Exception as e: st.error(f"DuckDuckGo 錯誤: {e}")
    return results

def search_arxiv_lib(query, max_results):
    results = []
    try:
        search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.Relevance)
        for r in arxiv.Client().results(search):
            results.append({"title": f"[論文] {r.title}", "link": r.pdf_url, "source": "arXiv", "type": "pdf"})
    except Exception as e: st.error(f"arXiv 錯誤: {e}")
    return results

def search_google_unofficial(query, max_results):
    results = []
    try:
        for r in google_unofficial_search(f"{query} filetype:pdf", num=max_results, advanced=True):
            results.append({"title": r.title, "link": r.url, "source": "Google (Unofficial)", "type": "pdf"})
    except Exception as e: st.error(f"Google (非官方) 錯誤: {e}")
    return results

def search_google_official(query, api_key, cse_id, max_results):
    results = []
    try:
        res = build("customsearch", "v1", developerKey=api_key).cse().list(q=query, cx=cse_id, fileType='pdf', num=max_results).execute()
        for item in res.get('items', []):
            results.append({"title": item['title'], "link": item['link'], "source": "Google API", "type": "pdf"})
    except Exception as e: st.error(f"Google API 錯誤: {e}")
    return results

def search_serpapi(query, api_key, max_results):
    results = []
    try:
        data = GoogleSearch({"engine": "google", "q": f"{query} filetype:pdf", "api_key": api_key, "num": max_results}).get_dict()
        for item in data.get("organic_results", []):
            results.append({"title": item.get('title'), "link": item.get('link'), "source": "SerpApi", "type": "pdf"})
    except Exception as e: st.error(f"SerpApi 錯誤: {e}")
    return results

# === 主介面邏輯 ===
def main():
    # --- 左側邊欄：搜尋設定 ---
    st.sidebar.title("⚙️ 搜尋設定")
    st.sidebar.markdown("**選擇搜尋引擎 (預設全選)**")
    
    engine_options = [
        "DuckDuckGo (推薦/免金鑰)", 
        "arXiv (學術論文/免金鑰)", 
        "OceanofPDF (網頁/免金鑰)",
        "Anna's Archive (網頁/免金鑰)",
        "雅書 Yabook (網頁/免金鑰)",
        "Google (非官方/易被擋)", 
        "Google Official API (需金鑰)", 
        "SerpApi (需金鑰)"
    ]
    
    selected_engines = []
    # 使用迴圈產生 Checkbox，並且 value=True 讓它內定打勾
    for engine in engine_options:
        if st.sidebar.checkbox(engine, value=True):
            selected_engines.append(engine)
    
    api_key, cse_id, serp_key = "", "", ""
    engine_str = "".join(selected_engines) 
    
    if "Google Official API" in engine_str:
        st.sidebar.warning("已啟用 Google API，請輸入金鑰：")
        api_key = st.sidebar.text_input("Google API Key", type="password")
        cse_id = st.sidebar.text_input("Search Engine ID (CSE ID)", type="password")
        
    if "SerpApi" in engine_str:
        st.sidebar.warning("已啟用 SerpApi，請輸入金鑰：")
        serp_key = st.sidebar.text_input("SerpApi Key", type="password")

    # --- 右側主畫面 ---
    st.title("🕵️ 全能 PDF 搜尋神器 (自動全選批次版)")
    st.markdown("---")

    col1, col2 = st.columns([4, 1])
    with col1:
        query = st.text_input("輸入關鍵字 (書名/論文名)", placeholder="例如: 原子習慣")
    with col2:
        st.write(""); st.write("")
        start_search = st.button("🔍 開始搜尋", type="primary", use_container_width=True)

    if start_search and query:
        st.session_state.results = [] 
        max_res = 5
        
        for engine in selected_engines:
            with st.spinner(f"正在使用 {engine.split(' ')[0]} 搜尋..."):
                if "DuckDuckGo" in engine:
                    st.session_state.results.extend(search_duckduckgo(query, max_res))
                elif "arXiv" in engine:
                    st.session_state.results.extend(search_arxiv_lib(query, max_res))
                elif "OceanofPDF" in engine:
                    st.session_state.results.extend(search_oceanofpdf(query, max_res))
                elif "Anna's Archive" in engine:
                    st.session_state.results.extend(search_annas_archive(query, max_res))
                elif "雅書 Yabook" in engine:
                    st.session_state.results.extend(search_yabook(query, max_res))
                elif "Google (非官方)" in engine:
                    st.session_state.results.extend(search_google_unofficial(query, max_res))
                elif "Google Official API" in engine and api_key and cse_id:
                    st.session_state.results.extend(search_google_official(query, api_key, cse_id, max_res))
                elif "SerpApi" in engine and serp_key:
                    st.session_state.results.extend(search_serpapi(query, serp_key, max_res))

    # === 搜尋結果顯示 ===
    if 'results' in st.session_state and st.session_state.results:
        st.success(f"🎉 總共找到 {len(st.session_state.results)} 個相關結果！")
        st.markdown("---")
        
        # 將結果分為 PDF 和 Webpage 兩類
        pdf_items = [item for item in st.session_state.results if item['type'] == 'pdf']
        web_items = [item for item in st.session_state.results if item['type'] == 'webpage']
        
        col_pdf, col_web = st.columns([1, 1])
        
        # ==========================================
        # 左欄 / 上半部：直連 PDF 勾選下載區
        # ==========================================
        if pdf_items:
            st.subheader("📄 直連 PDF 檔案 (可批次打包)")
            st.write("已為您**預設全選**，請取消不想下載的項目：")
            
            selected_pdfs_to_download = []
            
            # 使用獨立的 Checkbox 列出 PDF
            for i, item in enumerate(pdf_items):
                is_checked = st.checkbox(
                    f"[{item['source']}] {item['title']}", 
                    value=True, # 內定勾選
                    key=f"pdf_chk_{i}"
                )
                if is_checked:
                    selected_pdfs_to_download.append(item)
            
            # 下載與打包邏輯
            if selected_pdfs_to_download:
                st.write("")
                if st.button("⬇️ 開始下載並打包為 ZIP 壓縮檔", type="primary"):
                    progress_bar = st.progress(0, text="準備下載...")
                    zip_buffer = io.BytesIO()
                    success_count = 0
                    
                    with zipfile.ZipFile(zip_buffer, "w") as zip_file:
                        for idx, item in enumerate(selected_pdfs_to_download):
                            progress_bar.progress(idx / len(selected_pdfs_to_download), text=f"處理中 ({idx+1}/{len(selected_pdfs_to_download)}): {item['title'][:20]}...")
                            success, path, error = download_file(item['link'], progress_bar=progress_bar)
                            
                            if success:
                                zip_file.write(path, os.path.basename(path))
                                success_count += 1
                            else:
                                st.error(f"❌ 下載失敗: {item['title']} (原因: {error})")
                                
                    progress_bar.progress(1.0, text="處理完成！")
                    
                    if success_count > 0:
                        st.success(f"✅ 成功打包 {success_count} 個檔案！請點擊下方按鈕儲存。")
                        st.download_button(
                            label="💾 儲存 ZIP 檔案至電腦",
                            data=zip_buffer.getvalue(),
                            file_name="PDF_Downloads.zip",
                            mime="application/zip"
                        )
                    else:
                        st.error("所有勾選的檔案均下載失敗。")

        # ==========================================
        # 區分線或右欄：網頁連結顯示區
        # ==========================================
        if web_items:
            st.markdown("---")
            st.subheader("🌐 相關網頁資源 (需手動前往)")
            st.warning("⚠️ **以下項目需點擊連結前往該網站進行手動下載或瀏覽：**")
            
            # 直接條列資訊與超連結，不使用 Checkbox
            for item in web_items:
                with st.container(border=True):
                    st.markdown(f"**來源：** `{item['source']}`")
                    st.markdown(f"**標題：** {item['title']}")
                    st.markdown(f"🔗 **[點我前往下載頁面]({item['link']})**")

if __name__ == "__main__":
    main()
