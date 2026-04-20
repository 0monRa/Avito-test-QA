import copy
import random
import re
import string
import time
import uuid

import pytest
import requests
from jsonschema import validate

try:
    import allure
except ModuleNotFoundError:
    class _AllureFallback:
        @staticmethod
        def title(_):
            def decorator(func):
                return func

            return decorator

    allure = _AllureFallback()


BASE_URL = "https://qa-internship.avito.com"
TIMEOUT_SECONDS = 20
REQUEST_RETRIES = 2
UUID_RE = r"^[0-9a-fA-F-]{36}$"

ITEM_SCHEMA = {
    "type": "object",
    "required": ["id", "sellerId", "name", "price", "statistics", "createdAt"],
    "properties": {
        "id": {"type": "string", "pattern": UUID_RE},
        "sellerId": {"type": "integer"},
        "name": {"type": "string"},
        "price": {"type": "integer"},
        "createdAt": {"type": "string"},
        "statistics": {
            "type": "object",
            "required": ["likes", "viewCount", "contacts"],
            "properties": {
                "likes": {"type": "integer"},
                "viewCount": {"type": "integer"},
                "contacts": {"type": "integer"},
            },
        },
    },
}

ITEM_LIST_SCHEMA = {"type": "array", "minItems": 1, "items": ITEM_SCHEMA}

STAT_SCHEMA = {
    "type": "object",
    "required": ["likes", "viewCount", "contacts"],
    "properties": {
        "likes": {"type": "integer"},
        "viewCount": {"type": "integer"},
        "contacts": {"type": "integer"},
    },
}

STAT_LIST_SCHEMA = {"type": "array", "minItems": 1, "items": STAT_SCHEMA}

CREATE_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["status"],
    "properties": {"status": {"type": "string", "pattern": r".*[0-9a-fA-F-]{36}.*"}},
}

ERROR_SCHEMA = {
    "type": "object",
    "required": ["result", "status"],
    "properties": {
        "status": {"type": "string"},
        "result": {
            "type": "object",
            "required": ["message", "messages"],
            "properties": {
                "message": {"type": "string"},
                "messages": {"type": ["object", "null"]},
            },
        },
    },
}


def random_seller_id() -> int:
    return random.randint(111111, 999999)


def random_name(prefix: str = "qa-autotest") -> str:
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{prefix}-{suffix}"


def create_payload(
    *,
    seller_id: int | None = None,
    name: str | None = None,
    price: int = 1000,
    likes: int = 1,
    view_count: int = 10,
    contacts: int = 1,
) -> dict:
    return {
        "sellerID": seller_id if seller_id is not None else random_seller_id(),
        "name": name if name is not None else random_name(),
        "price": price,
        "statistics": {
            "likes": likes,
            "viewCount": view_count,
            "contacts": contacts,
        },
    }


def request_with_retry(method: str, path: str, **kwargs) -> requests.Response:
    last_error = None
    for _ in range(REQUEST_RETRIES + 1):
        try:
            return requests.request(method, f"{BASE_URL}{path}", timeout=TIMEOUT_SECONDS, **kwargs)
        except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout) as err:
            last_error = err
    raise last_error


def create_item(payload: dict) -> requests.Response:
    return request_with_retry("POST", "/api/1/item", json=payload)


def get_v1_item(item_id: str) -> requests.Response:
    return request_with_retry("GET", f"/api/1/item/{item_id}")


def get_v1_items_by_seller(seller_id: int) -> requests.Response:
    return request_with_retry("GET", f"/api/1/{seller_id}/item")


def get_v1_stat(item_id: str) -> requests.Response:
    return request_with_retry("GET", f"/api/1/statistic/{item_id}")


def get_v2_stat(item_id: str) -> requests.Response:
    return request_with_retry("GET", f"/api/2/statistic/{item_id}")


def delete_v2_item(item_id: str) -> requests.Response:
    return request_with_retry("DELETE", f"/api/2/item/{item_id}")


def parse_json(response: requests.Response) -> dict | list:
    assert response.text, "Expected non-empty response body"
    return response.json()


def assert_error_response_schema(response: requests.Response) -> None:
    assert response.status_code in (400, 404), response.text
    body = parse_json(response)
    validate(body, ERROR_SCHEMA)
    assert body["result"]["message"] is not None


def extract_item_id(create_response: requests.Response) -> str:
    body = parse_json(create_response)
    validate(body, CREATE_RESPONSE_SCHEMA)
    status_text = body["status"]
    match = re.search(r"([0-9a-fA-F-]{36})", status_text)
    assert match is not None, f"Cannot extract id from create response: {create_response.text}"
    return match.group(1)


def get_created_item_by_id(item_id: str) -> dict:
    response = get_v1_item(item_id)
    assert response.status_code == 200, response.text
    body = parse_json(response)
    validate(body, ITEM_LIST_SCHEMA)
    return next((item for item in body if item["id"] == item_id), {})


@pytest.fixture()
def created_item() -> dict:
    payload = create_payload()
    response = create_item(payload)
    assert response.status_code == 200, response.text
    item_id = extract_item_id(response)
    return {"request_payload": payload, "item_id": item_id}


@allure.title("POST /api/1/item: schema + data integrity")
@pytest.mark.positive
@pytest.mark.contract
def test_v1_create_contract_and_data_integrity():
    payload = create_payload(price=25000, likes=5, view_count=50, contacts=2)
    response = create_item(payload)

    assert response.status_code == 200, response.text
    item_id = extract_item_id(response)
    created_item_data = get_created_item_by_id(item_id)
    assert created_item_data, f"Created item {item_id} not found"

    assert created_item_data["sellerId"] == payload["sellerID"]
    assert created_item_data["name"] == payload["name"]
    assert created_item_data["price"] == payload["price"]
    assert created_item_data["statistics"] == payload["statistics"]


@allure.title("GET /api/1/item/{id}: JSON schema")
@pytest.mark.positive
@pytest.mark.contract
def test_v1_get_item_contract(created_item):
    response = get_v1_item(created_item["item_id"])
    assert response.status_code == 200, response.text
    body = parse_json(response)
    validate(body, ITEM_LIST_SCHEMA)


@allure.title("GET /api/1/{sellerID}/item: JSON schema")
@pytest.mark.positive
@pytest.mark.contract
def test_v1_get_items_by_seller_contract(created_item):
    seller_id = created_item["request_payload"]["sellerID"]
    response = get_v1_items_by_seller(seller_id)
    assert response.status_code == 200, response.text
    body = parse_json(response)
    validate(body, ITEM_LIST_SCHEMA)
    assert all(item["sellerId"] == seller_id for item in body)


@allure.title("GET /api/1/statistic/{id}: JSON schema")
@pytest.mark.positive
@pytest.mark.contract
def test_v1_get_statistic_contract(created_item):
    response = get_v1_stat(created_item["item_id"])
    assert response.status_code == 200, response.text
    body = parse_json(response)
    validate(body, STAT_LIST_SCHEMA)


@allure.title("Error schema: v1 item invalid id")
@pytest.mark.negative
@pytest.mark.contract
def test_error_schema_v1_get_item_invalid_id():
    response = get_v1_item("invalid-id")
    assert_error_response_schema(response)


@allure.title("Error schema: v1 item nonexistent id")
@pytest.mark.negative
@pytest.mark.contract
def test_error_schema_v1_get_item_nonexistent_id():
    response = get_v1_item(str(uuid.uuid4()))
    assert_error_response_schema(response)


@allure.title("Error schema: v1 statistic invalid id")
@pytest.mark.negative
@pytest.mark.contract
def test_error_schema_v1_get_stat_invalid_id():
    response = get_v1_stat("invalid-id")
    assert_error_response_schema(response)


@allure.title("Error schema: v2 statistic invalid id")
@pytest.mark.negative
@pytest.mark.contract
def test_error_schema_v2_get_stat_invalid_id():
    response = get_v2_stat("invalid-id")
    assert_error_response_schema(response)


@allure.title("Error schema: v2 delete invalid id")
@pytest.mark.negative
@pytest.mark.contract
def test_error_schema_v2_delete_invalid_id():
    response = delete_v2_item("invalid-id")
    assert_error_response_schema(response)


@allure.title("GET /api/2/statistic/{id}: JSON schema")
@pytest.mark.v2
@pytest.mark.contract
def test_v2_get_statistic_contract(created_item):
    response = get_v2_stat(created_item["item_id"])
    assert response.status_code == 200, response.text
    body = parse_json(response)
    validate(body, STAT_LIST_SCHEMA)


@allure.title("DELETE /api/2/item/{id}: successful deletion")
@pytest.mark.v2
def test_v2_delete_item_success():
    payload = create_payload(name=random_name("delete"))
    create_response = create_item(payload)
    assert create_response.status_code == 200, create_response.text
    item_id = extract_item_id(create_response)

    delete_response = delete_v2_item(item_id)
    assert delete_response.status_code == 200, delete_response.text
    assert delete_response.text == ""

    get_response = get_v1_item(item_id)
    assert get_response.status_code == 404, get_response.text
    assert_error_response_schema(get_response)


@allure.title("DELETE /api/2/item/{id}: delete nonexistent id")
@pytest.mark.v2
@pytest.mark.negative
def test_v2_delete_nonexistent_item():
    response = delete_v2_item(str(uuid.uuid4()))
    assert_error_response_schema(response)


# Matrix validation for create payload
MATRIX_CASES = [
    pytest.param("sellerID", lambda p: p.pop("sellerID"), 400, "sellerID", id="missing_sellerID"),
    pytest.param("sellerID", lambda p: p.__setitem__("sellerID", None), 400, "sellerID", id="null_sellerID"),
    pytest.param("sellerID", lambda p: p.__setitem__("sellerID", ""), 400, "", id="empty_string_sellerID"),
    pytest.param("sellerID", lambda p: p.__setitem__("sellerID", "abc"), 400, "", id="string_sellerID"),
    pytest.param("sellerID", lambda p: p.__setitem__("sellerID", 9999999999), 200, None, id="large_sellerID"),
    pytest.param("name", lambda p: p.pop("name"), 400, "name", id="missing_name"),
    pytest.param("name", lambda p: p.__setitem__("name", None), 400, "name", id="null_name"),
    pytest.param("name", lambda p: p.__setitem__("name", ""), 400, "name", id="empty_name"),
    pytest.param("name", lambda p: p.__setitem__("name", "A" * 1000), 200, None, id="long_name"),
    pytest.param("price", lambda p: p.pop("price"), 400, "price", id="missing_price"),
    pytest.param("price", lambda p: p.__setitem__("price", None), 400, "price", id="null_price"),
    pytest.param("price", lambda p: p.__setitem__("price", ""), 400, None, id="empty_string_price"),
    pytest.param("price", lambda p: p.__setitem__("price", "100"), 400, "", id="string_price"),
    pytest.param("price", lambda p: p.__setitem__("price", -1), 200, None, id="negative_price"),
    pytest.param("price", lambda p: p.__setitem__("price", 2**31), 200, None, id="large_price"),
    pytest.param("statistics", lambda p: p.pop("statistics"), 400, "likes", id="missing_statistics"),
    pytest.param("statistics", lambda p: p.__setitem__("statistics", None), 400, "likes", id="null_statistics"),
    pytest.param("statistics.likes", lambda p: p["statistics"].pop("likes"), 400, "likes", id="missing_likes"),
    pytest.param("statistics.likes", lambda p: p["statistics"].__setitem__("likes", None), 400, "likes", id="null_likes"),
    pytest.param("statistics.likes", lambda p: p["statistics"].__setitem__("likes", "1"), 400, None, id="string_likes"),
    pytest.param("statistics.viewCount", lambda p: p["statistics"].pop("viewCount"), 400, "viewCount", id="missing_viewCount"),
    pytest.param("statistics.viewCount", lambda p: p["statistics"].__setitem__("viewCount", None), 400, "viewCount", id="null_viewCount"),
    pytest.param("statistics.viewCount", lambda p: p["statistics"].__setitem__("viewCount", "1"), 400, None, id="string_viewCount"),
    pytest.param("statistics.contacts", lambda p: p["statistics"].pop("contacts"), 400, "contacts", id="missing_contacts"),
    pytest.param("statistics.contacts", lambda p: p["statistics"].__setitem__("contacts", None), 400, "contacts", id="null_contacts"),
    pytest.param("statistics.contacts", lambda p: p["statistics"].__setitem__("contacts", ""), 400, None, id="empty_string_contacts"),
]


@allure.title("POST /api/1/item: payload validation matrix")
@pytest.mark.matrix
@pytest.mark.contract
@pytest.mark.parametrize("field_name,mutator,expected_status,expected_message_part", MATRIX_CASES)
def test_create_item_validation_matrix(field_name, mutator, expected_status, expected_message_part):
    payload = create_payload(name=random_name("matrix"))
    payload = copy.deepcopy(payload)
    mutator(payload)

    response = create_item(payload)
    assert response.status_code == expected_status, f"{field_name}: {response.text}"

    if expected_status == 200:
        item_id = extract_item_id(response)
        created = get_created_item_by_id(item_id)
        assert created, f"{field_name}: created item not found after success response"
        return

    assert_error_response_schema(response)
    body = response.json()
    if expected_message_part is not None:
        assert expected_message_part in body["result"]["message"]


@allure.title("POST /api/1/item: idempotency check")
@pytest.mark.corner
def test_create_item_is_not_idempotent_for_post():
    fixed_payload = create_payload(name=random_name("same-payload"))
    first_response = create_item(fixed_payload)
    second_response = create_item(fixed_payload)

    assert first_response.status_code == 200, first_response.text
    assert second_response.status_code == 200, second_response.text

    first_id = extract_item_id(first_response)
    second_id = extract_item_id(second_response)
    assert first_id != second_id


@allure.title("Core endpoints response time under two seconds")
@pytest.mark.nonfunctional
def test_response_time_under_two_seconds_for_core_flow():
    payload = create_payload(name=random_name("perf"))

    start_create = time.perf_counter()
    create_response = create_item(payload)
    create_elapsed = time.perf_counter() - start_create
    assert create_response.status_code == 200, create_response.text
    assert create_elapsed < 2.0, f"Create took {create_elapsed:.3f}s"

    item_id = extract_item_id(create_response)
    start_get = time.perf_counter()
    get_response = get_v1_item(item_id)
    get_elapsed = time.perf_counter() - start_get
    assert get_response.status_code == 200, get_response.text
    assert get_elapsed < 2.0, f"Get by id took {get_elapsed:.3f}s"
