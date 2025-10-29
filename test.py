import requests
import pandas as pd
import time
from konlpy.tag import Okt
from transformers import AutoTokenizer, AutoModelForSequenceClassification, pipeline
import json
import os

# 네이버 API 인증 정보 (개발자 센터에서 발급)
NAVER_CLIENT_ID = "8UzzcjeXr92mWfAtqo6v"  # 네이버 개발자 센터에서 발급
NAVER_CLIENT_SECRET = "HR8S6o1XFo"
NAVER_MAPS_API_KEY = "oeRWLrI1dXKndxfzThyctuKG56mhe4FOXY889et9"  # 네이버 클라우드 지도 API 키

# KoNLPy와 KoBERT 감성 분석 초기화
okt = Okt()
try:
    tokenizer = AutoTokenizer.from_pretrained("monologg/kobert", trust_remote_code=True)
    model = AutoModelForSequenceClassification.from_pretrained("monologg/kobert", trust_remote_code=True)
    sentiment_analyzer = pipeline("sentiment-analysis", model=model, tokenizer=tokenizer)
except Exception as e:
    print(f"KoBERT loading failed: {e}. Falling back to basic sentiment analysis.")
    sentiment_analyzer = None  # 대체로 기본값 사용

# MBTI 키워드 매핑
mbti_keywords = {
    "INTJ": ["조용", "계획적", "깊이", "평화"],
    "ESFP": ["활기", "파티", "즉흥", "사람"],
    "ENFJ": ["문화", "체험", "친절", "현지"]
}

def search_naver_api(query, search_type="local", display=100, start=1):
    """네이버 검색 API 호출 (지역/블로그/쇼핑)"""
    url = f"https://openapi.naver.com/v1/search/{search_type}.json"
    params = {"query": query, "display": display, "start": start}
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json().get("items", [])
    except requests.RequestException as e:
        print(f"Error in {search_type} search: {e}")
        return []

def get_naver_map_data(address):
    """네이버 지도 API로 위경도"""
    url = f"https://naveropenapi.apigw.ntruss.com/map-geocode/v2/geocode"
    headers_maps = {"X-NCP-APIGW-API-KEY-ID": NAVER_MAPS_API_KEY}
    params = {"query": address}
    try:
        response = requests.get(url, headers=headers_maps, params=params)
        response.raise_for_status()
        data = response.json().get("addresses", [])
        if data:
            return {"lat": float(data[0]["y"]), "lon": float(data[0]["x"])}
        return {"lat": None, "lon": None}
    except requests.RequestException as e:
        print(f"Error in map API: {e}")
        return {"lat": None, "lon": None}

def extract_keywords(text):
    """KoNLPy로 키워드 추출"""
    try:
        nouns = okt.nouns(text)
        adjectives = [word for word, pos in okt.pos(text) if pos == "Adjective"]
        return nouns + adjectives
    except Exception as e:
        print(f"Keyword extraction error: {e}")
        return []

def calculate_mbti_compatibility(text):
    """MBTI 호환성 점수 계산"""
    keywords = extract_keywords(text)
    mbti_scores = {}
    for mbti, mbti_kws in mbti_keywords.items():
        score = sum(1 for kw in keywords if kw in mbti_kws) / max(len(keywords), 1) if keywords else 0.5
        mbti_scores[mbti] = score
    return mbti_scores

def analyze_sentiment(text):
    """KoBERT로 한국어 감성 분석 (대체 로직 포함)"""
    if sentiment_analyzer:
        try:
            result = sentiment_analyzer(text[:512])[0]  # 최대 512자
            score = 1.0 if result["label"] == "LABEL_1" else 0.0  # 긍정/부정
            return score
        except Exception as e:
            print(f"Sentiment analysis error: {e}")
    return 0.5  # 기본값 (KoBERT 실패 시)

def collect_naver_data(queries=["제주도 추천", "서울 맛집", "부산 휴양지"], max_items=1000):
    """네이버 API로 데이터 수집 및 칼럼 생성"""
    data = []
    
    for query in queries:
        # 지역 검색
        for start in range(1, max_items + 1, 100):
            items = search_naver_api(query, "local", display=100, start=start)
            for item in items:
                record = {
                    "item_id": f"local_{item['title']}_{start}",
                    "title": item["title"].replace("<b>", "").replace("</b>", ""),
                    "category": item.get("category", ""),
                    "address": item.get("address", ""),
                    "roadAddress": item.get("roadAddress", ""),
                    "location": get_naver_map_data(item.get("address", "")),
                    "telephone": item.get("telephone", ""),
                    "link": item.get("link", "")
                }
                data.append(record)
            time.sleep(0.1)

        # 블로그 검색
        for start in range(1, max_items + 1, 100):
            items = search_naver_api(query, "blog", display=100, start=start)
            for item in items:
                review_text = item["description"].replace("<b>", "").replace("</b>", "")
                record = {
                    "item_id": f"blog_{item['title']}_{start}",
                    "title": item["title"].replace("<b>", "").replace("</b>", ""),
                    "review_text": review_text,
                    "mbti_compatibility": calculate_mbti_compatibility(review_text),
                    "sentiment_score": analyze_sentiment(review_text),
                    "link": item["link"]
                }
                data.append(record)
            time.sleep(0.1)

        # 쇼핑 검색
        for start in range(1, max_items + 1, 100):
            items = search_naver_api(query, "shop", display=100, start=start)
            for item in items:
                record = {
                    "item_id": f"shop_{item['title']}_{start}",
                    "title": item["title"].replace("<b>", "").replace("</b>", ""),
                    "price": float(item.get("lprice", 0)),
                    "category": item.get("category1", ""),
                    "link": item.get("link", "")
                }
                data.append(record)
            time.sleep(0.1)

    # 데이터랩 (트렌드)
    url = "https://openapi.naver.com/v1/datalab/search"
    body = {
        "startDate": "2025-01-01",
        "endDate": "2025-10-02",
        "timeUnit": "month",
        "keywordGroups": [{"groupName": query, "keywords": [query]} for query in queries]
    }
    try:
        response = requests.post(url, headers=headers, json=body)
        trends = response.json().get("results", [])
        for trend in trends:
            for data_point in trend["data"]:
                for item in data:
                    if trend["title"] in item["title"]:
                        item["issue_trend"] = data_point["ratio"]
    except requests.RequestException as e:
        print(f"Error in datalab API: {e}")

    # 데이터프레임 변환
    df = pd.DataFrame(data)
    
    # 파생 칼럼
    df["travel_style"] = df["category"].apply(
        lambda x: "휴양" if "해변" in x or "리조트" in x else "문화" if "박물관" in x else "기타"
    )
    df["hidden_gem_score"] = df.apply(
        lambda row: 1.0 if row.get("sentiment_score", 0) > 0.8 and "blog" in row["item_id"] else 0.0, axis=1
    )
    df["budget_range"] = df["price"].apply(
        lambda x: "저예산" if x < 500000 else "중급" if x < 1500000 else "고급" if x > 0 else "미정"
    )

    # 중복 제거 및 결측치
    df = df.drop_duplicates(subset=["item_id"]).fillna({"price": 0, "sentiment_score": 0.5, "issue_trend": 0})
    
    return df

def save_data(df, output_path="travel_data.csv"):
    """데이터 저장"""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"Data saved to {output_path}")

if __name__ == "__main__":
    queries = ["제주도 추천", "서울 맛집", "부산 휴양지"]
    df = collect_naver_data(queries, max_items=1000)
    save_data(df, "recommender/data/travel_data.csv")