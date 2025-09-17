import pytest
import sys
from pathlib import Path

# --- 路徑修正，確保可以匯入 src 中的模組 ---
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC_DIR))

from tools.url_extractor import parse_chat_log

# 使用者提供的最新、最完整的聊天記錄，用於測試
FULL_CHAT_LOG = """
2025/6/28（週六）
21:47	577-0741727Silence張震	六月小作文-勤誠8210
https://walnut-planarian-4a2.notion.site/2025-06-29-2147d11db04c803791ebce733166f36d?source=copy_link
23:29	528-0434571荒唐信	六月小作文   7月下旬小那放空規劃

https://docs.google.com/document/d/1yaTv0GXQpAnkg1vbKrxi9apaoMfR4l-Lh9TSPyq9zkE/edit?usp=sharing
23:35	539-0727848威少已收回訊息
23:44	539-0727848威少	6月小作文 藥華藥
https://docs.google.com/document/d/1CMw4ANwoIGifeBjh037t3fTGybJv-aqc/edit?usp=drive_link&ouid=106402131487664706236&rtpof=true&sd=true

2025/6/30（週一）
00:07	592-0395380YH	六月小作文 保瑞
https://docs.google.com/document/d/1kOFJ0SS-XGfEiNzRPYLglAwl6EZyqahuE7M1ISAOihY/edit?usp=sharing
08:07	454-0454292RS	5209 新鼎
https://docs.google.com/document/d/1TdoPVBPpTZk0IlWUutKo7rdBMQbvYFip/edit?usp=sharing&ouid=118141708314069713984&rtpof=true&sd=true
08:42	127-0398125 Gerald	(loud volume)《經濟學人》當期有聲書
https://bit.ly/3xt99aD
09:57	530-0728960Harris	七月份小作文: 艾榭克2025年中間筆記分享

https://www.notion.so/2025H2-222ea376be388026b134e346cbaff48d?source=copy_link
14:30	590-0747255JEROME	https://docs.google.com/document/d/1Uh5OswmbgHUaS0Y-A8kRShQvsGAO7Bt1?rtpof=true&usp=drive_fs
23:53	587-0736295寫程式的工程師	6月小作文：凱鈿行動科技 (TPEx: 7737) 投資研究報告：AI驅動SaaS領域的成長與挑戰 (本研究報告產自AI的研究)

同樣為軟體業的工程師，最近有接觸到他們的產品，覺得以基本面角度有一定的成長性

https://docs.google.com/document/d/1i5ZYxkpgARnbfdcLsDYYQWIuC_eSAeOrrGiPLCVnRls/edit?tab=t.0
21:57	579-0740320Jack	6月小作文-2368 金像電

https://docs.google.com/document/d/1dg-XRQplih5nPTCc6hl-Giq7NbPo9INJ/edit?usp=sharing&ouid=118019031832096772647&rtpof=true&sd=true
"""

def test_chat_log_parsing():
    """
    對 `parse_chat_log` 函數進行完整的端到端測試，使用真實的、複雜的聊天記錄。
    """
    results = parse_chat_log(FULL_CHAT_LOG)

    # 1. 驗證總數是否正確 (排除無效訊息後)
    # 根據提供的日誌，應該有 10 個有效的貼文 (之前誤算為11)
    assert len(results) == 10, f"預期解析出 10 筆資料，但實際得到 {len(results)} 筆"

    # 2. 抽樣驗證幾個關鍵案例

    # 案例一：標準案例 (results[0])
    assert results[0]['date'] == '2025-06-28'
    assert results[0]['author'] == '577-0741727Silence張震'
    assert results[0]['title'] == '六月小作文-勤誠8210'
    assert results[0]['url'].startswith('https://walnut-planarian-4a2.notion.site')

    # 案例二：包含空行 (results[1])
    assert results[1]['date'] == '2025-06-28'
    assert results[1]['author'] == '528-0434571荒唐信'
    assert results[1]['title'] == '六月小作文 7月下旬小那放空規劃' # 驗證多個空白符被正規化為一個
    assert results[1]['url'].startswith('https://docs.google.com/document/d/1yaTv0GXQpAnkg1vbKrxi9apaoMfR4l-Lh9TSPyq9zkE')

    # 案例三：標題在不同行 (results[4])
    assert results[4]['date'] == '2025-06-30'
    assert results[4]['author'] == '454-0454292RS'
    assert results[4]['title'] == '5209 新鼎'
    assert results[4]['url'].startswith('https://docs.google.com/document/d/1TdoPVBPpTZk0IlWUutKo7rdBMQbvYFip')

    # 案例四：只有 URL，無標題 (results[7])
    assert results[7]['date'] == '2025-06-30'
    assert results[7]['author'] == '590-0747255JEROME'
    assert results[7]['title'] == '無標題' # 驗證預設標題
    assert results[7]['url'].startswith('https://docs.google.com/document/d/1Uh5OswmbgHUaS0Y-A8kRShQvsGAO7Bt1')

    # 案例五：最複雜的案例，多行文字和空行 (results[8])
    assert results[8]['date'] == '2025-06-30'
    assert results[8]['author'] == '587-0736295寫程式的工程師'
    expected_title = '6月小作文：凱鈿行動科技 (TPEx: 7737) 投資研究報告：AI驅動SaaS領域的成長與挑戰 (本研究報告產自AI的研究) 同樣為軟體業的工程師，最近有接觸到他們的產品，覺得以基本面角度有一定的成長性'
    assert results[8]['title'] == expected_title
    assert results[8]['url'].startswith('https://docs.google.com/document/d/1i5ZYxkpgARnbfdcLsDYYQWIuC_eSAeOrrGiPLCVnRls')

    # 案例六：標題和網址在同一行，但中間有空行 (results[9])
    assert results[9]['date'] == '2025-06-30'
    assert results[9]['author'] == '579-0740320Jack'
    assert results[9]['title'] == '6月小作文-2368 金像電'
    assert results[9]['url'].startswith('https://docs.google.com/document/d/1dg-XRQplih5nPTCc6hl-Giq7NbPo9INJ')
