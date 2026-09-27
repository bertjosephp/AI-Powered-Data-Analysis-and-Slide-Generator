from fastapi.testclient import TestClient


def test_lists_bundled_samples(client: TestClient) -> None:
    res = client.get("/api/v1/samples")
    assert res.status_code == 200
    samples = {s["name"]: s for s in res.json()}
    assert set(samples) == {
        "ecommerce_orders",
        "saas_churn",
        "hr_attrition",
        "hospital_readmissions",
    }
    churn = samples["saas_churn"]
    assert churn["suggested_target"] == "churned"
    assert churn["rows"] == 3000 and churn["filename"] == "saas_churn.csv"
    assert churn["suggested_question"].endswith("?")


def test_downloads_a_sample_csv(client: TestClient) -> None:
    res = client.get("/api/v1/samples/hr_attrition.csv")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert res.text.splitlines()[0].startswith("employee_id,department")


def test_unknown_sample_is_404_and_paths_are_not_followed(client: TestClient) -> None:
    for name in ["nope", "..%2F..%2Fpyproject", "ecommerce_orders.expected"]:
        res = client.get(f"/api/v1/samples/{name}.csv")
        assert res.status_code == 404
