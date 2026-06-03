#!/usr/bin/env python3
"""
AI 사이클 붕괴 모니터 — 자동 데이터 수집 스크립트
매일 FRED + 시장 데이터를 받아 data.json 생성
GitHub Actions에서 일일 실행
"""

import os
import json
import sys
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fetch_data():
    """FRED + 시장 데이터 수집, 복합지수 계산"""
    try:
        from fredapi import Fred
    except ImportError:
        logger.error("fredapi 미설치. pip install fredapi 실행 후 재시도.")
        sys.exit(1)
    
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance 미설치. pip install yfinance 실행 후 재시도.")
        sys.exit(1)
    
    # FRED API 키 (GitHub Secrets에서 읽음)
    fred_key = os.environ.get("FRED_API_KEY")
    if not fred_key:
        logger.error("FRED_API_KEY 환경변수 미설정. GitHub Secrets에 추가 필요.")
        sys.exit(1)
    
    fred = Fred(api_key=fred_key)
    
    # 지표 정의: (이름, FRED시리즈/ticker, 단위, 방향, 임계치, 가중)
    indicators = {
        "DGS10": {"name": "10Y 국채금리", "type": "fred", "sid": "DGS10", "unit": "%", "dir": "up", "bands": (4.0, 4.6, 5.0), "w": 2},
        "T10Y2Y": {"name": "10Y-2Y 금리차", "type": "fred", "sid": "T10Y2Y", "unit": "%p", "dir": "down", "bands": (-0.5, 0, 0.5), "w": 2},
        "BAMLH0A0HYM2": {"name": "HY 스프레드", "type": "fred", "sid": "BAMLH0A0HYM2", "unit": "%", "dir": "up", "bands": (3.5, 4.5, 6.0), "w": 3},
        "BAMLC0A0CM": {"name": "IG 스프레드", "type": "fred", "sid": "BAMLC0A0CM", "unit": "%", "dir": "up", "bands": (1.2, 1.6, 2.2), "w": 2},
        "DFII10": {"name": "10Y 실질금리", "type": "fred", "sid": "DFII10", "unit": "%", "dir": "up", "bands": (1.5, 2.0, 2.5), "w": 2},
        "T10YIE": {"name": "기대인플레", "type": "fred", "sid": "T10YIE", "unit": "%", "dir": "up", "bands": (2.3, 2.6, 3.0), "w": 2},
        "VIX": {"name": "VIX", "type": "yf", "ticker": "^VIX", "unit": "pt", "dir": "up", "bands": (15, 20, 30), "w": 2},
    }
    
    def get_status(value, bands, direction):
        """값 → 상태(0-3)"""
        if value is None or (isinstance(value, float) and value != value):  # NaN 체크
            return -1
        try:
            v = float(value)
        except:
            return -1
        
        t1, t2, t3 = bands
        if direction == "up":
            return 0 if v < t1 else (1 if v < t2 else (2 if v < t3 else 3))
        else:  # down
            return 0 if v > t3 else (1 if v > t2 else (2 if v > t1 else 3))
    
    data = {"timestamp": datetime.utcnow().isoformat(), "items": {}, "composite": 0}
    total_score = 0
    total_weight = 0
    
    for key, config in indicators.items():
        try:
            if config["type"] == "fred":
                # FRED에서 최신값 1개만 가져오기
                obs = fred.get_series(config["sid"], observations_start_date="2026-05-01")
                if obs is not None and len(obs) > 0:
                    value = float(obs.iloc[-1])
                else:
                    value = None
                    logger.warning(f"{key}: FRED에서 데이터 없음")
            elif config["type"] == "yf":
                # yfinance에서 최신 종가
                ticker = yf.Ticker(config["ticker"])
                hist = ticker.history(period="5d")
                if len(hist) > 0:
                    value = float(hist["Close"].iloc[-1])
                else:
                    value = None
                    logger.warning(f"{key}: Yahoo에서 데이터 없음")
            else:
                value = None
            
            status = get_status(value, config["bands"], config["dir"])
            
            data["items"][key] = {
                "name": config["name"],
                "value": value,
                "unit": config["unit"],
                "status": status,
                "threshold_bands": config["bands"],
                "direction": config["dir"],
                "weight": config["w"]
            }
            
            if status >= 0:
                total_score += status * config["w"]
                total_weight += 3 * config["w"]
            
            logger.info(f"✓ {key}: {value} ({['정상','주의','경계','위험'][status] if status >= 0 else '미지정'})")
        
        except Exception as e:
            logger.error(f"✗ {key}: {e}")
            data["items"][key] = {"value": None, "status": -1, "error": str(e)}
    
    # 복합지수 계산
    if total_weight > 0:
        composite = round(total_score / total_weight * 100)
    else:
        composite = 0
    
    data["composite"] = min(100, max(0, composite))
    
    # 판정
    if data["composite"] < 25:
        verdict = "안정"
    elif data["composite"] < 50:
        verdict = "주의"
    elif data["composite"] < 75:
        verdict = "경계"
    else:
        verdict = "위험·임박"
    
    data["verdict"] = verdict
    
    # data.json 저장
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    logger.info(f"\n복합 위험지수: {data['composite']} ({verdict})")
    logger.info(f"data.json 저장 완료")
    
    return data

if __name__ == "__main__":
    fetch_data()
