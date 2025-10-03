# tests/test_url_extractor.py
import sys
from pathlib import Path
import pytest

# --- 路徑修正，確保可以從 src 導入 ---
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from tools.url_extractor import parse_chat_log

# --- 測試資料 ---

# 這是使用者最初提供，可以被舊版解析器正確處理的資料
GOOD_INPUT_TEXT = """
股-氣立4555
https://drive.google.com/file/d/1sOQ659or7hLThbTmzNSnTwJcEsuaPick/view?usp=sharing
19:12	758-0841368庄咖郎涼水已收回訊息
19:17	758-0841368庄咖郎涼水	九月小作文
台股-玉晶光3406
https://docs.google.com/document/d/1-4QuetVB0zdzz8Or-IaR3XaVz984es7a65yVQ_B4yjw/mobilebasic
19:25	745-0830450更生狼	9月小作文2
台股-嘉澤 3533
https://docs.google.com/document/d/1_ys3F0OrN8mlfrROuvIFi0PDGHaiaut0/edit?usp=sharing&ouid=112274389475901734491&rtpof=true&sd=true
"""

# 這是使用者最初提供，但無法被舊版解析器處理的資料。
# 修改後的解析器應該要能處理這些格式。
BAD_INPUT_TEXT_NOW_SHOULD_WORK = """
le.com/document/d/14tDAP1fIB3VCnzfpEBc9YxOWd82P6KQf/edit?usp=sharing&ouid=118071323241450088018&rtpof=true&sd=true
2025.09.21 星期日
10:33 626-9800005rich 九月小作文
台股-智通* 8932
https://docs.google.com/document/d/1iG_dRmrcDJFsZlOLAkf8bD3rKw836lVn/edit?usp=drive_link&ouid=116363410657624684517&rtpof=true&sd=true
11:48 578-0742519GRACE 9月小作文
HVDC架構帶動功率元件升級趨勢分析報告

https://docs.google.com/document/d/17Ar2tbGvq8YqH7Vn8fkTa-53WlZl5cen/edit?usp=sharing&ouid=108449927033091815004&rtpof=true&sd=true
14:53 041-0397236拖泥帶水 更新ALAB資訊

事件：NVDA 入股 INTC
影響部分PCIe、但Scorpio 6 scale-up預期不受影響
市場反應：下殺7%收下引線+爆量→推測已反應PCIe影響+部分資近仍看好scale-up題材
結論：估值仍給予 $ 265 ($226~303)

https://docs.google.com/document/d/11cCt6IjE8dUPwZ0gNYIb2fSzzpdweygzMXH3nrSQJm4/edit?usp=sharing
"""

# --- 測試案例 ---

@pytest.fixture
def good_text_with_date():
    """提供一個帶有日期的良好格式文字區塊。"""
    return "2025/09/20（週六）\n" + GOOD_INPUT_TEXT

@pytest.fixture
def bad_text_that_should_now_work():
    """提供一個之前格式錯誤，但現在應該可以被處理的文字區塊。"""
    return BAD_INPUT_TEXT_NOW_SHOULD_WORK

def test_parse_with_original_good_format(good_text_with_date):
    """
    測試案例1：驗證解析器仍然可以正確處理原始的、格式良好的輸入。
    這確保了我們的修改沒有破壞原有的功能（回歸測試）。
    """
    results = parse_chat_log(good_text_with_date)

    # 原始的良好輸入應該能解析出 2 筆資料
    # ('股-氣立4555' 那筆沒有時間和作者，所以會被忽略)
    assert len(results) == 2, "對於原始的良好格式，應能解析出 2 筆有效的資料"

    # 檢查第一筆資料的內容是否正確
    assert results[0]['date'] == '2025-09-20'
    assert results[0]['time'] == '19:17'
    assert results[0]['author'] == '758-0841368庄咖郎涼水'
    assert '台股-玉晶光3406' in results[0]['title']
    assert results[0]['url'].startswith('https://docs.google.com')

def test_parse_with_previously_bad_format(bad_text_that_should_now_work):
    """
    測試案例2：驗證我們修改後的解析器，現在可以正確處理之前無法處理的格式。
    這是本次修改的核心驗證。
    """
    results = parse_chat_log(bad_text_that_should_now_work)

    # 這個之前無法處理的區塊，現在應該能解析出 3 筆資料
    assert len(results) == 3, "對於之前格式錯誤的輸入，現在應能解析出 3 筆有效的資料"

    # 驗證第一筆資料 (使用 YYYY.MM.DD 日期格式和空格分隔符)
    assert results[0]['date'] == '2025-09-21'
    assert results[0]['time'] == '10:33'
    assert results[0]['author'] == '626-9800005rich'
    assert '台股-智通* 8932' in results[0]['title']
    assert results[0]['url'].startswith('https://docs.google.com')

    # 驗證第二筆資料 (多行標題)
    assert results[1]['date'] == '2025-09-21'
    assert results[1]['time'] == '11:48'
    assert results[1]['author'] == '578-0742519GRACE'
    assert 'HVDC架構帶動功率元件升級趨勢分析報告' in results[1]['title']
    assert results[1]['url'].startswith('https://docs.google.com')

    # 驗證第三筆資料 (包含大量文字的複雜多行標題)
    assert results[2]['date'] == '2025-09-21'
    assert results[2]['time'] == '14:53'
    assert results[2]['author'] == '041-0397236拖泥帶水'
    assert '更新ALAB資訊' in results[2]['title']
    assert '結論：估值仍給予 $ 265' in results[2]['title']
    assert results[2]['url'].startswith('https://docs.google.com')

def test_empty_input():
    """測試案例3：提供空字串時，應回傳空列表。"""
    assert parse_chat_log("") == []

def test_no_valid_entries():
    """測試案例4：提供沒有有效項目的文字時，應回傳空列表。"""
    text = """
    這是一些沒有用的文字
    2025/01/01（週三）
    沒有時間戳的行
    也沒有網址
    """
    assert parse_chat_log(text) == []