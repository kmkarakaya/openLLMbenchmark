from scoring import evaluate_response


def test_numeric_scoring_success() -> None:
    verdict = evaluate_response("2.95 milyon TL", "Net kar 2,95 milyon TL olur.")
    assert verdict["status"] == "success"
    assert verdict["score"] == 1
    assert verdict["auto_scored"] is True


def test_text_scoring_fail() -> None:
    verdict = evaluate_response("Rahatladı", "Huzura çıktı")
    assert verdict["status"] == "fail"
    assert verdict["score"] == 0
