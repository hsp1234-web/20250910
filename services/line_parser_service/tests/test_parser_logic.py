# services/essay_ingestion_service/tests/test_parser_logic.py
import pytest
from services.essay_ingestion_service.logic import parse_chat_log

# 使用者提供的真實聊天紀錄作為測試案例
COMPLEX_CHAT_LOG = """
0488695 三寶	小作文-2424隴華
https://docs.google.com/document/d/10nDGa7nWuSZCLhU9qtR_VW8Cx-yQllk5/edit?usp=drive_link&ouid=105443695704290227678&rtpof=true&sd=true
13:19	421-0299033青蛙狼	https://docs.google.com/document/d/1-OeWOZfZ8-KQb2-S-QhfthC7k-UPb4KofyzmLiGT17Y/edit
14:08	506-0723994 樂觀感恩加入聊天
14:08	503-0551726千千加入聊天
14:09	503-0551726千千	四月小作文-日月光投控 3711
https://drive.google.com/file/d/1ADg9NnB10z3qjnSZPOn6BLh_Fz8wjY9T/view?usp=sharing
14:14	506-0723994 樂觀感恩	四月小作文-TIPT
https://docs.google.com/document/d/1W2vOOJBLSdoRWxmjh7x3S5nyYvW1YaUenZxGpB28hSA/edit?usp=sharing
14:50	381-0491048彼得森	小作文-3434哲固
https://docs.google.com/document/d/1J4ZO4YkbQefHXUjjqTz0tp47bSOqTX_6MsWsf4tHHKk/edit?tab=t.0
15:13	440-0208121 voice已收回訊息
15:17	440-0208121 空格voice	3月小作文-2383台光電
https://docs.google.com/document/d/1XdqN_JI8so3cJYskXKZGqKhhw3XTb7nu/edit?usp=sharing&ouid=112140481029709627573&rtpof=true&sd=true
19:12	414-0505439JCCC	三月份小作文-大成鋼-2027
https://www.dropbox.com/scl/fi/ji8p822xcgvi3efq9l2r3/2027-JCCC.docx?rlkey=djtg9ba6hoae8yoz36332lybw&st=g5v3akab&dl=0
21:41	434-0547510菲獅	四月小作文-聯發科2454
https://docs.google.com/document/d/1cZkdPLu1swM61r2CEHZpRzsnp9NaoYy6LvIvcxODvOw/edit?tab=t.0
23:16	441-0558088田橋子	https://docs.google.com/document/d/10lCS49RS2wA1AfZF6qnF7cpavj_NzrfEAMpzOH1gin8/edit
23:40	428-0429751貝卡	3月小作文- 鴻海(2317)
https://docs.google.com/document/d/1AhIMeRaLiTVQccemmE-_WbcNTdRsIU5nzWoXqZ5T3Gg/edit?usp=sharing

2025/4/6（週日）
00:19	477-0696872過兒已收回訊息
00:19	477-0696872過兒已收回訊息
00:22	477-0696872過兒	 四月小作文，龍巖
https://docs.google.com/document/d/10jVsypGJL9wTxitWNs-jPjcvOerC8G-sw_4ouflfUOo/edit?usp=sharing
15:08	459-0677503登大狼小海龜拔拔	這隻我也有持有 優點銷售地點 台灣跟中國 約各佔一半或許短期不受關稅問題影響  感謝分享
15:12	441-0558088田橋子	謝謝賞臉
"""

# (Jules @ 2025-10-09) 更新後的「黃金標準」，以匹配 v2 解析器的輸出
EXPECTED_RESULTS = [
    # 第一筆資料沒有日期，但有作者和標題
    {'date': None, 'time': None, 'author': '0488695 三寶', 'title': '小作文-2424隴華', 'url': 'https://docs.google.com/document/d/10nDGa7nWuSZCLhU9qtR_VW8Cx-yQllk5/edit?usp=drive_link&ouid=105443695704290227678&rtpof=true&sd=true'},
    # 第二筆，無標題
    {'date': None, 'time': '13:19', 'author': '421-0299033青蛙狼', 'title': '無標題', 'url': 'https://docs.google.com/document/d/1-OeWOZfZ8-KQb2-S-QhfthC7k-UPb4KofyzmLiGT17Y/edit'},
    # 標題與網址分離
    {'date': None, 'time': '14:09', 'author': '503-0551726千千', 'title': '四月小作文-日月光投控 3711', 'url': 'https://drive.google.com/file/d/1ADg9NnB10z3qjnSZPOn6BLh_Fz8wjY9T/view?usp=sharing'},
    # 標題與網址分離
    {'date': None, 'time': '14:14', 'author': '506-0723994 樂觀感恩', 'title': '四月小作文-TIPT', 'url': 'https://docs.google.com/document/d/1W2vOOJBLSdoRWxmjh7x3S5nyYvW1YaUenZxGpB28hSA/edit?usp=sharing'},
    # 標題與網址分離
    {'date': None, 'time': '14:50', 'author': '381-0491048彼得森', 'title': '小作文-3434哲固', 'url': 'https://docs.google.com/document/d/1J4ZO4YkbQefHXUjjqTz0tp47bSOqTX_6MsWsf4tHHKk/edit?tab=t.0'},
    # 標題與網址分離，且作者名有空格
    {'date': None, 'time': '15:17', 'author': '440-0208121 空格voice', 'title': '3月小作文-2383台光電', 'url': 'https://docs.google.com/document/d/1XdqN_JI8so3cJYskXKZGqKhhw3XTb7nu/edit?usp=sharing&ouid=112140481029709627573&rtpof=true&sd=true'},
    # 標題與網址分離
    {'date': None, 'time': '19:12', 'author': '414-0505439JCCC', 'title': '三月份小作文-大成鋼-2027', 'url': 'https://www.dropbox.com/scl/fi/ji8p822xcgvi3efq9l2r3/2027-JCCC.docx?rlkey=djtg9ba6hoae8yoz36332lybw&st=g5v3akab&dl=0'},
    # 標題與網址分離
    {'date': None, 'time': '21:41', 'author': '434-0547510菲獅', 'title': '四月小作文-聯發科2454', 'url': 'https://docs.google.com/document/d/1cZkdPLu1swM61r2CEHZpRzsnp9NaoYy6LvIvcxODvOw/edit?tab=t.0'},
    # 無標題
    {'date': None, 'time': '23:16', 'author': '441-0558088田橋子', 'title': '無標題', 'url': 'https://docs.google.com/document/d/10lCS49RS2wA1AfZF6qnF7cpavj_NzrfEAMpzOH1gin8/edit'},
    # 標題與網址分離
    {'date': None, 'time': '23:40', 'author': '428-0429751貝卡', 'title': '3月小作文- 鴻海(2317)', 'url': 'https://docs.google.com/document/d/1AhIMeRaLiTVQccemmE-_WbcNTdRsIU5nzWoXqZ5T3Gg/edit?usp=sharing'},
    # 新日期後的的第一筆
    {'date': '2025-04-06', 'time': '00:22', 'author': '477-0696872過兒', 'title': '四月小作文，龍巖', 'url': 'https://docs.google.com/document/d/10jVsypGJL9wTxitWNs-jPjcvOerC8G-sw_4ouflfUOo/edit?usp=sharing'},
]

def test_parse_chat_log_with_real_data():
    """
    使用真實、複雜的聊天紀錄來驗證增強後的解析器。
    這個測試是我們驗收新邏輯的黃金標準。
    """
    # 執行解析
    actual_results = parse_chat_log(COMPLEX_CHAT_LOG)

    # 為了方便偵錯，如果測試失敗，就印出兩個列表的詳細內容
    assert len(actual_results) == len(EXPECTED_RESULTS), \
        f"數量不符！預期得到 {len(EXPECTED_RESULTS)} 筆資料，但實際解析出 {len(actual_results)} 筆。\n" \
        f"預期結果: {EXPECTED_RESULTS}\n" \
        f"實際結果: {actual_results}"

    # 為了方便比較，我們不關心順序，只關心內容
    # 將結果列表轉換為元組的集合，這樣可以忽略順序進行比較
    actual_set = {tuple(sorted(d.items())) for d in actual_results}
    expected_set = {tuple(sorted(d.items())) for d in EXPECTED_RESULTS}

    # 斷言實際結果與預期結果完全相符
    assert actual_set == expected_set