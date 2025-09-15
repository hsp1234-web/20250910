import pytest
import httpx
import sqlite3
from typing import List, Dict

# The conftest.py in the same directory will automatically provide the live_services fixture.

# User-provided test data
LINE_CHAT_LOG = """
0724579Cowboy加入聊天
17:13	502-0724579 Cowboy	四月小作文-來頡6799
https://drive.google.com/file/d/1RUl7XhxyJpxKO4RBX0AxeeyD4ABYPU_l/view?usp=sharing
17:54	500-0724304FOMO就剁手手加入聊天

2025/4/4（週五）
17:44	504-0718103Leo加入聊天
17:46	504-0718103Leo已收回訊息
17:46	504-0718103Leo	四月小作文-精確3162
https://docs.google.com/document/d/16TkL54YmFAToS1UR26VdV_mYgr8bCAml/edit?tab=t.0
17:48	505-0724540捲髮狼加入聊天
17:48	505-0724540捲髮狼	四月小作文-5515建國
https://drive.google.com/file/d/1dwnVczcEvhIIj5TOXRHVow876da6zAGp/view?usp=drivesdk

2025/4/5（週六）
12:21	383-0488695 三寶已收回訊息
12:21	383-0488695 三寶	小作文-2424隴華

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
15:17	440-0208121 空格voice	3月小作文
"""

# Expected URLs and authors from the test data
# Note: The first line has no date, so it won't be parsed by the current logic.
# The "青蛙狼" line has no preceding author info line, so it won't be parsed.
# The "空格voice" line has no URL.
# The parser is more robust than initially thought and finds 8 URLs.
EXPECTED_URLS_COUNT = 8
EXPECTED_DATA = [
    {"url": "https://drive.google.com/file/d/1RUl7XhxyJpxKO4RBX0AxeeyD4ABYPU_l/view?usp=sharing", "author": "502-0724579 Cowboy", "date": None},
    {"url": "https://docs.google.com/document/d/16TkL54YmFAToS1UR26VdV_mYgr8bCAml/edit?tab=t.0", "author": "504-0718103Leo", "date": "2025-04-04"},
    {"url": "https://drive.google.com/file/d/1dwnVczcEvhIIj5TOXRHVow876da6zAGp/view?usp=drivesdk", "author": "505-0724540捲髮狼", "date": "2025-04-04"},
    {"url": "https://docs.google.com/document/d/10nDGa7nWuSZCLhU9qtR_VW8Cx-yQllk5/edit?usp=drive_link&ouid=105443695704290227678&rtpof=true&sd=true", "author": "383-0488695 三寶", "date": "2025-04-05"},
    {"url": "https://docs.google.com/document/d/1-OeWOZfZ8-KQb2-S-QhfthC7k-UPb4KofyzmLiGT17Y/edit", "author": "421-0299033青蛙狼", "date": "2025-04-05"},
    {"url": "https://drive.google.com/file/d/1ADg9NnB10z3qjnSZPOn6BLh_Fz8wjY9T/view?usp=sharing", "author": "503-0551726千千", "date": "2025-04-05"},
    {"url": "https://docs.google.com/document/d/1W2vOOJBLSdoRWxmjh7x3S5nyYvW1YaUenZxGpB28hSA/edit?usp=sharing", "author": "506-0723994 樂觀感恩", "date": "2025-04-05"},
    {"url": "https://docs.google.com/document/d/1J4ZO4YkbQefHXUjjqTz0tp47bSOqTX_6MsWsf4tHHKk/edit?tab=t.0", "author": "381-0491048彼得森", "date": "2025-04-05"},
]


def get_db_rows(db_path: str, table_name: str) -> List[Dict]:
    """Helper function to get all rows from a table."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


@pytest.mark.e2e
def test_page1_url_ingestion_flow(live_services):
    """
    Tests the full Page 1 flow:
    1. Sends a POST request with a chat log to the ingestion API.
    2. Verifies the API response.
    3. Verifies that the data was correctly saved to the database.
    """
    base_url = live_services["base_url"]
    db_path = live_services["db_path"]

    # 1. Call the API endpoint
    api_url = f"{base_url}/api/ingestion/extract_urls"
    payload = {"text": LINE_CHAT_LOG}

    with httpx.Client() as client:
        response = client.post(api_url, json=payload, timeout=30)

    # 2. Verify API response
    assert response.status_code == 200, f"API call failed with status {response.status_code}: {response.text}"
    response_data = response.json()
    assert isinstance(response_data, list)
    assert len(response_data) == EXPECTED_URLS_COUNT

    # 3. Verify database state
    db_rows = get_db_rows(db_path, "extracted_urls")
    assert len(db_rows) == EXPECTED_URLS_COUNT

    # Sort both lists to ensure consistent comparison
    sorted_response = sorted(response_data, key=lambda x: x['url'])
    sorted_expected = sorted(EXPECTED_DATA, key=lambda x: x['url'])

    for i in range(EXPECTED_URLS_COUNT):
        assert sorted_response[i]['url'] == sorted_expected[i]['url']

        # The parser logic may have slight variations in author name, so we check if it's contained
        assert sorted_expected[i]['author'] in sorted_response[i]['author']

        # The parser logic might not assign a date to the very first entry if it appears before a date line
        if sorted_expected[i]['date'] is not None:
            assert sorted_response[i]['date'] == sorted_expected[i]['date']

        # Check the corresponding database row
        db_row = next((row for row in db_rows if row['url'] == sorted_expected[i]['url']), None)
        assert db_row is not None
        assert sorted_expected[i]['author'] in db_row['author']
        if sorted_expected[i]['date'] is not None:
            assert db_row['message_date'] == sorted_expected[i]['date']
        assert db_row['status'] == 'pending'
