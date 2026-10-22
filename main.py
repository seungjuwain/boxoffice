import datetime
import requests
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(
    page_title="어제의 박스오피스",
    page_icon="🎬",
    layout="wide",
)

# ==========================================
# API 설정
# ==========================================
BASE_URL = (
    "https://www.kobis.or.kr/kobisopenapi/webservice/rest/"
)
BOXOFFICE_URL = BASE_URL + "boxoffice/searchDailyBoxOfficeList.json"
MOVIE_INFO_URL = BASE_URL + "movie/searchMovieInfo.json"
MOVIE_SEARCH_URL = BASE_URL + "movie/searchMovieList.json"
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"

KST = datetime.timezone(datetime.timedelta(hours=9))
today_kst = datetime.datetime.now(KST).date()
yesterday = today_kst - datetime.timedelta(days=1)

# ==========================================
# API 호출 함수
# ==========================================
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_boxoffice(date_text, api_key):
    response = requests.get(
        BOXOFFICE_URL,
        params={"key": api_key, "targetDt": date_text},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, dict):
        raise ValueError("올바르지 않은 KOBIS 응답입니다.")

    if "faultInfo" in data:
        raise ValueError(str(data["faultInfo"]))

    return data.get("boxOfficeResult", {}).get(
        "dailyBoxOfficeList", []
    )


@st.cache_data(ttl=3600, show_spinner=False)
def find_movie_code(movie_name, open_date, api_key):
    response = requests.get(
        MOVIE_SEARCH_URL,
        params={
            "key": api_key,
            "movieNm": movie_name,
            "itemPerPage": 100,
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()

    if "faultInfo" in data:
        raise ValueError(str(data["faultInfo"]))

    movies = data.get("movieListResult", {}).get("movieList", [])

    # 제목과 개봉일이 모두 일치하는 영화 우선
    matches = [
        movie for movie in movies
        if movie.get("movieNm") == movie_name
        and movie.get("openDt", "") == open_date
    ]

    if matches:
        return matches[0].get("movieCd")

    # 정확한 제목의 결과가 하나뿐일 때만 사용
    matches = [
        movie for movie in movies
        if movie.get("movieNm") == movie_name
    ]

    if len(matches) == 1:
        return matches[0].get("movieCd")

    return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_movie_info(movie_code, api_key):
    response = requests.get(
        MOVIE_INFO_URL,
        params={"key": api_key, "movieCd": movie_code},
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()

    if "faultInfo" in data:
        raise ValueError(str(data["faultInfo"]))

    return data.get("movieInfoResult", {}).get("movieInfo", {})


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_movie_poster(movie_name, release_year, tmdb_key):
    if not tmdb_key:
        return None

    response = requests.get(
        TMDB_SEARCH_URL,
        params={
            "query": movie_name,
            "language": "ko-KR",
            "year": release_year or None,
        },
        headers={
            "Authorization": f"Bearer {tmdb_key}",
            "accept": "application/json",
        },
        timeout=20,
    )
    response.raise_for_status()
    results = response.json().get("results", [])

    # 포스터가 있는 첫 번째 검색 결과
    movie = next(
        (item for item in results if item.get("poster_path")),
        None,
    )

    if not movie:
        return None

    return "https://image.tmdb.org/t/p/w500" + movie["poster_path"]


def format_release_date(value):
    value = str(value or "")

    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}년 {value[4:6]}월 {value[6:8]}일"

    return value or "정보 없음"


def format_rank_change(value):
    if value > 0:
        return f"↑ {value}"
    if value < 0:
        return f"↓ {abs(value)}"
    return "— 0"


def join_names(items, key):
    return ", ".join(
        item.get(key, "")
        for item in items
        if item.get(key)
    ) or "정보 없음"


# ==========================================
# Secrets 확인
# ==========================================
try:
    API_KEY = str(st.secrets["KOBIS_KEY"]).strip()
except Exception:
    st.error("KOBIS 인증키가 없습니다.")
    st.info(
        "Streamlit Cloud → Settings → Secrets에서 "
        "KOBIS_KEY를 등록하세요."
    )
    st.code('KOBIS_KEY = "발급받은_KOBIS_인증키"', language="toml")
    st.stop()

TMDB_KEY = str(st.secrets.get("TMDB_KEY", "")).strip()

# ==========================================
# 날짜 선택
# ==========================================
st.title("🎬 일별 박스오피스")
st.caption(
    "날짜를 선택하고 영화명을 누르면 영화 상세 정보를 확인할 수 있습니다."
)

selected_date = st.date_input(
    "조회 날짜",
    value=yesterday,
    min_value=datetime.date(2004, 1, 1),
    max_value=yesterday,
    format="YYYY/MM/DD",
)

target_dt = selected_date.strftime("%Y%m%d")
display_date = selected_date.strftime("%Y년 %m월 %d일")

# ==========================================
# 박스오피스 데이터 가져오기
# ==========================================
try:
    with st.spinner("박스오피스를 불러오는 중입니다..."):
        movies = fetch_boxoffice(target_dt, API_KEY)
except requests.exceptions.Timeout:
    st.error("KOBIS 서버 응답 시간이 초과되었습니다.")
    st.stop()
except requests.exceptions.RequestException as error:
    st.error(f"KOBIS 서버 연결 오류: {error}")
    st.stop()
except ValueError as error:
    st.error(f"KOBIS API 오류: {error}")
    st.stop()

if not movies:
    st.warning("해당 날짜의 박스오피스 데이터가 없습니다.")
    st.stop()

df = pd.DataFrame(movies)

required = [
    "rank", "rankInten", "movieNm", "openDt",
    "audiCnt", "audiAcc", "scrnCnt",
]
missing = [col for col in required if col not in df.columns]

if missing:
    st.error("필요한 데이터가 없습니다: " + ", ".join(missing))
    st.stop()

# 숫자 데이터 정리
for col in ["rank", "rankInten", "audiCnt", "audiAcc", "scrnCnt"]:
    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

df["movieNm"] = df["movieNm"].fillna("영화명 없음").astype(str)
df["openDt"] = df["openDt"].fillna("").astype(str)
df["표시 영화명"] = df.apply(
    lambda row: (
        f"{row['movieNm']} 🏆"
        if row["audiAcc"] > 1_000_000
        else row["movieNm"]
    ),
    axis=1,
)
df["순위 변동"] = df["rankInten"].map(format_rank_change)
df = df.sort_values("rank").reset_index(drop=True)

# ==========================================
# 화면 상태
# ==========================================
if "selected_movie" not in st.session_state:
    st.session_state["selected_movie"] = None

selected_movie = st.session_state["selected_movie"]

# ==========================================
# 영화 상세 화면
# ==========================================
if selected_movie is not None:
    if st.button("← 박스오피스로 돌아가기"):
        st.session_state["selected_movie"] = None
        st.rerun()

    movie_name = selected_movie["movieNm"]
    movie_code = selected_movie.get("movieCd")
    open_date = str(selected_movie.get("openDt", ""))

    st.title(f"🎬 {movie_name}")
    st.caption("영화 상세 정보")

    try:
        with st.spinner("영화 정보를 불러오는 중입니다..."):
            if not movie_code:
                movie_code = find_movie_code(
                    movie_name,
                    open_date,
                    API_KEY,
                )

            if not movie_code:
                st.warning(
                    "일치하는 영화 코드를 찾지 못했습니다. "
                    "KOBIS 영화 검색 결과를 확인해 주세요."
                )
                st.stop()

            info = fetch_movie_info(movie_code, API_KEY)

            if not info:
                st.warning("영화 상세 정보가 없습니다.")
                st.stop()

            directors = info.get("directors") or []
            actors = info.get("actors") or []
            genres = info.get("genres") or []
            nations = info.get("nations") or []
            audits = info.get("audits") or []

            director_names = join_names(directors, "peopleNm")
            actor_names = join_names(actors[:10], "peopleNm")
            genre_names = join_names(genres, "genreNm")
            nation_names = join_names(nations, "nationNm")
            grade_names = join_names(audits, "watchGradeNm")

            raw_date = info.get("openDt") or open_date
            release_date = format_release_date(raw_date)

            # 포스터 조회는 선택 사항
            poster_url = None

            if TMDB_KEY:
                try:
                    poster_url = fetch_movie_poster(
                        info.get("movieNm") or movie_name,
                        raw_date[:4] if len(raw_date) >= 4 else "",
                        TMDB_KEY,
                    )
                except (
                    requests.exceptions.RequestException,
                    ValueError,
                ):
                    poster_url = None

        poster_col, detail_col = st.columns([1, 2])

        with poster_col:
            if poster_url:
                st.image(poster_url, use_container_width=True)
            else:
                st.info(
                    "포스터가 없습니다. "
                    "TMDB_KEY 등록 여부를 확인해 주세요."
                )

        with detail_col:
            st.subheader(info.get("movieNm") or movie_name)
            st.write(f"**영문 제목:** {info.get('movieNmEn') or '정보 없음'}")
            st.write(f"**개봉일:** {release_date}")
            st.write(f"**감독:** {director_names}")
            st.write(f"**출연 배우:** {actor_names}")
            st.write(f"**장르:** {genre_names}")
            st.write(f"**제작 국가:** {nation_names}")

            show_time = info.get("showTm")
            st.write(
                f"**상영시간:** {show_time}분"
                if show_time
                else "**상영시간:** 정보 없음"
            )

            st.write(f"**관람 등급:** {grade_names}")
            st.write(f"**영화 유형:** {info.get('typeNm') or '정보 없음'}")

        st.divider()
        st.subheader(f"📊 {display_date} 박스오피스 성적")

        c1, c2, c3 = st.columns(3)
        c1.metric("순위", f"{selected_movie.get('rank', '-')}위")
        c2.metric(
            "당일 관객수",
            f"{int(selected_movie.get('audiCnt', 0)):,}명",
        )
        c3.metric(
            "누적 관객수",
            f"{int(selected_movie.get('audiAcc', 0)):,}명",
        )

        st.caption("영화 상세 정보 출처: KOBIS")
        if poster_url:
            st.caption("포스터 이미지 출처: TMDB")

    except requests.exceptions.RequestException:
        st.error("영화 정보 요청에 실패했습니다. 잠시 후 다시 시도해 주세요.")
    except ValueError as error:
        st.error(f"영화 정보를 처리할 수 없습니다: {error}")

# ==========================================
# 박스오피스 순위 화면
# ==========================================
else:
    first = df.iloc[0]

    st.subheader(f"🥇 {display_date} 1위 — {first['표시 영화명']}")

    c1, c2, c3 = st.columns(3)
    c1.metric("관객수", f"{first['audiCnt']:,}명")
    c2.metric("누적 관객수", f"{first['audiAcc']:,}명")
    c3.metric("스크린수", f"{first['scrnCnt']:,}개")

    st.subheader("📋 박스오피스 순위")
    st.caption("아래 영화명을 클릭하면 상세 화면으로 이동합니다.")

    header = st.columns([0.5, 1.0, 2.8, 1.2, 1.2, 1.2, 1.0])
    labels = [
        "순위", "전일 대비", "영화명",
        "개봉일", "관객수", "누적관객", "스크린수",
    ]

    for col, label in zip(header, labels):
        col.markdown(f"**{label}**")

    for _, row in df.iterrows():
        cols = st.columns([0.5, 1.0, 2.8, 1.2, 1.2, 1.2, 1.0])

        cols[0].write(int(row["rank"]))

        change = row["순위 변동"]
        if change.startswith("↑"):
            cols[1].markdown(f":red[**{change}**]")
        elif change.startswith("↓"):
            cols[1].markdown(f":blue[**{change}**]")
        else:
            cols[1].write(change)

        if cols[2].button(
            str(row["표시 영화명"]),
            key=f"movie_{target_dt}_{row['rank']}",
            use_container_width=True,
        ):
            st.session_state["selected_movie"] = row.to_dict()
            st.rerun()

        cols[3].write(row["openDt"] or "-")
        cols[4].write(f"{row['audiCnt']:,}")
        cols[5].write(f"{row['audiAcc']:,}")
        cols[6].write(f"{row['scrnCnt']:,}")

    st.subheader("📊 관객수 상위 5편")

    top5 = df.nlargest(5, "audiCnt").sort_values(
        "audiCnt",
        ascending=True,
    )

    chart = px.bar(
        top5,
        x="audiCnt",
        y="표시 영화명",
        orientation="h",
        labels={
            "audiCnt": "관객수(명)",
            "표시 영화명": "영화명",
        },
        text="audiCnt",
    )

    chart.update_traces(
        texttemplate="%{text:,}",
        textposition="outside",
        cliponaxis=False,
    )

    chart.update_layout(
        yaxis_title="",
        xaxis_title="관객수(명)",
        margin=dict(l=10, r=40, t=20, b=10),
    )

    st.plotly_chart(chart, use_container_width=True)

    st.caption(
        "데이터 출처: 영화관입장권통합전산망(KOBIS) 일별 박스오피스 API"
    )
