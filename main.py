import datetime
import requests
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title="영화 박스오피스", page_icon="🎬", layout="wide")

BASE = "https://www.kobis.or.kr/kobisopenapi/webservice/rest"
DAILY_URL = f"{BASE}/boxoffice/searchDailyBoxOfficeList.json"
OLD_URL = f"{BASE}/boxoffice/searchOldAndNewDailyBoxOfficeList.json"
MOVIE_URL = f"{BASE}/movie/searchMovieInfo.json"
SEARCH_URL = f"{BASE}/movie/searchMovieList.json"
TMDB_URL = "https://api.themoviedb.org/3/search/movie"

KST = datetime.timezone(datetime.timedelta(hours=9))
TODAY = datetime.datetime.now(KST).date()
YESTERDAY = TODAY - datetime.timedelta(days=1)


def api_get(url, params):
    response = requests.get(url, params=params, timeout=25)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("API 응답 형식이 올바르지 않습니다.")
    if "faultInfo" in data:
        raise ValueError(str(data["faultInfo"]))
    return data


@st.cache_data(ttl=1800, show_spinner=False)
def daily_data(date_text, key):
    data = api_get(DAILY_URL, {"key": key, "targetDt": date_text})
    return data.get("boxOfficeResult", {}).get("dailyBoxOfficeList", [])


@st.cache_data(ttl=3600, show_spinner=False)
def movie_info(code, key):
    data = api_get(MOVIE_URL, {"key": key, "movieCd": code})
    return data.get("movieInfoResult", {}).get("movieInfo", {})


@st.cache_data(ttl=3600, show_spinner=False)
def search_code(name, open_date, key):
    data = api_get(
        SEARCH_URL,
        {"key": key, "movieNm": name, "itemPerPage": 100},
    )
    items = data.get("movieListResult", {}).get("movieList", [])
    matches = [
        x for x in items
        if x.get("movieNm") == name
        and x.get("openDt", "") == open_date
    ]
    if matches:
        return matches[0].get("movieCd")
    matches = [x for x in items if x.get("movieNm") == name]
    return matches[0].get("movieCd") if len(matches) == 1 else None


@st.cache_data(ttl=86400, show_spinner=False)
def poster_search(name, year, token):
    if not token:
        return None, "TMDB_KEY가 설정되지 않았습니다."
    params = {"query": name, "language": "ko-KR"}
    if year and year.isdigit():
        params["year"] = year

    response = requests.get(
        TMDB_URL,
        params=params,
        headers={
            "Authorization": f"Bearer {token}",
            "accept": "application/json",
        },
        timeout=20,
    )
    if response.status_code in (401, 403):
        return None, "TMDB 인증 실패: API Read Access Token을 확인하세요."
    response.raise_for_status()
    results = response.json().get("results", [])
    results = [x for x in results if x.get("poster_path")]
    if not results:
        return None, "포스터 검색 결과가 없습니다."

    chosen = results[0]
    if year:
        chosen = next(
            (x for x in results if x.get("release_date", "").startswith(year)),
            chosen,
        )
    return "https://image.tmdb.org/t/p/w500" + chosen["poster_path"], None


def date_text(value):
    value = str(value or "")
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value or "정보 없음"


def names(items, field):
    return ", ".join(
        x.get(field, "") for x in items if x.get(field)
    ) or "정보 없음"


# API 키
try:
    KOBIS_KEY = str(st.secrets["KOBIS_KEY"]).strip()
except Exception:
    st.error("Streamlit Cloud Settings → Secrets에 KOBIS_KEY를 등록하세요.")
    st.code('KOBIS_KEY = "발급받은_KOBIS_인증키"', language="toml")
    st.stop()

try:
    TMDB_KEY = str(st.secrets.get("TMDB_KEY", "")).strip()
except Exception:
    TMDB_KEY = ""

# 페이지 상태
if "page" not in st.session_state:
    st.session_state.page = "daily"
if "movie" not in st.session_state:
    st.session_state.movie = None

st.title("🎬 영화 박스오피스")

nav1, nav2 = st.columns(2)
with nav1:
    if st.button("📅 일별 박스오피스", use_container_width=True):
        st.session_state.page = "daily"
        st.session_state.movie = None
        st.rerun()
with nav2:
    if st.button("🏆 역대 흥행 순위", use_container_width=True):
        st.session_state.page = "history"
        st.session_state.movie = None
        st.rerun()

# 영화 상세 화면
if st.session_state.movie is not None:
    selected = st.session_state.movie

    if st.button("← 목록으로 돌아가기"):
        st.session_state.movie = None
        st.rerun()

    name = str(selected.get("movieNm", ""))
    code = str(selected.get("movieCd", "") or "")
    open_date = str(selected.get("openDt", "") or "")

    st.header(f"🎬 {name}")

    try:
        with st.spinner("영화 정보를 불러오는 중입니다..."):
            if not code:
                code = search_code(name, open_date, KOBIS_KEY)
            if not code:
                st.warning("영화 코드를 찾지 못했습니다.")
                st.stop()

            info = movie_info(code, KOBIS_KEY)
            if not info:
                st.warning("상세 정보가 없습니다.")
                st.stop()

            raw_date = info.get("openDt") or open_date
            poster, poster_error = None, None
            try:
                poster, poster_error = poster_search(
                    info.get("movieNm") or name,
                    raw_date[:4],
                    TMDB_KEY,
                )
            except requests.exceptions.RequestException:
                poster_error = "TMDB 연결 오류입니다."

        left, right = st.columns([1, 2])
        with left:
            if poster:
                st.image(poster, use_container_width=True)
            else:
                st.info("포스터를 표시할 수 없습니다.")
                st.caption(poster_error or "")

        with right:
            st.subheader(info.get("movieNm") or name)
            st.write(f"**영문 제목:** {info.get('movieNmEn') or '정보 없음'}")
            st.write(f"**개봉일:** {date_text(raw_date)}")
            st.write(f"**감독:** {names(info.get('directors', []), 'peopleNm')}")
            st.write(f"**배우:** {names((info.get('actors') or [])[:10], 'peopleNm')}")
            st.write(f"**장르:** {names(info.get('genres', []), 'genreNm')}")
            st.write(f"**제작 국가:** {names(info.get('nations', []), 'nationNm')}")
            st.write(f"**상영시간:** {info.get('showTm') or '정보 없음'}분")
            st.write(f"**관람 등급:** {names(info.get('audits', []), 'watchGradeNm')}")

        if selected.get("audiAcc") is not None:
            st.divider()
            c1, c2, c3 = st.columns(3)
            c1.metric("순위", f"{selected.get('rank', '-')}위")
            c2.metric("누적 관객수", f"{int(selected.get('audiAcc', 0)):,}명")
            c3.metric("당일 관객수", f"{int(selected.get('audiCnt', 0)):,}명")

    except requests.exceptions.RequestException as error:
        st.error(f"영화 정보 요청 오류: {error}")
    except ValueError as error:
        st.error(f"영화 정보 오류: {error}")

# 일별 박스오피스 화면
elif st.session_state.page == "daily":
    chosen_date = st.date_input(
        "조회 날짜",
        value=YESTERDAY,
        min_value=datetime.date(2004, 1, 1),
        max_value=YESTERDAY,
    )
    target = chosen_date.strftime("%Y%m%d")

    try:
        with st.spinner("일별 순위를 불러오는 중입니다..."):
            movies = daily_data(target, KOBIS_KEY)
    except (requests.exceptions.RequestException, ValueError) as error:
        st.error(f"박스오피스 조회 오류: {error}")
        st.stop()

    if not movies:
        st.warning("해당 날짜의 데이터가 없습니다.")
        st.stop()

    df = pd.DataFrame(movies)
    for col in ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["movieNm"] = df["movieNm"].fillna("영화명 없음")
    df["openDt"] = df["openDt"].fillna("")
    if "movieCd" not in df.columns:
        df["movieCd"] = ""

    df = df.sort_values("rank").reset_index(drop=True)
    first = df.iloc[0]
    st.subheader(f"🥇 {chosen_date:%Y년 %m월 %d일} 1위 — {first['movieNm']}")

    c1, c2, c3 = st.columns(3)
    c1.metric("관객수", f"{first['audiCnt']:,}명")
    c2.metric("누적 관객수", f"{first['audiAcc']:,}명")
    c3.metric("스크린수", f"{first['scrnCnt']:,}개")

    st.subheader("📋 일별 순위")
    for _, row in df.iterrows():
        cols = st.columns([0.6, 3, 1.2, 1.2, 1.2])
        cols[0].write(f"{row['rank']}위")
        if cols[1].button(
            str(row["movieNm"]),
            key=f"daily_{target}_{row['rank']}",
            use_container_width=True,
        ):
            st.session_state.movie = row.to_dict()
            st.rerun()
        cols[2].write(f"{row['audiCnt']:,}명")
        cols[3].write(f"{row['audiAcc']:,}명")
        cols[4].write(f"{row['scrnCnt']:,}개")

    st.subheader("📊 관객수 상위 5편")
    top = df.nlargest(5, "audiCnt").sort_values("audiCnt")
    chart = px.bar(
        top, x="audiCnt", y="movieNm", orientation="h",
        labels={"audiCnt": "관객수(명)", "movieNm": "영화명"},
        text="audiCnt",
    )
    chart.update_traces(texttemplate="%{text:,}", textposition="outside")
    st.plotly_chart(chart, use_container_width=True)

# 역대 흥행 순위 화면
else:
    st.header("🏆 역대 흥행 순위")
    st.info(
        "아래는 KOBIS 역대 박스오피스 통계 페이지로 연결합니다. "
        "일별 API만으로는 전체 기간 누적 관객수 순위를 정확하게 산출할 수 없습니다."
    )
    st.link_button(
        "KOBIS 공식 역대 박스오피스 열기",
        "https://www.kobis.or.kr/kobis/business/stat/boxs/findFormerBoxOfficeList.do",
        use_container_width=True,
    )

st.caption("데이터 출처: 영화관입장권통합전산망(KOBIS)")
