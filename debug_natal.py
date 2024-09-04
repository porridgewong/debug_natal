import json
import os
import requests
import streamlit as st
from datetime import datetime
from typing import Dict, List, Tuple
from openai import OpenAI
from volcenginesdkarkruntime import Ark
from zhipuai import ZhipuAI


DEFAULT_PROMPT_TEMPLATE = """
根据我的星盘介绍我的 情感 婚姻 和家庭生活

星盘:

{natal}
"""


def get_api_key(key_name: str) -> str:
    if key_name in os.environ:
        api_key = os.environ.get(key_name)
    else:
        api_key = st.secrets[key_name]
    return api_key


def get_model_endpoint():
    if "ARK_MODEL_ENDPOINT" in os.environ:
        model_endpoint = os.environ.get("ARK_MODEL_ENDPOINT")
    else:
        model_endpoint = st.secrets["ARK_MODEL_ENDPOINT"]
    return model_endpoint


def get_llm_response(prompt, model, llm):
    resp = llm.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": prompt},
        ],
        stream=False,
    )
    return resp.choices[0].message.content


def get_planet_data(data: Dict) -> List[str]:
    res = []
    planet_data = data["data"]["planet"]
    for planet in planet_data:
        sign = planet["sign"]["sign_chinese"]
        planet_name = planet["planet_chinese"]
        res.append(f"{planet_name}落在{sign}座")
    return res


def get_natal(birthday: str, region: Tuple[float, float]) -> List[str]:
    url = "http://www.xingpan.vip/astrology/chart/natal"
    header = {"Content-Type": "application/json;charset=UTF-8"}

    data = {
        "access_token": get_api_key("XINGPAN_ACCESS_TOKEN"),
        "birthday": birthday,
        "h_sys": "P",
        "latitude": str(region[0]),
        "longitude": str(region[1]),
        "planets": ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"],
        "planet_xs": ["433"],
        "planet_xf": ["Regulus"],
        "virtual": ["10"],
        "phase": {"0": 0.5, "30": 0.5},
        "tz": "8.00",
        "svg_type": "-1",
    }

    r = requests.post(url, headers=header, data=json.dumps(data), timeout=60)
    return get_planet_data(eval(r.text))


st.set_page_config(page_title="星座prompt调试", page_icon="🔮")

# load region data
LOCATIONS = {}
PROVINCE_CITY = {}
CITY_DISTRICT = {}
st.session_state.clicked = False


def get_key(location_trace: List[str]) -> str:
    """Generate a key from the location trace."""
    return "-".join(location_trace)


def process_locations(location: Dict, location_trace: List[str]) -> None:
    """Recursively flatten the location data and store the coordinates in LOCATIONS."""
    if len(location["districts"]) == 0:
        LOCATIONS[get_key(location_trace)] = (
            location["center"]["longitude"],
            location["center"]["latitude"],
        )
        return
    for items in location["districts"]:
        location_trace.append(items["name"])
        process_locations(items, location_trace)
        location_trace.pop()


with open("region.json", "r", encoding="utf8") as file:
    data = json.load(file)
    process_locations(data, [])

    # province -> list of cities
    for province in data["districts"]:
        PROVINCE_CITY[province["name"]] = [
            city["name"] for city in province["districts"]
        ]

    # city -> list of districts
    for province in data["districts"]:
        for city in province["districts"]:
            CITY_DISTRICT[city["name"]] = [
                district["name"] for district in city["districts"]
            ]

birth_location = None
birth_time = None


with st.sidebar:
    st.title("输入")

    st.subheader("生日")
    birthday = st.date_input(
        "选择生日",
        datetime(1990, 1, 1),
    )

    st.subheader("出生时间")
    hour = st.selectbox("时", range(0, 24))
    minute = st.selectbox("分", range(0, 60))
    time = f"{hour:02d}:{minute:02d}"
    birth_time = f"{birthday}{time}"

    st.subheader("出生地点")
    province = st.selectbox("省", list(PROVINCE_CITY.keys()))
    city = st.selectbox("市", PROVINCE_CITY[province])
    districts = CITY_DISTRICT[city]
    district = ""
    if len(districts) > 0:
        district = st.selectbox("区", districts)

    if district:
        birth_location = LOCATIONS.get(f"{province}-{city}-{district}")
    else:
        birth_location = LOCATIONS.get(f"{province}-{city}")

    prompt_template = st.text_area("自定义Prompt模板")

    if st.button("提交"):
        natal_data = get_natal(birth_time, birth_location)
        st.session_state.natal = "\n".join(natal_data)
        st.session_state.clicked = True

placeholder = st.empty()

if "natal" in st.session_state:
    placeholder.info(st.session_state.natal)

col1, col2, col3 = st.columns(3)

with col1:
    st.header("gpt4o")
    placeholder1 = st.empty()
    if "gpt" in st.session_state:
        placeholder1.write(st.session_state.gpt)

with col2:
    st.header("glm4")
    placeholder2 = st.empty()
    if "glm" in st.session_state:
        placeholder2.write(st.session_state.glm)

with col3:
    st.header("doubao-pro")
    placeholder3 = st.empty()
    if "doubao" in st.session_state:
        placeholder3.write(st.session_state.doubao)

if (
    st.session_state.clicked
    and "natal" in st.session_state
    and len(st.session_state.natal) > 0
):
    placeholder.info(st.session_state.natal)

    prompt = (
        DEFAULT_PROMPT_TEMPLATE.format(natal=st.session_state.natal).strip()
        if prompt_template == ""
        else f"{prompt_template}\n{st.session_state.natal}"
    )

    with col1:
        placeholder1.empty()
        with st.spinner("Thinking..."):
            client = OpenAI(api_key=get_api_key("OPENAI_API_KEY"))
            response = get_llm_response(prompt, "gpt-4o", client)
            placeholder1.write(response)
            st.session_state.gpt = response

    with col2:
        placeholder2.empty()
        with st.spinner("Thinking..."):
            client = ZhipuAI(api_key=get_api_key("ZHIPU_API_KEY"))
            response = get_llm_response(prompt, "glm-4-0520", client)
            st.write(response)
            st.session_state.glm = response

    with col3:
        placeholder3.empty()
        with st.spinner("Thinking..."):
            client = Ark(api_key=get_api_key("ARK_API_KEY"))
            response = get_llm_response(prompt, get_model_endpoint(), client)
            st.write(response)
            st.session_state.doubao = response

    st.session_state.clicked = False
